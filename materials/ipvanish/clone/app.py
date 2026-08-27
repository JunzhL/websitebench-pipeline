"""IPVanish offline clone.

Served documents are the frozen rendered DOM, localized by
``tools/build_clone_pages.py`` and cached here as plain strings.  They are not
templates: the captured stylesheets are full of ``){#id`` sequences and one
inline config carries ``{{id}}``, so anything Jinja-shaped would have to be
fought rather than used.  Request-time content is spliced against captured
anchors by ``htmlslice``, which walks the tag stack and hard-fails when an
anchor moved -- a build error beats a silently unspliced page.

Boundaries this file keeps:

* Auth, sessions, mail and payments only through the vendored seam
  (``backend/site_backend_integration.py`` -> ``backend/db.py``).
* No field anywhere accepts card data.  The source's Zuora card iframe is
  replaced by an honestly labelled local-sandbox outcome selector, and every
  submitted key and value is screened by ``db.reject_payment_fields``.
* Order amounts are derived from ``backend/catalogue.py`` server-side and are
  never read from the request.
* An unmatched path answers HTTP 404 with the home document as its body, which
  is what the source does.

Everything under ``/account`` and ``/checkout/confirmation`` is clone-local
inference: the source gates account creation behind a purchase, so no
subscriber or post-payment state was ever observed.  Those pages say so.
"""

from __future__ import annotations

import hashlib
import hmac
import html
import json
import os
import re
import sys
from pathlib import Path
from string import Template

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:  # vendored websitebench + backend imports
    sys.path.insert(0, str(ROOT))

# Writable-state location.  Harbor's ABI passes DATA_DIR; the offline-clone
# live sandbox passes WEBSITEBENCH_DATA_DIR, and the vendored runtime keeps the
# older CLAWBENCH_DATA_DIR name.  Reading only DATA_DIR left the JEFIT database
# in the read-only candidate root, so every write route answered 500 under the
# live diagnostic while read-only pages passed.  This must run before the
# backend import, because the seam binds its database path at open time.
_DATA_DIR = (
    os.environ.get("DATA_DIR")
    or os.environ.get("WEBSITEBENCH_DATA_DIR")
    or os.environ.get("CLAWBENCH_DATA_DIR")
)
if _DATA_DIR and "WEBSITEBENCH_SITE_BACKEND_DATABASE" not in os.environ:
    os.environ["WEBSITEBENCH_SITE_BACKEND_DATABASE"] = str(
        Path(_DATA_DIR).resolve() / "ipvanish.sqlite3"
    )

from fastapi import FastAPI, Request  # noqa: E402
from fastapi.responses import (  # noqa: E402
    HTMLResponse,
    JSONResponse,
    RedirectResponse,
    Response,
)
from fastapi.staticfiles import StaticFiles  # noqa: E402

from backend import db  # noqa: E402
from backend.catalogue import (  # noqa: E402
    BY_ID,
    PERIOD_BY_QUERY,
    PLANS,
    money,
    plan_for_flow,
)
from htmlslice import (  # noqa: E402
    drop_element,
    replace_element,
    replace_nth,
    replace_once,
)
from websitebench.local_clone_auth import (  # noqa: E402
    AuthError,
    AuthRejected,
    AuthValidationError,
)
from websitebench.site_backend import PaymentError  # noqa: E402


SITE_ID = "ipvanish"
PAGES = ROOT / "frontend" / "pages"
FRAGMENTS = ROOT / "frontend" / "fragments"
STATIC_DIR = ROOT / "static"
EXTERNAL_LINKS = json.loads(
    (ROOT / "frontend" / "external-links.json").read_text(encoding="utf-8")
)
ADMIN_TOKEN = os.environ.get(
    "WEBSITEBENCH_IPVANISH_ADMIN_TOKEN", "ipvanish-local-admin"
)
BUILD_ID = os.environ.get("DEPLOYMENT_BUILD_ID") or os.environ.get(
    "WEBSITEBENCH_BUILD_ID"
)
CONTENT_SECURITY_POLICY = (
    "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
    "script-src 'self'; font-src 'self' data:; connect-src 'self'; "
    # 'self', not 'none': the captured pages carry <iframe>s whose third-party
    # sources are rewritten to this origin's own /embed/ boundary. With
    # frame-ancestors 'none' the clone refused to frame its own documents, and
    # the source's `.video-frame { background: #000 }` showed through as the
    # blank black rectangle a blind review flagged on /why-vpn/. Third-party
    # framing of the clone is still forbidden.
    "frame-src 'self'; frame-ancestors 'self'; base-uri 'self'; "
    "form-action 'self'"
)
_HEALTH_BODY = json.dumps({"ok": True, "site_id": SITE_ID}, separators=(",", ":"))
MAIN_SENTINEL = "<!--ipvanish-clone-main-->"

app = FastAPI(
    title="IPVanish offline clone",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

_page_cache: dict[str, str] = {}
_fragment_cache: dict[str, Template] = {}


def esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def page(name: str) -> str:
    """Read one served document, cached; the tree is immutable at runtime."""

    cached = _page_cache.get(name)
    if cached is None:
        cached = (PAGES / f"{name}.html").read_text(encoding="utf-8")
        _page_cache[name] = cached
    return cached


def fragment(name: str, **values: str) -> str:
    """Render one clone-local form fragment.

    The three POST forms live in ``frontend/fragments/`` rather than in Python
    string literals so that exactly one file under ``clone/`` declares each
    ``method="post" action="..."`` pair.  Harbor's ``derive-from-clone`` reads
    the templates on disk to resolve a form-backed submit step, and a form built
    only at request time is invisible to it.

    ``string.Template`` raises on an unknown or missing placeholder, so a
    fragment and its caller cannot drift apart silently.
    """

    cached = _fragment_cache.get(name)
    if cached is None:
        cached = Template((FRAGMENTS / f"{name}.html").read_text(encoding="utf-8"))
        _fragment_cache[name] = cached
    return cached.substitute(**values)


def shell(main_html: str) -> str:
    """A clone-local page inside the captured marketing chrome."""

    return page("_shell").replace(MAIN_SENTINEL, main_html, 1)


def inference_banner(what: str) -> str:
    return (
        '<div class="ipvanish-clone-note" role="note">'
        "<strong>Clone-local view.</strong> "
        f"{esc(what)} was never reachable on the source site — IPVanish gates "
        "account creation behind a paid subscription — so this page is offline-"
        "clone inference, not a reproduction of a captured screen."
        "</div>"
    )


# --------------------------------------------------------------------------
# sessions
# --------------------------------------------------------------------------


def cookie_name() -> str:
    return db.backend().config.cookie_name


def set_session_cookie(response: Response, token: str) -> None:
    facts = db.backend().session_cookie
    response.set_cookie(
        facts["name"],
        token,
        secure=facts["secure"],
        httponly=facts["httponly"],
        samesite=facts["samesite"],
        path=facts["path"],
    )


def session_token(request: Request) -> str | None:
    return request.cookies.get(cookie_name())


def ensure_session(request: Request) -> str:
    token, _ = db.auth().ensure_session(session_token(request))
    return token


def current_subject(request: Request) -> str | None:
    token = session_token(request)
    if not token:
        return None
    session = db.auth().resolve_session(token)
    if not session or not session.get("authenticated"):
        return None
    account = session.get("account") or {}
    subject = account.get("subject_id")
    return str(subject) if subject else None


def current_account(request: Request) -> dict | None:
    subject = current_subject(request)
    if subject is None:
        return None
    return db.account_by_subject(subject)


# --------------------------------------------------------------------------
# infrastructure
# --------------------------------------------------------------------------


class _MirrorStaticFiles(StaticFiles):
    """Retry percent-encoded on-disk names; the mirror keeps source encoding."""

    def lookup_path(self, path: str):  # type: ignore[override]
        full_path, stat_result = super().lookup_path(path)
        if stat_result is not None:
            return full_path, stat_result
        import urllib.parse

        requoted = "/".join(
            urllib.parse.quote(segment) for segment in path.split("/")
        )
        if requoted != path:
            retry_path, retry_stat = super().lookup_path(requoted)
            if retry_stat is not None:
                return retry_path, retry_stat
        return full_path, stat_result


app.mount("/static", _MirrorStaticFiles(directory=str(STATIC_DIR)), name="static")


@app.middleware("http")
async def runtime_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["Content-Security-Policy"] = CONTENT_SECURITY_POLICY
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    if BUILD_ID:
        response.headers["X-WebsiteBench-Build-Id"] = BUILD_ID
    return response


@app.get("/healthz", include_in_schema=False)
async def healthz() -> Response:
    return Response(content=_HEALTH_BODY, media_type="application/json")


@app.get("/__websitebench/health", include_in_schema=False)
async def harbor_health() -> Response:
    return Response(content='{"status":"ok"}', media_type="application/json")


@app.post("/__admin/reset", include_in_schema=False)
async def admin_reset(request: Request) -> Response:
    token = request.headers.get("X-WebsiteBench-Admin-Token", "")
    if not hmac.compare_digest(token, ADMIN_TOKEN):
        return JSONResponse({"error": "forbidden"}, status_code=403)
    db.reset()
    return JSONResponse({"reset": True, "site_id": SITE_ID})


def not_found() -> HTMLResponse:
    """The source answers an unknown path 404 with the home page as its body.

    Byte-near-identical to `/`, no "404" string anywhere, primary navigation
    intact.  There is no branded not-found view to build.
    """

    return HTMLResponse(page("home"), status_code=404)


@app.exception_handler(404)
async def not_found_handler(request: Request, exc: Exception) -> Response:
    if request.url.path.startswith(("/api/", "/__websitebench/")):
        return JSONResponse({"error": "not-found"}, status_code=404)
    return not_found()


# --------------------------------------------------------------------------
# marketing tree
# --------------------------------------------------------------------------

MARKETING_ROUTES = {
    "/why-vpn/": "why-vpn",
    "/what-is-a-vpn/": "what-is-a-vpn",
    "/servers/": "servers",
    "/vpn-features/": "vpn-features",
    "/vpn-features/threat-protection/": "threat-protection",
    "/money-back-guarantee/": "money-back-guarantee",
    "/coupons/": "coupons",
    "/vpn-locations/": "vpn-locations",
    "/reviews/": "reviews",
    "/trust/": "trust",
    "/no-log-vpn-policy/": "no-log-vpn-policy",
    "/secure-browser/": "secure-browser",
    "/cloud-storage/": "cloud-storage",
    "/vpn-setup/windows/": "vpn-setup-windows",
    "/vpn-for-streaming/": "vpn-for-streaming",
    "/resources/": "resources",
    "/setup-guides/": "setup-guides",
    "/what-is-my-ip-address/": "what-is-my-ip-address",
    "/blog/": "blog",
    "/tos/": "tos",
    "/privacy-policy/": "privacy-policy",
    "/partners/": "partners",
    "/press/": "press",
}

# States of `/` the source reaches by hovering or tapping.  clone.js performs
# the same class mutation on a real click; these paths let a driver land on the
# state directly as well.
HOME_STATES = {
    "product": "nav-product",
    "apps": "nav-apps",
    "resources": "nav-resources",
}


@app.get("/", include_in_schema=False)
async def home(request: Request) -> HTMLResponse:
    nav = (request.query_params.get("nav") or "").strip().casefold()
    if nav in HOME_STATES:
        return HTMLResponse(page(HOME_STATES[nav]))
    if (request.query_params.get("menu") or "").strip().casefold() == "open":
        return HTMLResponse(page("mobile-menu-open"))
    return HTMLResponse(page("home"))


def _register_marketing(route: str, name: str) -> None:
    @app.get(route, include_in_schema=False)
    async def marketing_page(_name: str = name) -> HTMLResponse:
        return HTMLResponse(page(_name))

    @app.get(route.rstrip("/"), include_in_schema=False)
    async def marketing_redirect(_route: str = route) -> RedirectResponse:
        # The source 301s the unslashed form; captured markup links to both.
        return RedirectResponse(_route, status_code=308)


for _route, _name in MARKETING_ROUTES.items():
    _register_marketing(_route, _name)


@app.get("/external/{slug}", include_in_schema=False)
async def external_boundary(slug: str) -> HTMLResponse:
    """Every off-site link lands here, so no served document holds a remote href."""

    target = EXTERNAL_LINKS.get(slug)
    body = (
        '<div class="ipvanish-clone-note" role="note">'
        "<strong>External link.</strong> This link leaves the captured site. "
        "The offline clone makes no request to it."
        + (f"<br>Source target: <code>{esc(target)}</code>" if target else "")
        + '<br><a href="/">Return to the IPVanish home page</a></div>'
    )
    return HTMLResponse(shell(body), status_code=200 if target else 404)


# --------------------------------------------------------------------------
# pricing
# --------------------------------------------------------------------------

PRICING_PAGES = {
    None: "pricing",
    "biennial": "pricing-2year",
    "annual": "pricing-yearly",
    "monthly": "pricing-monthly",
}


@app.get("/embed/{slug}", include_in_schema=False)
async def embed_boundary(slug: str) -> HTMLResponse:
    """The in-frame counterpart of /external/<slug>.

    A captured ``<iframe>`` keeps its own geometry, so the slot's size and
    position are exactly the source's; only what paints inside it is ours. The
    source's YouTube embed painted a player poster, and a blind review called
    the resulting empty rectangle the one confidently distinguishable thing on
    ``/why-vpn/``. Loading youtube.com is forbidden by the closure invariant and
    reshipping the poster artwork would be republishing third-party content, so
    the slot gets a neutral local panel that says so instead: no third-party
    imagery, and no play affordance implying it would work.
    """

    target = EXTERNAL_LINKS.get(slug)
    host = ""
    if target:
        from urllib.parse import urlsplit

        host = urlsplit(target).netloc
    return HTMLResponse(
        "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        "<title>External embed</title>"
        '<link rel="stylesheet" href="/static/site/clone.css">'
        "</head><body class=\"ipvanish-embed\">"
        '<div class="ipvanish-embed__panel" role="note">'
        '<p class="ipvanish-embed__title">External embed not loaded</p>'
        + (
            f'<p class="ipvanish-embed__host">{esc(host)}</p>'
            if host
            else ""
        )
        + '<p class="ipvanish-embed__body">This offline clone makes no request to '
        "third-party services, so the embedded content is out of scope. The "
        "surrounding layout is reproduced from the captured page.</p>"
        "</div></body></html>",
        status_code=200 if target else 404,
    )


@app.get("/pricing/", include_in_schema=False)
async def pricing(request: Request) -> HTMLResponse:
    """Three billing periods, one visible at a time.

    Each period is its own captured document, in which the two other periods'
    panels carry the source's own ``display: none``.  clone.js additionally
    performs the source's client-side toggle, so a real click switches period
    without a round trip; this route exists so the state is also addressable.
    """

    raw = (request.query_params.get("period") or "").strip().casefold()
    period = PERIOD_BY_QUERY.get(raw) if raw else None
    return HTMLResponse(page(PRICING_PAGES[period]))


@app.get("/pricing", include_in_schema=False)
async def pricing_redirect() -> RedirectResponse:
    return RedirectResponse("/pricing/", status_code=308)


# --------------------------------------------------------------------------
# checkout
# --------------------------------------------------------------------------

CHECKOUT_PATH = "/checkout/address-payment-method"
SUMMARY_PRICE = '<span class="c-summary-prices__item__price"> $0.00 </span>'
SUMMARY_DISCOUNT = (
    '<span class="c-summary-prices__item__price"> -&nbsp;$0.00 </span>'
)
SUMMARY_TOTAL = '<span class="u-margin-right--x-small">$</span><span>0.00</span>'
DISCOUNT_ROW = '<div class="price-row discount-row ng-star-inserted">'
BADGE_BLOCK = '<div class="badge-container new-flow-design ng-star-inserted">'
CARD_WITH_BADGE = (
    '<div class="checkout-section__card new-flow-design ng-star-inserted has-badge">'
)
CARD_WITHOUT_BADGE = (
    '<div class="checkout-section__card new-flow-design ng-star-inserted">'
)
ZUORA_SLOT = '<div id="zuora_payment" class="u-margin-top--base ng-star-inserted">'
SUBSCRIBE_BUTTON = (
    '<button tabindex="0" type="button" class="c-button c-button--primary">'
)
PRODUCT_NAME = re.compile(r'(<span dynamic="SuiteProduct_name">)([^<]*)(</span>)')
SAVE_PERCENT = re.compile(r'(<span class="ng-star-inserted">&nbsp;)(\d+)(%</span>)')
CAPTURED_DISCLOSURE = (
    "By clicking the subscribe button you agree to be charged 46.68 per first "
    "year. Your plan renews automatically until you cancel at any time through "
    "your IPVanish account."
)
WALLET_ROWS = {
    "paypal": "PayPal",
    "applepay": "Apple Pay",
    "googlepay": "Google Pay",
}
SCENARIOS = (
    ("sandbox-approved", "Simulated approval"),
    ("sandbox-declined", "Simulated decline"),
    ("sandbox-retry", "Simulated retry"),
)
BILLING_COUNTRIES = (
    ("US", "United States"),
    ("CA", "Canada"),
    ("GB", "United Kingdom"),
    ("AU", "Australia"),
    ("DE", "Germany"),
    ("FR", "France"),
    ("NL", "Netherlands"),
    ("SE", "Sweden"),
)


def _idempotency_key(token: str, flow: str, attempt: int) -> str:
    digest = hashlib.sha256(f"{token}|{flow}|{attempt}".encode()).hexdigest()
    return f"ck{digest[:38]}"


def _splice_summary(document: str, plan) -> str:
    """Fill the captured Order Summary from the catalogue, server-side."""

    document = PRODUCT_NAME.sub(
        lambda m: f"{m.group(1)}{esc(plan.product_name)}{m.group(3)}", document, count=1
    )
    if plan.discount_minor <= 0:
        if DISCOUNT_ROW in document:
            document = drop_element(document, DISCOUNT_ROW)
        if BADGE_BLOCK in document:
            document = drop_element(document, BADGE_BLOCK)
        if CARD_WITH_BADGE in document:
            document = replace_once(document, CARD_WITH_BADGE, CARD_WITHOUT_BADGE)
    else:
        document = SAVE_PERCENT.sub(
            lambda m: f"{m.group(1)}{plan.save_percent}{m.group(3)}",
            document,
            count=1,
        )
        document = replace_once(
            document,
            SUMMARY_DISCOUNT,
            '<span class="c-summary-prices__item__price"> -&nbsp;'
            f"{money(plan.discount_minor)} </span>",
        )
    document = replace_nth(
        document,
        SUMMARY_PRICE,
        [
            '<span class="c-summary-prices__item__price"> '
            f"{money(plan.list_minor)} </span>",
            '<span class="c-summary-prices__item__price"> '
            f"{money(plan.tax_minor)} </span>",
        ],
    )
    return replace_once(
        document,
        SUMMARY_TOTAL,
        '<span class="u-margin-right--x-small">$</span>'
        f"<span>{money(plan.total_minor)[1:]}</span>",
    )


def _sandbox_form(plan, key: str, attempt: int, contact: dict | None) -> str:
    """The clone-local replacement for the source's hosted card iframe.

    The captured form's card number, cardholder name, expiry month, expiry year
    and security code have no counterpart here by design: the candidate offers
    no field capable of carrying card data.  The account email and the billing
    country and postal code are kept because they are real business inputs.
    """

    countries = "".join(
        f'<option value="{esc(code)}"'
        f'{" selected" if contact and contact.get("country") == code else ""}'
        f">{esc(label)}</option>"
        for code, label in BILLING_COUNTRIES
    )
    scenarios = "".join(
        '<label class="ipvanish-sandbox__scenario">'
        f'<input type="radio" name="scenario_id" value="{esc(scenario)}"'
        f'{" checked" if index == 0 else ""}> {esc(label)}</label>'
        for index, (scenario, label) in enumerate(SCENARIOS)
    )
    return fragment(
        "sandbox-checkout-form",
        flow=esc(plan.flow),
        key=esc(key),
        attempt=str(attempt),
        email=esc((contact or {}).get("email", "")),
        postal=esc((contact or {}).get("postal_code", "")),
        countries=countries,
        scenarios=scenarios,
    )


def _checkout_document(
    plan,
    *,
    method: str | None,
    key: str,
    attempt: int,
    contact: dict | None,
    notice: str = "",
) -> str:
    if method == "card":
        document = page("checkout-card-form")
    elif plan.has_badge:
        document = page("checkout-chooser-essential-annual")
    else:
        document = page("checkout-chooser-essential-monthly")
    document = _splice_summary(document, plan)
    if method == "card":
        document = replace_element(
            document, ZUORA_SLOT, _sandbox_form(plan, key, attempt, contact)
        )
        document = replace_once(
            document,
            SUBSCRIBE_BUTTON,
            '<button tabindex="0" type="submit" form="ipvanish-sandbox-form"'
            ' class="c-button c-button--primary" data-clone-action="subscribe">',
        )
        if CAPTURED_DISCLOSURE in document:
            document = replace_once(
                document, CAPTURED_DISCLOSURE, esc(plan.recurring_disclosure)
            )
    elif method in WALLET_ROWS:
        notice = notice or (
            f"{WALLET_ROWS[method]} is a third-party wallet. "
            "scope/purpose.json places live wallet providers out of scope, so "
            "this offline clone renders the row without contacting them. "
            "Choose Credit card to continue with the local sandbox."
        )
    if notice:
        document = replace_once(
            document,
            '<div class="checkout-page__main ng-star-inserted">',
            '<div class="checkout-page__main ng-star-inserted">'
            f'<div class="ipvanish-clone-note" role="alert">{esc(notice)}</div>',
        )
    return document


@app.get(CHECKOUT_PATH, include_in_schema=False)
async def checkout(request: Request) -> Response:
    flow = request.query_params.get("flow")
    plan = plan_for_flow(flow)
    if plan is None:
        return RedirectResponse("/pricing/", status_code=303)
    method = (request.query_params.get("method") or "").strip().casefold() or None
    if method not in {None, "card", *WALLET_ROWS}:
        method = None
    token = ensure_session(request)
    attempt = 0
    document = _checkout_document(
        plan,
        method=method,
        key=_idempotency_key(token, plan.flow, attempt),
        attempt=attempt,
        contact=None,
    )
    response = HTMLResponse(document)
    set_session_cookie(response, token)
    return response


@app.get("/checkout/subscribe", include_in_schema=False)
async def checkout_subscribe_form(request: Request) -> Response:
    """The route that accepts the subscription also renders the form for it.

    Clone-local: the source has no such route -- its Angular bundle POSTs to a
    Zuora endpoint. It exists so the registration form is reachable by a plain
    GET at the same path its ``action`` names, which is what lets a contract
    resolve a form-backed submit step rather than guessing a selector. It serves
    the same document as ``?method=card`` for the flow given, defaulting to the
    annual Essential plan that trace 687 selects.
    """

    plan = plan_for_flow(request.query_params.get("flow")) or BY_ID["essential-annual"]
    token = ensure_session(request)
    document = _checkout_document(
        plan,
        method="card",
        key=_idempotency_key(token, plan.flow, 0),
        attempt=0,
        contact=None,
    )
    response = HTMLResponse(document)
    set_session_cookie(response, token)
    return response


@app.post("/checkout/subscribe", include_in_schema=False)
async def checkout_subscribe(request: Request) -> Response:
    form = dict(await request.form())
    try:
        db.reject_payment_fields(form)
    except db.PaymentFieldRejected as error:
        return JSONResponse(
            {"error": "payment-field-rejected", "detail": str(error)},
            status_code=422,
        )
    plan = plan_for_flow(str(form.get("flow", "")))
    if plan is None:
        return RedirectResponse("/pricing/", status_code=303)
    token = ensure_session(request)
    account_email = str(form.get("account_email", "")).strip()
    country = str(form.get("billing_country", "")).strip()
    postal_code = str(form.get("billing_postal_code", "")).strip()
    scenario_id = str(form.get("scenario_id", "")).strip()
    try:
        attempt = max(0, min(9, int(str(form.get("attempt", "0")) or "0")))
    except ValueError:
        attempt = 0
    contact = {"email": account_email, "country": country, "postal_code": postal_code}

    def rendered(notice: str, next_attempt: int, status: int = 200) -> Response:
        document = _checkout_document(
            plan,
            method="card",
            key=_idempotency_key(token, plan.flow, next_attempt),
            attempt=next_attempt,
            contact=contact,
            notice=notice,
        )
        response = HTMLResponse(document, status_code=status)
        set_session_cookie(response, token)
        return response

    if not account_email or "@" not in account_email:
        return rendered("Enter the email address for your account.", attempt, 422)
    if not country or not postal_code:
        return rendered(
            "Enter the billing country and postal code for your account.",
            attempt,
            422,
        )
    if scenario_id not in {identifier for identifier, _ in SCENARIOS}:
        return rendered("Choose a simulated payment outcome.", attempt, 422)

    subject = "ipvanish-checkout-" + hashlib.sha256(
        account_email.casefold().encode()
    ).hexdigest()[:24]
    try:
        # The account row is written only once the sandbox approves, so a
        # declined or retryable attempt leaves no trace at all.
        result = db.purchase(
            subject_id=subject,
            plan=plan,
            scenario_id=scenario_id,
            idempotency_key=str(form.get("idempotency_key", ""))
            or _idempotency_key(token, plan.flow, attempt),
        )
    except PaymentError as error:
        return rendered(f"The local sandbox refused this attempt: {error}", attempt + 1, 422)
    if result["outcome"] == "declined":
        return rendered(
            "Simulated decline: the local sandbox declined this attempt, so no "
            "subscription and no order were created. Choose another simulated "
            "outcome and try again.",
            attempt + 1,
        )
    if result["outcome"] == "retryable":
        return rendered(
            "Simulated retry: the local sandbox asked for another attempt, so "
            "no subscription and no order were created yet. Submit again — the "
            "local-sandbox contract binds each outcome to its scenario id, so a "
            "successful retry uses the approval scenario.",
            attempt + 1,
        )
    db.ensure_checkout_account(
        subject, email=account_email, display_name=account_email.split("@")[0]
    )
    db.update_billing_contact(
        subject,
        full_name=account_email.split("@")[0],
        email=account_email,
        country=country,
        postal_code=postal_code,
    )
    db.record_receipt(
        db.auth().session_owner_digest(token), str(result["order"]["order_id"])
    )
    response = RedirectResponse("/checkout/confirmation", status_code=303)
    set_session_cookie(response, token)
    return response


@app.get("/checkout/confirmation", include_in_schema=False)
async def checkout_confirmation(request: Request) -> Response:
    token = session_token(request)
    receipt = None
    if token:
        try:
            receipt = db.receipt_for(db.auth().session_owner_digest(token))
        except AuthRejected:
            receipt = None
    if receipt is None:
        return RedirectResponse("/pricing/", status_code=303)
    plan = BY_ID.get(str(receipt["plan_id"]))
    rows = "".join(
        f"<tr><th scope=\"row\">{esc(label)}</th><td>{esc(value)}</td></tr>"
        for label, value in (
            ("Order", receipt["order_id"]),
            ("Plan", f"IPVanish {plan.tier}" if plan else receipt["plan_id"]),
            ("Billing period", plan.period if plan else "—"),
            ("Charged today", money(int(receipt["total_minor"]))),
            ("Renews at", money(int(plan.renewal_minor)) if plan else "—"),
            ("Simulated outcome", receipt["scenario_id"]),
        )
    )
    body = (
        '<article class="ipvanish-clone-page">'
        + inference_banner("The post-payment confirmation")
        + "<h1>Your IPVanish subscription is active</h1>"
        + "<p>Thank you. This confirmation and the account area behind it are "
        "clone-local: reaching the source site's own confirmation step requires "
        "charging a real card, which this run is forbidden to do.</p>"
        f'<table class="ipvanish-clone-table"><tbody>{rows}</tbody></table>'
        '<p><a class="ipvanish-clone-cta" href="/account/">Go to My Account</a> '
        '<a href="/pricing/">Back to plans</a></p></article>'
    )
    return HTMLResponse(shell(body))


# --------------------------------------------------------------------------
# auth
# --------------------------------------------------------------------------

SIGNIN_ERROR_SLOT = '<div class="login-form_fields__lxq3I">'
RECOVERY_ERROR_SLOT = '<div class="views_fields__LHxi_">'


def _with_message(document: str, slot: str, message: str, kind: str) -> str:
    return replace_once(
        document,
        slot,
        f'<div class="ipvanish-clone-note ipvanish-clone-note--{kind}" '
        f'role="alert">{esc(message)}</div>{slot}',
    )


def _signin_document(message: str = "", kind: str = "error") -> str:
    document = page("sso-signin")
    document = replace_once(
        document,
        '<form class="login-form_form__TvN3C">',
        '<form class="login-form_form__TvN3C" method="post" action="/login">',
    )
    if message:
        document = _with_message(document, SIGNIN_ERROR_SLOT, message, kind)
    return document


def _recovery_document(message: str = "", kind: str = "error") -> str:
    document = page("sso-recovery")
    document = replace_once(
        document,
        '<form class="views_form__Gddbz">',
        '<form class="views_form__Gddbz" method="post" action="/login/reset-password">',
    )
    if message:
        document = _with_message(document, RECOVERY_ERROR_SLOT, message, kind)
    return document


@app.get("/login", include_in_schema=False)
async def login_view(request: Request) -> Response:
    if current_subject(request) is not None:
        return RedirectResponse("/account/", status_code=303)
    token = ensure_session(request)
    response = HTMLResponse(_signin_document())
    set_session_cookie(response, token)
    return response


@app.post("/login", include_in_schema=False)
async def login_submit(request: Request) -> Response:
    form = dict(await request.form())
    email = str(form.get("email", "")).strip()
    password = str(form.get("password", ""))
    token = ensure_session(request)
    destination = str(form.get("next", "") or request.query_params.get("next", ""))
    if not destination.startswith("/") or destination.startswith("//"):
        destination = "/account/"
    if not email or not password:
        response = HTMLResponse(
            _signin_document("Enter your email address and password."),
            status_code=422,
        )
        set_session_cookie(response, token)
        return response
    try:
        result = db.auth().sign_in(token, email=email, password=password)
    except (AuthRejected, AuthValidationError):
        response = HTMLResponse(
            _signin_document("That email address and password do not match."),
            status_code=422,
        )
        set_session_cookie(response, token)
        return response
    response = RedirectResponse(destination, status_code=303)
    set_session_cookie(response, str(result["session_token"]))
    return response


@app.post("/logout", include_in_schema=False)
async def logout(request: Request) -> Response:
    db.auth().sign_out(session_token(request))
    response = RedirectResponse("/", status_code=303)
    response.delete_cookie(cookie_name(), path="/")
    return response


@app.get("/login/reset-password", include_in_schema=False)
async def recovery_view(request: Request) -> Response:
    token = ensure_session(request)
    response = HTMLResponse(_recovery_document())
    set_session_cookie(response, token)
    return response


@app.post("/login/reset-password", include_in_schema=False)
async def recovery_submit(request: Request) -> Response:
    form = dict(await request.form())
    email = str(form.get("username", "")).strip()
    token = ensure_session(request)
    if not email:
        response = HTMLResponse(
            _recovery_document("Enter you account email."), status_code=422
        )
        set_session_cookie(response, token)
        return response
    message = (
        "If that email belongs to a local account, a reset code is waiting in "
        "this clone's local outbox. No message is ever sent."
    )
    try:
        db.auth().start_password_reset(token, email=email, restart_invalid_flow=True)
    except AuthValidationError:
        response = HTMLResponse(
            _recovery_document("Enter a valid email address."), status_code=422
        )
        set_session_cookie(response, token)
        return response
    except AuthError:
        # Neutral answer: the response must not reveal whether an account exists.
        pass
    response = HTMLResponse(_recovery_document(message, kind="ok"))
    set_session_cookie(response, token)
    return response


# --------------------------------------------------------------------------
# support
# --------------------------------------------------------------------------

SUPPORT_KNOWLEDGE = '<section class="section knowledge-base">'
SUPPORT_FAQ = '<section class="section faq">'


def _support_results(query: str) -> str:
    articles = db.support_articles(query)
    if articles:
        items = "".join(
            f'<li><a href="/support/articles/{esc(row["slug"])}">'
            f'{esc(row["title"])}</a></li>'
            for row in articles
        )
        return (
            '<section class="section faq"><div class="faq-inner">'
            f"<h2>Search results for “{esc(query)}”</h2>"
            f"<ul>{items}</ul></div></section>"
        )
    return (
        '<section class="section faq"><div class="faq-inner">'
        f"<h2>No results for “{esc(query)}”</h2>"
        "<p>Your search did not match any article in this offline clone's "
        "support index.</p><ul>"
        '<li><a href="/pricing/">See IPVanish plans &amp; pricing</a></li>'
        '<li><a href="/support">Back to the Support Center</a></li>'
        "</ul></div></section>"
    )


def _support_document(query: str | None) -> str:
    document = page("support-home")
    if not query:
        return document
    document = drop_element(document, SUPPORT_KNOWLEDGE)
    return replace_element(document, SUPPORT_FAQ, _support_results(query))


@app.get("/support", include_in_schema=False)
async def support(request: Request) -> HTMLResponse:
    query = (request.query_params.get("query") or "").strip() or None
    return HTMLResponse(_support_document(query))


@app.get("/support/search", include_in_schema=False)
async def support_search(request: Request) -> HTMLResponse:
    query = (request.query_params.get("query") or "").strip() or None
    return HTMLResponse(_support_document(query))


@app.get("/support/articles/{slug}", include_in_schema=False)
async def support_article(slug: str) -> HTMLResponse:
    for row in db.support_articles():
        if row["slug"] == slug:
            body = (
                '<section class="section faq"><div class="faq-inner">'
                f'<h2>{esc(row["title"])}</h2><p>{esc(row["body"])}</p>'
                '<p><a href="/support">Back to the Support Center</a></p>'
                "</div></section>"
            )
            document = drop_element(page("support-home"), SUPPORT_KNOWLEDGE)
            return HTMLResponse(replace_element(document, SUPPORT_FAQ, body))
    return not_found()


# --------------------------------------------------------------------------
# subscriber dashboard -- clone-local inference throughout
# --------------------------------------------------------------------------


def _require_subject(request: Request) -> tuple[str | None, Response | None]:
    subject = current_subject(request)
    if subject is None:
        destination = request.url.path
        return None, RedirectResponse(
            f"/login?next={destination}", status_code=303
        )
    return subject, None


def _plan_label(plan_id: str) -> str:
    plan = BY_ID.get(plan_id)
    if plan is None:
        return plan_id
    return f"IPVanish {plan.tier} — {plan.period}"


def _subscription_card(row: dict) -> str:
    status = str(row["status"])
    actions = []
    if status == "active":
        actions.append(("pause", "Pause subscription"))
        actions.append(("cancel", "Cancel subscription"))
    elif status == "paused":
        actions.append(("resume", "Resume subscription"))
        actions.append(("cancel", "Cancel subscription"))
    else:
        actions.append(("reactivate", "Reactivate subscription"))
    buttons = "".join(
        '<form method="post" class="ipvanish-clone-inline" '
        f'action="/account/subscription/{esc(row["subscription_id"])}/{action}">'
        f'<button type="submit" data-clone-action="{action}">{esc(label)}</button>'
        "</form>"
        for action, label in actions
    )
    return (
        f'<section class="ipvanish-clone-card" data-subscription-status="{esc(status)}">'
        f'<h3>{esc(_plan_label(str(row["plan_id"])))}</h3>'
        f'<p class="ipvanish-clone-status">Status: <strong>{esc(status)}</strong></p>'
        f'<p>Started {esc(row["started_on"])} · renews {esc(row["renews_on"])} at '
        f'{esc(money(int(row["renewal_price_minor"])))}</p>'
        + (
            f'<p>Paused on {esc(row["paused_on"])}</p>' if row["paused_on"] else ""
        )
        + (
            f'<p>Canceled on {esc(row["canceled_on"])}</p>'
            if row["canceled_on"]
            else ""
        )
        + f'<div class="ipvanish-clone-actions">{buttons}</div></section>'
    )


def _account_nav(active: str) -> str:
    items = (
        ("/account/", "Overview"),
        ("/account/billing", "Billing history"),
        ("/account/plan", "Change plan"),
        ("/account/billing-contact", "Billing contact"),
    )
    current = ' aria-current="page"'
    links = "".join(
        f'<a href="{esc(href)}"'
        f"{current if href == active else ''}>{esc(label)}</a>"
        for href, label in items
    )
    return f'<nav class="ipvanish-clone-subnav" aria-label="My Account">{links}</nav>'


def _account_page(active: str, heading: str, body: str, notice: str = "") -> str:
    banner = (
        f'<div class="ipvanish-clone-note" role="alert">{esc(notice)}</div>'
        if notice
        else ""
    )
    return shell(
        '<article class="ipvanish-clone-page">'
        + inference_banner("The subscriber account area")
        + _account_nav(active)
        + f"<h1>{esc(heading)}</h1>"
        + banner
        + body
        + '<form method="post" action="/logout" class="ipvanish-clone-inline">'
        '<button type="submit" data-clone-action="sign-out">Sign out</button>'
        "</form></article>"
    )


@app.get("/account/", include_in_schema=False)
async def account_overview(request: Request) -> Response:
    subject, redirect = _require_subject(request)
    if redirect is not None:
        return redirect
    account = db.account_by_subject(subject) or {}
    rows = db.subscriptions_for(subject)
    cards = "".join(_subscription_card(row) for row in rows) or (
        "<p>No subscription is on this account.</p>"
    )
    body = (
        f'<p>Signed in as {esc(account.get("email", ""))}.</p>'
        f"{cards}"
        '<p><a class="ipvanish-clone-cta" href="/account/plan">Change plan</a></p>'
    )
    return HTMLResponse(_account_page("/account/", "My Account", body))


@app.get("/account", include_in_schema=False)
async def account_redirect() -> RedirectResponse:
    return RedirectResponse("/account/", status_code=308)


@app.get("/account/billing", include_in_schema=False)
async def account_billing(request: Request) -> Response:
    subject, redirect = _require_subject(request)
    if redirect is not None:
        return redirect
    orders = db.orders_for(subject)
    rows = "".join(
        "<tr>"
        f'<td>{esc(row["charged_on"])}</td>'
        f'<td>{esc(_plan_label(str(row["plan_id"])))}</td>'
        f'<td>{esc(row["kind"])}</td>'
        f'<td>{esc(money(int(row["amount_minor"])))}</td>'
        f'<td>{esc(money(int(row["tax_minor"])))}</td>'
        f'<td>{esc(money(int(row["total_minor"])))}</td>'
        f'<td>{esc(row["status"])}</td>'
        "</tr>"
        for row in orders
    )
    body = (
        '<table class="ipvanish-clone-table"><thead><tr>'
        "<th>Date</th><th>Plan</th><th>Type</th><th>Amount</th><th>Tax</th>"
        "<th>Total</th><th>Status</th></tr></thead>"
        f"<tbody>{rows}</tbody></table>"
        "<p>Traces asking for a shipping address, a delivery skip or shipment "
        "status have no counterpart on a VPN subscription. The billing address, "
        "the pause action and this billing history are the equivalents this "
        "clone provides; the difference is recorded rather than invented.</p>"
    )
    return HTMLResponse(_account_page("/account/billing", "Billing history", body))


@app.get("/account/plan", include_in_schema=False)
async def account_plan(request: Request) -> Response:
    subject, redirect = _require_subject(request)
    if redirect is not None:
        return redirect
    rows = db.subscriptions_for(subject)
    active = next((row for row in rows if row["status"] != "canceled"), None)
    options = "".join(
        f'<option value="{esc(plan.plan_id)}"'
        f'{" selected" if active and active["plan_id"] == plan.plan_id else ""}>'
        f"IPVanish {esc(plan.tier)} — {esc(plan.period)} — "
        f"{esc(money(plan.charge_minor))} first term, then "
        f"{esc(money(plan.renewal_minor))}</option>"
        for plan in PLANS
    )
    scenarios = "".join(
        f'<label class="ipvanish-sandbox__scenario">'
        f'<input type="radio" name="scenario_id" value="{esc(scenario)}"'
        f'{" checked" if index == 0 else ""}> {esc(label)}</label>'
        for index, (scenario, label) in enumerate(SCENARIOS)
    )
    body = fragment(
        "account-plan-form",
        subscription_id=esc(active["subscription_id"] if active else ""),
        options=options,
        scenarios=scenarios,
    )
    return HTMLResponse(_account_page("/account/plan", "Change plan", body))


@app.post("/account/plan", include_in_schema=False)
async def account_plan_submit(request: Request) -> Response:
    subject, redirect = _require_subject(request)
    if redirect is not None:
        return redirect
    form = dict(await request.form())
    try:
        db.reject_payment_fields(form)
    except db.PaymentFieldRejected as error:
        return JSONResponse(
            {"error": "payment-field-rejected", "detail": str(error)},
            status_code=422,
        )
    plan = plan_for_flow(str(form.get("plan_id", "")))
    scenario_id = str(form.get("scenario_id", "")).strip()
    subscription_id = str(form.get("subscription_id", "")).strip() or None
    if plan is None or scenario_id not in {identifier for identifier, _ in SCENARIOS}:
        return RedirectResponse("/account/plan", status_code=303)
    if subscription_id and db.subscription(subject, subscription_id) is None:
        return RedirectResponse("/account/plan", status_code=303)
    key = "pc" + hashlib.sha256(
        f"{subject}|{plan.plan_id}|{scenario_id}".encode()
    ).hexdigest()[:38]
    try:
        result = db.purchase(
            subject_id=subject,
            plan=plan,
            scenario_id=scenario_id,
            idempotency_key=key,
            kind="plan-change",
            subscription_id=subscription_id,
        )
    except PaymentError as error:
        return HTMLResponse(
            _account_page(
                "/account/plan",
                "Change plan",
                "<p>The plan was not changed.</p>",
                notice=f"The local sandbox refused this attempt: {error}",
            ),
            status_code=422,
        )
    if result["outcome"] != "approved":
        return HTMLResponse(
            _account_page(
                "/account/plan",
                "Change plan",
                "<p>The previous plan is unchanged and no order was written.</p>",
                notice=(
                    f"Simulated {result['outcome']}: the plan change was not "
                    "applied."
                ),
            ),
            status_code=200,
        )
    return RedirectResponse("/account/", status_code=303)


@app.get("/account/billing-contact", include_in_schema=False)
async def account_contact(request: Request) -> Response:
    subject, redirect = _require_subject(request)
    if redirect is not None:
        return redirect
    contact = db.billing_contact(subject) or {}
    countries = "".join(
        f'<option value="{esc(code)}"'
        f'{" selected" if contact.get("country") == code else ""}>'
        f"{esc(label)}</option>"
        for code, label in BILLING_COUNTRIES
    )
    body = fragment(
        "account-billing-contact-form",
        full_name=esc(contact.get("full_name", "")),
        email=esc(contact.get("email", "")),
        countries=countries,
        postal=esc(contact.get("postal_code", "")),
    )
    return HTMLResponse(
        _account_page("/account/billing-contact", "Billing contact", body)
    )


@app.post("/account/billing-contact", include_in_schema=False)
async def account_contact_submit(request: Request) -> Response:
    subject, redirect = _require_subject(request)
    if redirect is not None:
        return redirect
    form = dict(await request.form())
    try:
        db.reject_payment_fields(form)
    except db.PaymentFieldRejected as error:
        return JSONResponse(
            {"error": "payment-field-rejected", "detail": str(error)},
            status_code=422,
        )
    full_name = str(form.get("full_name", "")).strip()
    email = str(form.get("email", "")).strip()
    country = str(form.get("country", "")).strip()
    postal_code = str(form.get("postal_code", "")).strip()
    if not (full_name and email and country and postal_code):
        return HTMLResponse(
            _account_page(
                "/account/billing-contact",
                "Billing contact",
                "<p>Nothing was saved.</p>",
                notice="Every billing contact field is required.",
            ),
            status_code=422,
        )
    db.update_billing_contact(
        subject,
        full_name=full_name,
        email=email,
        country=country,
        postal_code=postal_code,
    )
    return RedirectResponse("/account/billing-contact", status_code=303)


SUBSCRIPTION_ACTIONS = {
    "pause": "paused",
    "resume": "active",
    "cancel": "canceled",
    "reactivate": "active",
}


@app.post("/account/subscription/{subscription_id}/{action}", include_in_schema=False)
async def account_subscription_action(
    request: Request, subscription_id: str, action: str
) -> Response:
    subject, redirect = _require_subject(request)
    if redirect is not None:
        return redirect
    status = SUBSCRIPTION_ACTIONS.get(action)
    if status is None:
        return not_found()
    updated = db.set_subscription_state(subject, subscription_id, status=status)
    if updated is None:
        # Another actor's subscription id is invisible here, not merely refused.
        return not_found()
    return RedirectResponse("/account/", status_code=303)


# --------------------------------------------------------------------------
# local outbox (mail is local-only; codes are never rendered into a body)
# --------------------------------------------------------------------------


@app.get("/api/outbox", include_in_schema=False)
async def outbox(request: Request) -> Response:
    token = session_token(request)
    if not token:
        return JSONResponse({"message": None})
    message = db.auth().local_mail_for_session(token, purpose="password-reset")
    if message is None:
        return JSONResponse({"message": None})
    return JSONResponse(
        {
            "message": {
                "purpose": message["purpose"],
                "recipient": message["recipient"],
                "status": message["status"],
                "verification_code": message["verification_code"],
            }
        }
    )


if __name__ == "__main__":  # pragma: no cover - manual/offline start
    # ACCEPTANCE.md step 3 starts the clone with `python app.py`; the
    # diagnostics and the deployment descriptor use `uvicorn app:app`.
    import uvicorn

    uvicorn.run(
        app,
        host=os.environ.get("HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", "10000")),
        log_level="warning",
    )
