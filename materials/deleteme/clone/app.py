"""The `deleteme` offline clone.

Four boundaries this module keeps, so no route can forget one:

1. **Authentication, mail and payments only through the vendored seam.**
   Nothing here hashes a password, sends a message or moves money on its own.
2. **No card field exists anywhere.**  The source collects card details inside a
   Stripe-hosted iframe; the clone offers a named local sandbox scenario and
   refuses any request carrying card-shaped data.
3. **Every amount is derived server-side** from `backend/catalogue.py`, in
   integer minor units.  The served documents carry price *sentinels*, never
   formatted strings.
4. **Two hosts, one origin.**  The source splits marketing (`joindeleteme.com`),
   the member app (`app.joindeleteme.com`), the help centre and the policy site
   across four hosts.  The clone maps them onto local paths and keeps the two
   different not-found behaviours those hosts genuinely have.

Surfaces marked *clone-local inference* below were never observable on the
source, because DeleteMe issues an account only after a purchase this run may
not make.  Every one of them renders a visible notice saying so:

* the whole `/account` tree - dashboard, removal profile, reports, billing
  history, plan change, pause, cancel, reactivate;
* the password-reset success state and the password-set page;
* the post-purchase confirmation body's clone-local framing;
* the checkout form's *placement* (its field set, labels and validation strings
  are the source's own, read out of the frozen application bundle; the captured
  checkout screen was an expired session, so the layout is the clone's).
"""

from __future__ import annotations

import hashlib
import hmac
import html
import json
import os
import re
import signal
import sys
import urllib.parse
from pathlib import Path
from string import Template

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:  # vendored websitebench + backend imports
    sys.path.insert(0, str(ROOT))

# Writable-state location.  Harbor's ABI passes DATA_DIR; the offline-clone live
# sandbox passes WEBSITEBENCH_DATA_DIR; the vendored runtime keeps the older
# CLAWBENCH_DATA_DIR name.  Reading only the first put a database inside a
# read-only candidate root on an earlier site and failed two sessions, so all
# three are honoured - and this must run before the backend import, because the
# seam binds its database path at open time.
_DATA_DIR = (
    os.environ.get("DATA_DIR")
    or os.environ.get("WEBSITEBENCH_DATA_DIR")
    or os.environ.get("CLAWBENCH_DATA_DIR")
)
if _DATA_DIR and "WEBSITEBENCH_SITE_BACKEND_DATABASE" not in os.environ:
    os.environ["WEBSITEBENCH_SITE_BACKEND_DATABASE"] = str(
        Path(_DATA_DIR).resolve() / "deleteme.sqlite3"
    )

from fastapi import FastAPI, Request  # noqa: E402
from fastapi.responses import (  # noqa: E402
    HTMLResponse,
    JSONResponse,
    RedirectResponse,
    Response,
)
from fastapi.staticfiles import StaticFiles  # noqa: E402

from backend import catalogue, db  # noqa: E402
from htmlslice import insert_after, replace_once  # noqa: E402
from websitebench.local_clone_auth import (  # noqa: E402
    AuthError,
    AuthRejected,
    AuthValidationError,
)

SITE_ID = "deleteme"
PAGES = ROOT / "frontend" / "pages"
FRAGMENTS = ROOT / "frontend" / "fragments"
STATIC_DIR = ROOT / "static"
EXTERNAL_LINKS: dict[str, str] = json.loads(
    (ROOT / "frontend" / "external-links.json").read_text(encoding="utf-8")
)
ADMIN_TOKEN = os.environ.get("WEBSITEBENCH_DELETEME_ADMIN_TOKEN", "deleteme-local-admin")
BUILD_ID = os.environ.get("DEPLOYMENT_BUILD_ID") or os.environ.get(
    "WEBSITEBENCH_BUILD_ID"
)
CONTENT_SECURITY_POLICY = (
    "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
    "font-src 'self'; script-src 'self'; frame-src 'self'; frame-ancestors 'self'; "
    "form-action 'self'; base-uri 'none'; connect-src 'self'"
)
_HEALTH_BODY = json.dumps({"ok": True, "site_id": SITE_ID}, separators=(",", ":"))
MAIN_SENTINEL = "<!--deleteme-clone-main-->"
CAPTURED_SEARCH_TERM = "zzzz-no-match-websitebench"

app = FastAPI(
    title="DeleteMe offline clone",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)


# ---------------------------------------------------------------------------
# documents
# ---------------------------------------------------------------------------

_PRICE_SENTINEL = re.compile(r"<!--wb:price:([A-Za-z0-9]+)\.([a-z-]+)-->")
_page_cache: dict[str, str] = {}
_fragment_cache: dict[str, Template] = {}


def _fill_prices(document: str) -> str:
    """Resolve every build-time price sentinel from the plan catalogue.

    This is the only place a price becomes a string.  A sentinel naming a plan
    or a field the catalogue does not have is a hard error, not a blank: a
    silently empty price is exactly the defect a diff would miss.
    """

    return _PRICE_SENTINEL.sub(
        lambda match: html.escape(catalogue.field_value(match.group(1), match.group(2))),
        document,
    )


def page(name: str) -> str:
    cached = _page_cache.get(name)
    if cached is None:
        cached = _fill_prices((PAGES / f"{name}.html").read_text(encoding="utf-8"))
        _page_cache[name] = cached
    return cached


def fragment(name: str, **values: str) -> str:
    template = _fragment_cache.get(name)
    if template is None:
        template = Template((FRAGMENTS / f"{name}.html").read_text(encoding="utf-8"))
        _fragment_cache[name] = template
    return template.substitute(**values)


def app_shell(main_html: str, *, title: str) -> str:
    """Render a clone-local application-host page inside the captured chrome."""

    document = page("_app-shell").replace(MAIN_SENTINEL, main_html, 1)
    return re.sub(
        r"<title>.*?</title>", f"<title>{html.escape(title)}</title>", document, count=1
    )


def esc(value: object) -> str:
    return html.escape(str(value), quote=True)


CLONE_NOTE_TEMPLATE = (
    '<div class="dm-clone-note" role="note" data-clone-local="{kind}">'
    "<strong>Clone-local surface.</strong> {body}</div>"
)


def inference_notice(what: str) -> str:
    """The standard disclosure for a surface nobody could observe.

    Recording inferred evidence as observed is an unconditional rejection, so
    every such page says plainly which part of it is inference.
    """

    return CLONE_NOTE_TEMPLATE.format(
        kind="inferred",
        body=(
            f"{html.escape(what)} was never observable on the source: DeleteMe issues "
            "an account only after a purchase this capture run was not permitted to "
            "make. What you see here is offline-clone inference, not a reproduction "
            "of a captured screen."
        ),
    )


def sandbox_notice() -> str:
    return CLONE_NOTE_TEMPLATE.format(
        kind="sandbox",
        body=(
            "Payment here is a local simulation. The source collects card details "
            "inside a Stripe-hosted iframe; this clone reproduces no card field at "
            "all and takes no card data of any kind. Choose a named sandbox outcome "
            "below. The field set, labels and validation wording are the source's "
            "own, read from its published application bundle; their placement is "
            "this clone's, because the captured checkout screen was an expired "
            "session rather than a live form."
        ),
    )


def message(kind: str, body: str) -> str:
    return (
        f'<div class="dm-clone-note dm-clone-note--{kind}" role="alert">'
        f"{html.escape(body)}</div>"
    )


# ---------------------------------------------------------------------------
# sessions
# ---------------------------------------------------------------------------


def cookie_name() -> str:
    return db.backend().config.cookie_name


def set_session_cookie(response: Response, token: str) -> None:
    facts = db.backend().session_cookie
    response.set_cookie(
        facts["name"],
        token,
        secure=bool(facts.get("secure", True)),
        httponly=bool(facts.get("httponly", True)),
        samesite=str(facts.get("samesite", "Lax")).lower(),
        path=str(facts.get("path", "/")),
    )


def session_token(request: Request) -> str | None:
    return request.cookies.get(cookie_name())


def ensure_session(request: Request) -> str:
    token, _ = db.auth().ensure_session(session_token(request))
    return token


def current_account(request: Request) -> dict[str, object] | None:
    token = session_token(request)
    if not token:
        return None
    resolved = db.auth().resolve_session(token)
    if not resolved:
        return None
    account = resolved.get("account")
    return account or None


def current_subject(request: Request) -> str | None:
    account = current_account(request)
    return str(account["subject_id"]) if account else None


# ---------------------------------------------------------------------------
# infrastructure
# ---------------------------------------------------------------------------


class _MirrorStaticFiles(StaticFiles):
    """Retry percent-encoded on-disk names; the mirror keeps source encoding."""

    def lookup_path(self, path: str):  # type: ignore[override]
        full_path, stat_result = super().lookup_path(path)
        if stat_result is not None:
            return full_path, stat_result
        requoted = "/".join(
            urllib.parse.quote(segment) for segment in path.split("/")
        )
        if requoted != path:
            return super().lookup_path(requoted)
        return full_path, stat_result


app.mount("/static", _MirrorStaticFiles(directory=str(STATIC_DIR)), name="static")


@app.middleware("http")
async def runtime_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("Content-Security-Policy", CONTENT_SECURITY_POLICY)
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    if BUILD_ID:
        response.headers.setdefault("X-WebsiteBench-Build-Id", BUILD_ID)
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
    _page_cache.clear()
    return JSONResponse({"reset": True, "site_id": SITE_ID})


@app.get("/api/outbox", include_in_schema=False)
async def outbox(request: Request) -> Response:
    """Whatever mail this clone produced, and where it stopped: here."""

    token = session_token(request)
    if not token:
        return JSONResponse({"messages": []})
    messages = []
    for purpose in ("password-reset", "registration"):
        found = db.auth().local_mail_for_session(token, purpose=purpose)
        if found:
            messages.append(
                {
                    "purpose": found["purpose"],
                    "recipient": found["recipient"],
                    "template": found["template"],
                    "status": found["status"],
                    "delivery": "local-outbox-only",
                }
            )
    return JSONResponse({"messages": messages})


# ---------------------------------------------------------------------------
# marketing tree
# ---------------------------------------------------------------------------

MARKETING_ROUTES: dict[str, str] = {
    "/privacy-protection-plans/": "plans",
    "/pricing/": "pricing",
    "/signup/": "signup-grid",
    "/scan/": "scan",
    "/how-we-work/": "how-we-work",
    "/sites-we-remove-from/": "sites-we-remove-from",
    "/reviews/": "reviews",
    "/about-us/": "about",
    "/security/": "security",
    "/international/": "international",
    "/how-public-record-information-works/": "how-public-record",
    "/blog/": "blog",
    "/blog/opt-out-guides/": "opt-out-guides",
    "/delete-your-account/": "delete-your-account",
    "/doxxing/": "doxxing",
    "/is-site-safe/": "is-site-safe",
    "/is-it-scam/": "is-it-scam",
    "/glossary/": "glossary",
    "/do-not-call-list/": "do-not-call-list",
    "/ai-privacy-settings/": "ai-privacy-settings",
    "/data-breaches/": "data-breaches",
    "/podcast/": "podcast",
    "/permission-slip/": "permission-slip",
    "/permission-slip/faq/": "permission-slip-faq",
    "/press/": "press",
    "/careers/": "careers",
}


def _register_marketing(route: str, name: str) -> None:
    @app.get(route, include_in_schema=False)
    async def marketing_page(_name: str = name) -> HTMLResponse:
        return HTMLResponse(page(_name))

    @app.get(route.rstrip("/"), include_in_schema=False)
    async def marketing_redirect(_route: str = route) -> RedirectResponse:
        # The source 301s an extensionless path to its trailing-slash form.
        return RedirectResponse(_route, status_code=301)


for _route, _name in MARKETING_ROUTES.items():
    _register_marketing(_route, _name)


def _search_document(term: str) -> str:
    """The captured search page with the query echoed where the source echoes it.

    The source shows **no** no-results message: heading `Search`, an H2 echoing
    the term in curly quotes, and an empty region.  This clone indexes nothing,
    so every query renders that same empty region.  The populated `results`
    state was never captured, and inventing either the results layout or a
    "no results found" string would be the cleanest possible way to fail this
    build dishonestly.
    """

    document = page("search")
    safe = html.escape(term, quote=True)
    return document.replace(CAPTURED_SEARCH_TERM, safe)


@app.get("/", include_in_schema=False)
async def home(request: Request) -> HTMLResponse:
    term = request.query_params.get("s")
    if term is not None:
        return HTMLResponse(_search_document(term))
    return HTMLResponse(page("home"))


@app.get("/help", include_in_schema=False)
async def help_centre() -> HTMLResponse:
    return HTMLResponse(page("help"))


@app.get("/policies", include_in_schema=False)
async def policies() -> HTMLResponse:
    return HTMLResponse(page("policies"))


@app.get("/external/{slug}", include_in_schema=False)
async def external_boundary(slug: str) -> HTMLResponse:
    target = EXTERNAL_LINKS.get(slug)
    if target is None:
        return not_found()
    body = (
        '<div class="dm-clone-standalone"><h1>This link leaves the captured site</h1>'
        + CLONE_NOTE_TEMPLATE.format(
            kind="external",
            body=(
                "The source links this destination on another origin. An offline "
                "clone never requests one, so the link stops here and the target is "
                "recorded instead of fetched."
            ),
        )
        + f"<p class=\"dm-clone-target\"><code>{esc(target)}</code></p>"
        '<p><a href="/">Go to the homepage</a></p></div>'
    )
    return HTMLResponse(_standalone(body, title="External link"))


@app.get("/embed/{slug}", include_in_schema=False)
async def embed_boundary(slug: str) -> HTMLResponse:
    target = EXTERNAL_LINKS.get(slug)
    if target is None:
        return not_found()
    body = (
        '<div class="dm-clone-embed"><p class="dm-clone-embed__title">'
        "Third-party frame not loaded</p>"
        f'<p class="dm-clone-embed__host"><code>{esc(target)}</code></p></div>'
    )
    return HTMLResponse(_standalone(body, title="Embedded frame", embed=True))


def _standalone(body: str, *, title: str, embed: bool = False) -> str:
    klass = "dm-clone-embed-body" if embed else "dm-clone-standalone-body"
    return (
        "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{esc(title)} | DeleteMe</title>"
        '<link rel="stylesheet" href="/static/site/clone.css">'
        f'</head><body class="{klass}">{body}</body></html>'
    )


# ---------------------------------------------------------------------------
# not found - two hosts, two behaviours, deliberately not normalised
# ---------------------------------------------------------------------------


def not_found() -> HTMLResponse:
    """The marketing host: a real 404 with full chrome."""

    return HTMLResponse(page("not-found"), status_code=404)


def app_not_found() -> HTMLResponse:
    """The application host: HTTP 200 with a client-rendered `Page not found`."""

    return HTMLResponse(page("app-not-found"), status_code=200)


@app.exception_handler(404)
async def not_found_handler(request: Request, exc: Exception) -> Response:
    path = request.url.path
    if path.startswith(("/api/", "/__websitebench/", "/__admin/")):
        return JSONResponse({"error": "not-found"}, status_code=404)
    if path.startswith("/account"):
        return app_not_found()
    if path.startswith("/static/"):
        return Response("not found", status_code=404, media_type="text/plain")
    # An unknown *extensionless* marketing path 301s to the trailing-slash form
    # first, exactly as the source does, and only then answers 404.
    if not path.endswith("/") and "." not in path.rsplit("/", 1)[-1]:
        query = f"?{request.url.query}" if request.url.query else ""
        return RedirectResponse(f"{path}/{query}", status_code=301)
    return not_found()


# ---------------------------------------------------------------------------
# checkout
# ---------------------------------------------------------------------------

def sandbox_scenarios() -> list[dict[str, str]]:
    """The named outcomes, straight from `backend/runtime.json`.

    There is no other payment input in this clone, and no other adapter: the
    runtime contract names `local-sandbox` and nothing else is wired.
    """

    payments = db.backend().config.payments
    adapter = payments["default_adapter"]
    if adapter != "local-sandbox":
        raise RuntimeError(f"unexpected payment adapter in runtime.json: {adapter}")
    return [dict(scenario) for scenario in payments["local_sandbox"]["scenarios"]]


DEFAULT_TERM = 2  # the grid ships every 1-Year group display:none
DEFAULT_QTY = 1


def _selection(params) -> tuple[catalogue.Plan, bool]:
    def _int(name: str, fallback: int) -> int:
        raw = params.get(name)
        try:
            return int(str(raw))
        except (TypeError, ValueError):
            return fallback

    term = _int("term", DEFAULT_TERM)
    qty = _int("qty", DEFAULT_QTY)
    plan = catalogue.plan_for(term, qty)
    if plan is None:
        return catalogue.plan_for(DEFAULT_TERM, DEFAULT_QTY), True  # type: ignore[return-value]
    return plan, False


def _checkout_body(
    plan: catalogue.Plan,
    *,
    values: dict[str, str] | None = None,
    errors: list[str] | None = None,
    notice: str = "",
    scenario: str = "sandbox-approved",
    agreements: tuple[bool, bool] = (False, False),
) -> str:
    values = values or {}
    errors = errors or []
    scenario_html = "".join(
        '<label class="dm-sandbox__scenario">'
        f'<input type="radio" name="scenario" value="{esc(item["id"])}"'
        f'{" checked" if item["id"] == scenario else ""}>'
        f'<span>{esc(item["display_label"])}</span>'
        f'<code>{esc(item["id"])}</code></label>'
        for item in sandbox_scenarios()
    )
    error_html = ""
    if errors:
        error_html = (
            '<div class="dm-checkout__errors" role="alert" data-checkout-errors>'
            "<p>Please review and accept the following to continue</p><ul>"
            + "".join(f"<li>{esc(item)}</li>" for item in errors)
            + "</ul></div>"
        )
    includes = "".join(
        f"<li>{esc(item)}</li>"
        for item in (
            "Quarterly privacy reports",
            "A+ BBB rating",
            "Email, chat, and phone support",
            "Custom removal requests",
            "100% satisfaction guarantee",
            "Continuous data removal",
        )
    )
    return fragment(
        "checkout-form",
        notice=sandbox_notice() + notice + error_html,
        term=str(plan.term_years),
        qty=str(plan.quantity),
        plan_summary=esc(plan.summary_line),
        plan_total=esc(plan.total_display),
        plan_monthly=esc(plan.monthly_display),
        plan_key=esc(plan.key),
        includes=includes,
        scenarios=scenario_html,
        first_name=esc(values.get("firstName", "")),
        last_name=esc(values.get("lastName", "")),
        email=esc(values.get("email", "")),
        address=esc(values.get("address", "")),
        source=esc(values.get("selfReportedSource", "")),
        billing_checked=" checked" if agreements[0] else "",
        terms_checked=" checked" if agreements[1] else "",
    )


@app.get("/checkout", include_in_schema=False)
async def checkout(request: Request) -> HTMLResponse:
    plan, clamped = _selection(request.query_params)
    notice = ""
    if clamped and (
        "term" in request.query_params or "qty" in request.query_params
    ):
        notice = message(
            "info",
            "That plan selection is not one the grid offers, so the checkout fell "
            "back to the default: two years for one person.",
        )
    response = HTMLResponse(
        app_shell(_checkout_body(plan, notice=notice), title="Checkout | DeleteMe")
    )
    set_session_cookie(response, ensure_session(request))
    return response


@app.post("/checkout", include_in_schema=False)
async def checkout_submit(request: Request) -> Response:
    form = dict(await request.form())
    try:
        db.reject_payment_fields(form)
    except db.PaymentFieldRejected as error:
        return JSONResponse(
            {"error": "payment-field-rejected", "detail": str(error)}, status_code=422
        )
    try:
        db.reject_removal_pii(form)
    except db.RemovalPiiRejected as error:
        return JSONResponse(
            {"error": "removal-pii-rejected", "detail": str(error)}, status_code=422
        )

    plan, _ = _selection(form)
    values = {name: str(form.get(name, "")).strip() for name in db.CHECKOUT_FIELDS}
    values["selfReportedSource"] = str(form.get("selfReportedSource", "")).strip()
    billing = str(form.get("agree_billing", "")) not in ("", "off", "false")
    terms = str(form.get("agree_terms", "")) not in ("", "off", "false")
    scenario = str(form.get("scenario", "sandbox-approved"))
    known = {item["id"] for item in sandbox_scenarios()}
    if scenario not in known:
        return JSONResponse(
            {"error": "unknown-scenario", "detail": scenario}, status_code=422
        )

    # The wording is the source's own, from its published checkout bundle.
    errors: list[str] = []
    if not values["firstName"]:
        errors.append("Please enter your first name")
    if not values["lastName"]:
        errors.append("Please enter your last name")
    if not values["email"]:
        errors.append("Please enter your email address")
    elif not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", values["email"]):
        errors.append("Please enter your email address")
    if not values["address"]:
        errors.append("Please enter your address")
    if not (billing and terms):
        errors.append("Please accept the terms and conditions")
    if errors:
        return HTMLResponse(
            app_shell(
                _checkout_body(
                    plan,
                    values=values,
                    errors=errors,
                    scenario=scenario,
                    agreements=(billing, terms),
                ),
                title="Checkout | DeleteMe",
            ),
            status_code=422,
        )

    token = ensure_session(request)
    subject = db.ensure_checkout_subject(values["email"])
    digest = db.auth().session_owner_digest(token)
    attempt = str(form.get("attempt", "1"))
    key = "ck" + hashlib.sha256(
        f"{digest}|{plan.key}|{scenario}|{attempt}|{values['email']}".encode()
    ).hexdigest()[:38]
    result = db.purchase(
        subject_id=subject,
        plan=plan,
        scenario_id=scenario,
        idempotency_key=key,
        contact=values,
    )
    if result["outcome"] != "approved":
        outcome = str(result["outcome"])
        copy = {
            "declined": "Your bank declined this card. Try a different card, or "
            "contact your bank — they can tell you why.",
            "retryable": "Something went wrong processing your payment. "
            "Please try again in a moment.",
        }.get(outcome, "Something went wrong processing your payment.")
        return HTMLResponse(
            app_shell(
                _checkout_body(
                    plan,
                    values=values,
                    notice=message("error", copy),
                    scenario=scenario,
                    agreements=(billing, terms),
                ),
                title="Checkout | DeleteMe",
            ),
            status_code=402,
        )

    db.record_receipt(
        session_digest=digest,
        subject_id=subject,
        order_id=str(result["order"]["order_id"]),
        plan_key=plan.key,
    )
    response = RedirectResponse("/checkout/complete", status_code=303)
    set_session_cookie(response, token)
    return response


@app.get("/checkout/complete", include_in_schema=False)
async def checkout_complete(request: Request) -> HTMLResponse:
    """The captured confirmation, with the clone-local framing it needs.

    The source's own confirmation copy is reproduced verbatim from the capture.
    What is *not* observed - and is disclosed - is everything the email it
    promises would do, because no account was ever created on the source.
    """

    document = page("checkout-complete")
    token = session_token(request)
    receipt = None
    if token:
        receipt = db.receipt_for(db.auth().session_owner_digest(token))
    detail = ""
    if receipt is not None:
        plan = catalogue.BY_KEY.get(str(receipt["plan_key"]))
        if plan is not None:
            detail = (
                '<p class="dm-clone-receipt">'
                f"Local sandbox order <code>{esc(receipt['order_id'])}</code> — "
                f"{esc(plan.summary_line)} {esc(plan.disclaimer)}</p>"
            )
    notice = (
        inference_notice("The account this confirmation promises")
        + CLONE_NOTE_TEMPLATE.format(
            kind="sandbox",
            body=(
                "No payment was taken and no message left this machine: the purchase "
                "ran against the local sandbox and any mail stays in the clone's own "
                "outbox."
            ),
        )
        + detail
    )
    document = insert_after(
        document, '<div class="MuiBox-root css-1wkjpkc">', notice
    )
    return HTMLResponse(document)


# ---------------------------------------------------------------------------
# authentication
# ---------------------------------------------------------------------------


def _login_document(*, notice: str = "", email: str = "") -> str:
    document = page("login")
    document = replace_once(
        document, "<form>", '<form method="post" action="/login" data-login-form>'
    )
    if email:
        document = document.replace(
            'autocomplete="email" id="«r1»" required=""',
            f'autocomplete="email" id="«r1»" required="" name="email" '
            f'value="{esc(email)}"',
            1,
        )
    else:
        document = document.replace(
            'autocomplete="email" id="«r1»" required=""',
            'autocomplete="email" id="«r1»" required="" name="email"',
            1,
        )
    document = document.replace(
        'autocomplete="current-password" id="«r2»" required=""',
        'autocomplete="current-password" id="«r2»" required="" name="password"',
        1,
    )
    if notice:
        document = replace_once(
            document,
            '<form method="post" action="/login" data-login-form>',
            f'<form method="post" action="/login" data-login-form>{notice}',
        )
    return document


@app.get("/login", include_in_schema=False)
async def login(request: Request) -> HTMLResponse:
    response = HTMLResponse(_login_document())
    set_session_cookie(response, ensure_session(request))
    return response


@app.post("/login", include_in_schema=False)
async def login_submit(request: Request) -> Response:
    form = dict(await request.form())
    try:
        db.reject_payment_fields(form)
    except db.PaymentFieldRejected as error:
        return JSONResponse(
            {"error": "payment-field-rejected", "detail": str(error)}, status_code=422
        )
    email = str(form.get("email", "")).strip()
    password = str(form.get("password", ""))
    token = ensure_session(request)
    if not email or not password:
        response = HTMLResponse(
            _login_document(
                notice=message("error", "Enter your email address and password."),
                email=email,
            ),
            status_code=422,
        )
        set_session_cookie(response, token)
        return response
    try:
        result = db.auth().sign_in(token, email=email, password=password)
    except (AuthRejected, AuthValidationError, AuthError):
        # Deliberately identical for an unknown address and a wrong password.
        response = HTMLResponse(
            _login_document(
                notice=message("error", "That email address and password do not match."),
                email=email,
            ),
            status_code=401,
        )
        set_session_cookie(response, token)
        return response
    response = RedirectResponse("/account", status_code=303)
    set_session_cookie(response, str(result["session_token"]))
    return response


@app.post("/logout", include_in_schema=False)
async def logout(request: Request) -> Response:
    token = session_token(request)
    if token:
        db.auth().sign_out(token)
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie(cookie_name(), path="/")
    return response


def _forgot_document(*, notice: str = "") -> str:
    document = page("password-forgot")
    document = replace_once(
        document,
        '<form class="MuiBox-root css-164r41r">',
        '<form class="MuiBox-root css-164r41r" method="post" action="/password/forgot"'
        " data-forgot-form>",
    )
    if notice:
        document = document.replace(
            '<form class="MuiBox-root css-164r41r" method="post" '
            'action="/password/forgot" data-forgot-form>',
            '<form class="MuiBox-root css-164r41r" method="post" '
            f'action="/password/forgot" data-forgot-form>{notice}',
            1,
        )
    return document


@app.get("/password/forgot", include_in_schema=False)
async def password_forgot(request: Request) -> HTMLResponse:
    response = HTMLResponse(_forgot_document())
    set_session_cookie(response, ensure_session(request))
    return response


@app.post("/password/forgot", include_in_schema=False)
async def password_forgot_submit(request: Request) -> Response:
    form = dict(await request.form())
    email = str(form.get("email", "")).strip()
    token = ensure_session(request)
    if not email or "@" not in email:
        response = HTMLResponse(
            _forgot_document(
                notice=message("error", "Enter the email address on your account.")
            ),
            status_code=422,
        )
        set_session_cookie(response, token)
        return response
    try:
        db.auth().start_password_reset(token, email=email, restart_invalid_flow=True)
    except AuthError:
        pass  # neutrality: the surface must not reveal whether the address exists
    body = (
        '<div class="dm-app-panel"><h1>Check your email</h1>'
        + inference_notice("The password-reset success state")
        + CLONE_NOTE_TEMPLATE.format(
            kind="mail",
            body=(
                "Nothing was sent. This clone writes to a local outbox only, and no "
                "message ever leaves the machine."
            ),
        )
        + "<p>If an account uses that address, a reset link is on its way.</p>"
        '<p><a href="/login">Back to sign in</a></p>'
        '<p><a href="/password/set">Open the clone-local password-set page</a></p>'
        "</div>"
    )
    response = HTMLResponse(app_shell(body, title="Reset your password | DeleteMe"))
    set_session_cookie(response, token)
    return response


@app.get("/password/set", include_in_schema=False)
async def password_set() -> HTMLResponse:
    body = (
        '<div class="dm-app-panel"><h1>Set your password</h1>'
        + inference_notice("The password-set page")
        + "<p>On the source this page is reached from an emailed link after a "
        "purchase. No purchase was made and no message was sent, so nothing here "
        "was observed: the field below is the clone's own.</p>"
        '<form method="post" action="/password/set" class="dm-app-form">'
        '<label for="dm-new-password">New password</label>'
        '<input id="dm-new-password" name="password" type="password" '
        'autocomplete="new-password" required>'
        '<button type="submit">Set password</button></form>'
        '<p><a href="/login">Back to sign in</a></p></div>'
    )
    return HTMLResponse(app_shell(body, title="Set your password | DeleteMe"))


@app.post("/password/set", include_in_schema=False)
async def password_set_submit(request: Request) -> Response:
    form = dict(await request.form())
    try:
        db.reject_payment_fields(form)
    except db.PaymentFieldRejected as error:
        return JSONResponse(
            {"error": "payment-field-rejected", "detail": str(error)}, status_code=422
        )
    body = (
        '<div class="dm-app-panel"><h1>Set your password</h1>'
        + inference_notice("The password-set page")
        + message(
            "info",
            "This clone-local page accepts nothing: the reset flow it belongs to "
            "was never observable on the source, so no credential is stored here.",
        )
        + '<p><a href="/login">Back to sign in</a></p></div>'
    )
    return HTMLResponse(
        app_shell(body, title="Set your password | DeleteMe"), status_code=422
    )


# ---------------------------------------------------------------------------
# subscriber surfaces - clone-local inference, every one of them
# ---------------------------------------------------------------------------

ACCOUNT_NAV = (
    ("/account", "Dashboard"),
    ("/account/profile", "Removal profile"),
    ("/account/reports", "Removal reports"),
    ("/account/billing", "Billing history"),
    ("/account/plan", "Plan and cadence"),
)


def _account_page(
    request: Request, title: str, body: str, *, what: str, status: int = 200
) -> Response:
    subject = current_subject(request)
    if subject is None:
        return RedirectResponse("/login", status_code=303)
    nav = "".join(
        f'<a href="{esc(href)}"{" aria-current=\"page\"" if href == request.url.path else ""}>'
        f"{esc(label)}</a>"
        for href, label in ACCOUNT_NAV
    )
    account = current_account(request) or {}
    document = app_shell(
        '<div class="dm-account">'
        f'<nav class="dm-account__nav" aria-label="Account">{nav}'
        '<form method="post" action="/logout" class="dm-account__logout">'
        '<button type="submit">Sign out</button></form></nav>'
        f'<main class="dm-account__main"><h1>{esc(title)}</h1>'
        + inference_notice(what)
        + f'<p class="dm-account__who">Signed in as '
        f"{esc(account.get('display_name', ''))} "
        # the vendored auth store names the column `email_normalized`
        f"&lt;{esc(account.get('email_normalized') or account.get('email', ''))}&gt;</p>"
        + body
        + "</main></div>",
        title=f"{title} | DeleteMe",
    )
    return HTMLResponse(document, status_code=status)


def _table(headers: tuple[str, ...], rows: list[tuple[str, ...]]) -> str:
    head = "".join(f"<th scope=\"col\">{esc(item)}</th>" for item in headers)
    body = "".join(
        "<tr>" + "".join(f"<td>{esc(cell)}</td>" for cell in row) + "</tr>"
        for row in rows
    )
    if not rows:
        return '<p class="dm-account__empty">Nothing recorded yet.</p>'
    return f'<table class="dm-account__table"><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>'


@app.get("/account", include_in_schema=False)
async def account_dashboard(request: Request) -> Response:
    subject = current_subject(request)
    if subject is None:
        return RedirectResponse("/login", status_code=303)
    records = db.removal_records(subject)
    subscriptions = db.subscriptions(subject)
    cards = []
    for row in subscriptions:
        plan = catalogue.BY_KEY.get(str(row["plan_key"]))
        cards.append(
            '<article class="dm-account__card" data-subscription="'
            f'{esc(row["subscription_id"])}">'
            f"<h2>{esc(plan.years_label if plan else row['plan_key'])}</h2>"
            f'<p class="dm-account__status" data-status>{esc(row["status"])}</p>'
            f"<p>{esc(plan.disclaimer if plan else '')}</p>"
            f"<p>Renews {esc(row['renews_on'])}.</p>"
            + fragment(
                "subscription-actions", subscription_id=esc(row["subscription_id"])
            )
            + "</article>"
        )
    body = (
        "".join(cards)
        + "<h2>Removal activity</h2>"
        + _table(
            ("Data broker", "Status", "Requested", "Completed"),
            [
                (
                    str(row["broker"]),
                    str(row["status"]),
                    str(row["requested_on"]),
                    str(row["completed_on"]) or "—",
                )
                for row in records
            ],
        )
    )
    return _account_page(
        request,
        "Dashboard",
        body,
        what="The subscriber dashboard, and the removal activity it lists,",
    )


@app.get("/account/profile", include_in_schema=False)
async def account_profile(request: Request) -> Response:
    subject = current_subject(request)
    if subject is None:
        return RedirectResponse("/login", status_code=303)
    stored = db.removal_profile(subject) or {}
    contact = db.profile(subject) or {}
    body = (
        CLONE_NOTE_TEMPLATE.format(
            kind="pii",
            body=(
                "This is the only surface in the clone that asks for age, telephone, "
                "previous names, aliases or relatives. On the source those questions "
                "live here too - after a purchase - and never at checkout. Enter "
                "nothing real: this clone stores whatever it is given in a local "
                "SQLite file and contacts no data broker, ever."
            ),
        )
        + f'<p class="dm-account__contact">Billing identity: '
        f"{esc(contact.get('first_name', ''))} {esc(contact.get('last_name', ''))}, "
        f"{esc(contact.get('address', ''))}</p>"
        + fragment(
            "removal-profile-form",
            birth_year=esc(stored.get("birth_year", "")),
            phone=esc(stored.get("phone", "")),
            previous_names=esc(stored.get("previous_names", "")),
            aliases=esc(stored.get("aliases", "")),
            relatives=esc(stored.get("relatives", "")),
            other_addresses=esc(stored.get("other_addresses", "")),
        )
    )
    return _account_page(
        request, "Removal profile", body, what="The removal profile"
    )


@app.post("/account/profile", include_in_schema=False)
async def account_profile_submit(request: Request) -> Response:
    # The payment boundary is checked before the authorization one: card data
    # must be refused whoever sends it, and a redirect to sign-in would be a
    # quieter answer than this request deserves.
    form = dict(await request.form())
    try:
        db.reject_payment_fields(form)
    except db.PaymentFieldRejected as error:
        return JSONResponse(
            {"error": "payment-field-rejected", "detail": str(error)}, status_code=422
        )
    subject = current_subject(request)
    if subject is None:
        return RedirectResponse("/login", status_code=303)
    db.save_removal_profile(
        subject, {name: str(value) for name, value in form.items()}
    )
    return RedirectResponse("/account/profile", status_code=303)


@app.get("/account/reports", include_in_schema=False)
async def account_reports(request: Request) -> Response:
    subject = current_subject(request)
    if subject is None:
        return RedirectResponse("/login", status_code=303)
    rows = db.reports(subject)
    body = _table(
        ("Period", "Issued", "Listings found", "Listings removed"),
        [
            (
                str(row["period"]),
                str(row["issued_on"]),
                str(row["listings_found"]),
                str(row["listings_removed"]),
            )
            for row in rows
        ],
    )
    return _account_page(request, "Removal reports", body, what="Removal reports")


@app.get("/account/billing", include_in_schema=False)
async def account_billing(request: Request) -> Response:
    subject = current_subject(request)
    if subject is None:
        return RedirectResponse("/login", status_code=303)
    rows = db.billing_events(subject)
    body = _table(
        ("Date", "Description", "Amount"),
        [
            (
                str(row["occurred_on"]),
                str(row["description"]),
                catalogue.money(int(row["amount_minor"])),
            )
            for row in rows
        ],
    )
    return _account_page(request, "Billing history", body, what="Billing history")


@app.get("/account/plan", include_in_schema=False)
async def account_plan(request: Request) -> Response:
    subject = current_subject(request)
    if subject is None:
        return RedirectResponse("/login", status_code=303)
    rows = db.subscriptions(subject)
    if not rows:
        return _account_page(
            request, "Plan and cadence", "<p>No subscription.</p>", what="Plan changes"
        )
    current = rows[0]
    options = "".join(
        f'<option value="{plan.term_years}-{plan.quantity}"'
        f'{" selected" if plan.key == current["plan_key"] else ""}>'
        f"{esc(plan.years_label)} — {esc(plan.total_display)} "
        f"({esc(plan.monthly_display)}/mo)</option>"
        for plan in catalogue.PLANS
    )
    body = fragment(
        "plan-change-form",
        subscription_id=esc(current["subscription_id"]),
        options=options,
    )
    return _account_page(request, "Plan and cadence", body, what="Plan changes")


@app.post("/account/plan", include_in_schema=False)
async def account_plan_submit(request: Request) -> Response:
    form = dict(await request.form())
    try:
        db.reject_payment_fields(form)
    except db.PaymentFieldRejected as error:
        return JSONResponse(
            {"error": "payment-field-rejected", "detail": str(error)}, status_code=422
        )
    subject = current_subject(request)
    if subject is None:
        return RedirectResponse("/login", status_code=303)
    subscription_id = str(form.get("subscription_id", ""))
    if db.subscription(subject, subscription_id) is None:
        return app_not_found()
    raw = str(form.get("selection", ""))
    try:
        term, qty = (int(part) for part in raw.split("-", 1))
    except ValueError:
        return JSONResponse({"error": "unknown-selection"}, status_code=422)
    plan = catalogue.plan_for(term, qty)
    if plan is None:
        return JSONResponse({"error": "unknown-selection"}, status_code=422)
    db.change_plan(subject, subscription_id, plan=plan)
    return RedirectResponse("/account/plan", status_code=303)


SUBSCRIPTION_ACTIONS = {
    "pause": "paused",
    "cancel": "cancelled",
    "reactivate": "active",
}


@app.post("/account/subscription/{subscription_id}/{action}", include_in_schema=False)
async def subscription_action(
    request: Request, subscription_id: str, action: str
) -> Response:
    subject = current_subject(request)
    if subject is None:
        return RedirectResponse("/login", status_code=303)
    status = SUBSCRIPTION_ACTIONS.get(action)
    if status is None or db.subscription(subject, subscription_id) is None:
        return app_not_found()
    db.set_subscription_state(subject, subscription_id, status=status)
    return RedirectResponse("/account", status_code=303)


@app.get("/account/{rest:path}", include_in_schema=False)
async def account_unknown(rest: str) -> Response:
    """The application host answers an unknown route with HTTP 200.

    The two hosts genuinely disagree about not-found and the clone keeps both
    behaviours instead of normalising them to one status.
    """

    return app_not_found()


# ---------------------------------------------------------------------------
# entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":  # pragma: no cover - manual/offline start
    import uvicorn

    def _terminate(signum, frame):  # noqa: ANN001, ARG001
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, _terminate)
    uvicorn.run(
        app,
        host=os.environ.get("HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", "10000")),
        log_level="warning",
    )
