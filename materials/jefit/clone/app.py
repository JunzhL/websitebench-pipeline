"""JEFIT offline clone — FastAPI composition root.

* Frozen localized public documents (``frontend/pages/*.html``) are served at
  their real source routes; unknown paths reproduce the source's unbranded
  server 404.
* Discovery pages (``frontend/templates/*.html``) render the reduced catalog
  fixture through templates carved from the captured DOM; the two captured
  entity pages (/exercises/2/..., /routines/19113/...) serve their frozen
  documents verbatim.
* The member area (``frontend/member/*.html``) renders templates carved from
  the authenticated capture, bound to this site's own SQLite business state
  behind the vendored ``websitebench`` seam (``backend/db.py``).
* Payment (task 539) accepts ONLY opaque local-sandbox scenario ids; the
  Elite order and membership state are written in the same transaction that
  consumes the sandbox approval. Card-like fields are rejected, never stored.
* ``GET /healthz`` -> ``{"ok":true,"site_id":"jefit"}``;
  ``GET /__websitebench/health`` -> ``{"status":"ok"}`` (Harbor ABI).
"""

from __future__ import annotations

import hmac
import html
import json
import os
import re
import secrets
import sys
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:  # vendored websitebench + backend imports
    sys.path.insert(0, str(ROOT))

# Writable-state location. Harbor's ABI passes DATA_DIR; the offline-clone
# live sandbox passes WEBSITEBENCH_DATA_DIR (plus the vendored runtime's
# compatibility name). Reading only DATA_DIR left the database pointed at the
# read-only candidate root under the live diagnostic, so every write route
# answered 500 while read-only pages stayed 200.
_DATA_DIR = (
    os.environ.get("DATA_DIR")
    or os.environ.get("WEBSITEBENCH_DATA_DIR")
    or os.environ.get("CLAWBENCH_DATA_DIR")
)
if _DATA_DIR and "WEBSITEBENCH_SITE_BACKEND_DATABASE" not in os.environ:
    os.environ["WEBSITEBENCH_SITE_BACKEND_DATABASE"] = str(
        Path(_DATA_DIR).resolve() / "jefit.sqlite3"
    )

from fastapi import FastAPI, Request  # noqa: E402
from fastapi.responses import (  # noqa: E402
    HTMLResponse,
    JSONResponse,
    PlainTextResponse,
    RedirectResponse,
    Response,
)
from jinja2 import Environment, FileSystemLoader  # noqa: E402
from starlette.staticfiles import StaticFiles  # noqa: E402

from backend import db  # noqa: E402
from backend.db import PaymentFieldRejected  # noqa: E402
from websitebench.local_clone_auth import (  # noqa: E402
    AuthConflict,
    AuthError,
    AuthRejected,
    AuthValidationError,
)
from websitebench.site_backend import PaymentError  # noqa: E402

SITE_ID = "jefit"
PAGES = ROOT / "frontend" / "pages"
MEMBER = ROOT / "frontend" / "member"
TEMPLATES = ROOT / "frontend" / "templates"
STATIC_DIR = ROOT / "static"
FIXTURES = ROOT / "backend" / "fixtures"

_HEALTH_BODY = json.dumps({"ok": True, "site_id": SITE_ID}, separators=(",", ":"))
ADMIN_TOKEN = os.environ.get("WEBSITEBENCH_JEFIT_ADMIN_TOKEN", "jefit-local-admin")
BUILD_ID = os.environ.get("DEPLOYMENT_BUILD_ID") or os.environ.get(
    "WEBSITEBENCH_BUILD_ID"
)

CONTENT_SECURITY_POLICY = (
    "default-src 'self'; "
    "img-src 'self' data:; "
    "style-src 'self' 'unsafe-inline'; "
    "script-src 'self' 'unsafe-inline'; "
    "font-src 'self' data:; "
    "connect-src 'self'; "
    "frame-ancestors 'none'; "
    "base-uri 'self'; "
    "form-action 'self'"
)

app = FastAPI(title="JEFIT offline clone", docs_url=None, redoc_url=None,
              openapi_url=None)

_env = Environment(
    loader=FileSystemLoader([str(TEMPLATES), str(MEMBER)]),
    autoescape=False,
    auto_reload=False,
)

_PAGE_CACHE: dict[str, str] = {}
_CATALOG = json.loads((FIXTURES / "catalog.json").read_text())
_UI = json.loads((FIXTURES / "ui.json").read_text())
_SIGNUP = json.loads(
    (ROOT / "frontend" / "signup-steps.json").read_text()
)
PAGE_SIZE = 18


def esc(value: object) -> str:
    return html.escape(str(value), quote=True)


_NAV_OVERLAYS = json.loads(
    (ROOT / "frontend" / "nav-overlays.json").read_text()
)
_NAV_BUNDLE = "".join(
    f'<template data-nav-overlay="{key}">{markup}</template>'
    for key, markup in _NAV_OVERLAYS.items()
)


def _enhance_page(name: str, doc: str) -> str:
    """The captured nav-overlay states ride along as inert <template>
    elements for the clone runtime (form wiring is baked into the documents
    at build time by tools/build_clone_pages.py)."""

    if name == "not-found":
        # the source 404 is a bare unbranded server page: no clone runtime,
        # no nav overlays
        return doc.replace(
            '<script src="/static/site/app.js" defer></script>', ""
        )
    if "</body>" in doc and "data-nav-overlay" not in doc:
        doc = doc.replace("</body>", _NAV_BUNDLE + "</body>", 1)
    return doc


def _load_page(name: str) -> str:
    cached = _PAGE_CACHE.get(name)
    if cached is None:
        cached = (PAGES / f"{name}.html").read_text(encoding="utf-8")
        cached = _enhance_page(name, cached)
        _PAGE_CACHE[name] = cached
    return cached


def _not_found() -> HTMLResponse:
    return HTMLResponse(_load_page("not-found"), status_code=404)


# ---------------------------------------------------------------------------
# session helpers
# ---------------------------------------------------------------------------


def _cookie_name() -> str:
    return db.backend().config.cookie_name


def _set_session_cookie(response: Response, token: str) -> None:
    facts = db.backend().session_cookie
    response.set_cookie(
        facts["name"],
        token,
        secure=facts["secure"],
        httponly=facts["httponly"],
        samesite=facts["samesite"],
        path=facts["path"],
    )


def _session_token(request: Request) -> str | None:
    return request.cookies.get(_cookie_name())


def current_user(request: Request) -> dict | None:
    token = _session_token(request)
    if not token:
        return None
    session = db.auth().resolve_session(token)
    if not session or not session.get("authenticated"):
        return None
    account = session.get("account") or {}
    subject = account.get("subject_id")
    if not subject:
        return None
    return db.user_by_subject(str(subject))


def _login_redirect(path: str) -> RedirectResponse:
    return RedirectResponse(
        f"/login?redirect={urllib.parse.quote(path, safe='')}", status_code=302
    )


def _safe_local(path: str | None, fallback: str = "/my-jefit") -> str:
    if not path or not path.startswith("/") or path.startswith("//"):
        return fallback
    if "\\" in path or "\r" in path or "\n" in path:
        return fallback
    return path


# ---------------------------------------------------------------------------
# middleware / health / static
# ---------------------------------------------------------------------------


class _MirrorStaticFiles(StaticFiles):
    """Retry percent-encoded on-disk names (mirror keeps source encoding)."""

    def lookup_path(self, path: str):
        full_path, stat_result = super().lookup_path(path)
        if stat_result is not None:
            return full_path, stat_result
        requoted = "/".join(urllib.parse.quote(seg) for seg in path.split("/"))
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
    response.headers["X-Frame-Options"] = "DENY"
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


_EXTERNAL_PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>External link boundary</title></head>
<body style="font-family: sans-serif; max-width: 40rem; margin: 4rem auto;">
<h1>External link</h1>
<p>This offline clone does not open third-party destinations. The original
page linked to an external site ({slug}). No remote request was made.</p>
<p><a href="/">Return to the home page</a></p>
</body></html>
"""


@app.get("/external/{slug}", include_in_schema=False)
async def external_boundary(slug: str) -> HTMLResponse:
    return HTMLResponse(_EXTERNAL_PAGE.format(slug=esc(slug[:80])))


# ---------------------------------------------------------------------------
# frozen public pages
# ---------------------------------------------------------------------------

PAGE_ROUTES: dict[str, str] = {
    "/": "home",
    "/elite": "elite",
    "/support": "support",
    "/support/faq": "support-faq",
    "/about-us": "about-us",
    "/ai-workout-tracker": "ai-workout-tracker",
    "/ai-workout-tracker/adaptive-plan": "adaptive-plan",
    "/use-case": "use-case",
    "/watch": "watch",
    "/coach": "coach",
    "/our-story": "our-story",
    "/community/": "community",
    "/blog": "blog",
    "/terms-of-use": "terms-of-use",
    "/privacy-policy": "privacy-policy",
    "/ip-notice-process": "ip-notice-process",
    "/press-media": "press-media",
    "/signup/results": "signup-results",
    "/signup/register": "signup-account-create",
}


def _register_page(route: str, name: str) -> None:
    @app.get(route, include_in_schema=False)
    async def frozen_page(_name: str = name) -> HTMLResponse:
        return HTMLResponse(_load_page(_name))


for _route, _name in PAGE_ROUTES.items():
    _register_page(_route, _name)


@app.get("/home", include_in_schema=False)
async def home_alias() -> HTMLResponse:
    """Clone-local alias of the index document (contract tooling cannot use
    '/' as a step)."""

    return HTMLResponse(_load_page("home"))


@app.get("/community", include_in_schema=False)
async def community_redirect() -> RedirectResponse:
    # source: /community 301s to /community/
    return RedirectResponse("/community/", status_code=301)


@app.exception_handler(404)
async def not_found_handler(request: Request, exc: Exception) -> Response:
    if request.url.path.startswith("/api/"):
        return JSONResponse({"error": "not-found"}, status_code=404)
    return _not_found()


# ---------------------------------------------------------------------------
# discovery: exercises
# ---------------------------------------------------------------------------


def _exercise_ctx(entry: dict) -> dict:
    return {
        "id": entry["id"],
        "slug": entry["slug"],
        "name": esc(entry["name"]),
        "muscle": esc(entry["muscle"]),
        "equipment": esc(entry["equipment"]),
        "description": esc(entry["description"]),
        "srcset": entry["srcset"],
        "src": entry["src"],
    }


def _client_catalog_json() -> str:
    payload = [
        {
            "id": e["id"],
            "slug": e["slug"],
            "name": e["name"],
            "muscle": e["muscle"],
            "equipment": e["equipment"],
            "description": e["description"],
            "srcset": e["srcset"],
            "src": e["src"],
        }
        for e in _CATALOG["exercises"]
    ]
    return json.dumps(
        {
            "exercises": payload,
            "muscles": _CATALOG["muscles"],
            "equipment": _CATALOG["equipment"],
            "page_size": PAGE_SIZE,
        }
    ).replace("</", "<\\/")


def _pagination(base: str, page: int, pages: int) -> str:
    region = _UI["pagination_region"].replace("/exercises?page=", f"{base}?page=")
    current_tpl = _UI["number_current"].replace("/exercises?page=", f"{base}?page=")
    other_tpl = _UI["number_other"].replace("/exercises?page=", f"{base}?page=")

    def anchor_sub(match: re.Match) -> str:
        tag = match.group(0)
        label_m = re.search(r'aria-label="([^"]+)"', tag)
        label = label_m.group(1) if label_m else ""
        if label == "First page":
            target = 1
        elif label == "Previous page":
            target = page - 1  # page 1 emits ?page=0 (source quirk)
        elif label == "Next page":
            target = min(page + 1, pages)
        elif label == "Last page":
            target = pages
        else:
            return tag
        return re.sub(r"\?page=\d+", f"?page={target}", tag)

    region = re.sub(r"<a [^>]*aria-label=\"(?:First|Previous|Next|Last) page\"[^>]*>",
                    anchor_sub, region)
    # numbered sequence: replace from the 'Page 1' anchor start to the last
    # numbered anchor end with the generated set
    starts = [m.start() for m in re.finditer(r'<a aria-label="Page \d+"', region)]
    if starts:
        first = starts[0]
        last = starts[-1]
        last_end = region.find("</a>", last) + 4
        numbers: list[str] = []
        window = list(range(1, min(pages, 5) + 1))
        if pages > 5:
            window.append(pages)
        for number in window:
            template = current_tpl if number == page else other_tpl
            piece = re.sub(r"\?page=\d+", f"?page={number}", template)
            piece = re.sub(r'aria-label="Page \d+"',
                           f'aria-label="Page {number}"', piece)
            piece = re.sub(r">(\d+)</a>$", f">{number}</a>", piece)
            numbers.append(piece)
        region = region[:first] + "".join(numbers) + region[last_end:]
    region = re.sub(
        r"<!-- -->\d+<!-- --> of <!-- -->\d+</p>",
        f"<!-- -->{page}<!-- --> of <!-- -->{pages}</p>",
        region,
    )
    return region


@app.get("/exercises", include_in_schema=False)
async def exercises_list(request: Request) -> HTMLResponse:
    raw_page = request.query_params.get("page", "1")
    try:
        page = int(raw_page)
    except ValueError:
        page = 1
    entries = _CATALOG["exercises"]
    pages = max(1, -(-len(entries) // PAGE_SIZE))
    page = min(max(page, 1), pages)  # ?page=0 renders page 1 (source quirk)
    chunk = entries[(page - 1) * PAGE_SIZE : page * PAGE_SIZE]
    title = (
        "Exercise Database - JEFIT"
        if page == 1
        else f"Exercise Database - Page {page} - JEFIT"
    )
    body = _env.get_template("exercises.html").render(
        exercises=[_exercise_ctx(e) for e in chunk],
        count=len(entries),
        title=esc(title),
        pagination=_pagination("/exercises", page, pages),
        catalog_json=_client_catalog_json(),
    )
    return HTMLResponse(body)


MUSCLE_ICONS = {
    "Abs": "absIcon",
    "Back": "backIcon",
    "Biceps": "bicepsIcon",
    "Cardio": "cardioIcon",
    "Chest": "chestIcon",
    "Forearms": "forearmsIcon",
    "Glutes": "glutesIcon",
    "Shoulders": "shoulderIcon",
    "Triceps": "tricepsIcon",
    "Upper Legs": "upperLegsIcon",
    "Lower Legs": "lowerLegsIcon",
}


def _slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")


def _muscle_icon(muscle: str) -> str:
    name = MUSCLE_ICONS.get(muscle, "chestIcon")
    candidate = (
        STATIC_DIR
        / "assets"
        / "2026-08-18.jefit-r1"
        / "www.jefit.com"
        / "icons"
        / "muscle"
        / f"{name}.svg"
    )
    if not candidate.is_file():
        name = "chestIcon"
    return (
        f"/static/assets/2026-08-18.jefit-r1/www.jefit.com/icons/muscle/"
        f"{name}.svg"
    )


def _render_exercise_detail(entry: dict, template: str = "exercise-detail.html"):
    detail = entry["detail"]
    alternatives = [
        _exercise_ctx(e)
        for e in _CATALOG["exercises"]
        if e["muscle"] == entry["muscle"] and e["id"] != entry["id"]
    ][:8]
    return _env.get_template(template).render(
        name=esc(entry["name"]),
        hero_src=entry["src"],
        muscle=esc(entry["muscle"]),
        muscle_href=f"/exercises/{_slugify(entry['muscle'])}",
        muscle_icon=_muscle_icon(entry["muscle"]),
        equipment=esc(entry["equipment"]),
        equipment_href=f"/exercises/{_slugify(entry['equipment'])}",
        equipment_icon=entry["src"],
        difficulty=esc(detail["difficulty"].lower()),
        exercise_type=esc(detail["exercise_type"].lower()),
        log_type=esc(detail["log_type"].lower()),
        instructions=esc(entry["description"]),
        alternatives=alternatives,
    )


@app.get("/exercises/{exercise_id}/{slug}", include_in_schema=False)
async def exercise_detail(exercise_id: str, slug: str) -> HTMLResponse:
    if exercise_id == "2":
        return HTMLResponse(_load_page("exercise-detail"))
    try:
        entry = db.exercise_by_id(int(exercise_id))
    except ValueError:
        entry = None
    if entry is None:
        return _not_found()
    return HTMLResponse(_render_exercise_detail(entry))


# ---------------------------------------------------------------------------
# discovery: routines
# ---------------------------------------------------------------------------

SORTS = {
    None: "Most Downloaded",
    "views": "Most Viewed",
    "last_updated": "Latest",
}


def _routine_ctx(entry: dict) -> dict:
    return {
        "id": entry["id"],
        "slug": entry["slug"],
        "name": esc(entry["name"]),
        "meta": esc(entry["meta"]),
        "days_label": esc(entry["days_label"]),
        "focus": esc(entry["focus"]),
        "level": esc(entry["level"]),
        "description": esc(entry["description"]),
        "srcset": entry["srcset"],
        "src": entry["src"],
    }


def _sorted_routines(sort: str | None) -> list[dict]:
    routines = list(_CATALOG["routines"])
    if sort == "views":
        routines.sort(key=lambda r: r["id"], reverse=True)
    elif sort == "last_updated":
        routines.reverse()
    return routines


@app.get("/routines", include_in_schema=False)
async def routines_list(request: Request) -> HTMLResponse:
    sort = request.query_params.get("sort")
    if sort not in SORTS:
        sort = None
    body = _env.get_template("routines.html").render(
        routines=[_routine_ctx(r) for r in _sorted_routines(sort)[:16]],
        sort_label=SORTS[sort],
    )
    return HTMLResponse(body)


CATEGORY_HEADINGS = {
    "beginner": "Workout Plans for Beginner - Simple &amp; Effective Routines "
    "to Get Started!",
    "home": "Home Workout Plans - Train Anywhere, No Gym Needed",
    "gym": "Gym Workout Plans - Build Strength with Proven Routines",
    "men": "Workout Plans for Men - Build Muscle and Strength",
    "women": "Workout Plans for Women - Strong, Lean and Confident",
    "muscle-building": "Muscle-Building Workout Plans - Grow with Progressive "
    "Training",
    "fat-burning": "Fat-Burning Workout Plans - Train Hard, Burn More",
    "leg": "Leg Workout Plans - Stronger Squats, Bigger Legs",
}


def _category_matches(slug: str) -> list[dict]:
    routines = _CATALOG["routines"]

    def level_is(level: str):
        return [r for r in routines if r["level"] == level]

    keyword_map = {
        "beginner": level_is("Beginner"),
        "home": [r for r in routines if "Home" in r["name"] or "Dumbbell" in
                 r["name"]],
        "gym": [r for r in routines if "Gym" in r["name"] or "Machine" in
                r["name"] or "Barbell" in r["name"]],
        "men": [r for r in routines if r["focus"] == "Bulking"],
        "women": [r for r in routines if r["focus"] == "Cutting"],
        "muscle-building": [r for r in routines if r["focus"] == "Bulking"],
        "fat-burning": [r for r in routines if r["focus"] == "Cutting"],
        "leg": [r for r in routines if "Leg" in r["name"] or "Lower" in
                r["name"] or "Glute" in r["name"]],
    }
    matches = keyword_map.get(slug, [])
    if len(matches) < 10:
        seen = {r["id"] for r in matches}
        matches = matches + [r for r in routines if r["id"] not in seen]
    return matches[:10]


@app.get("/routines/{tail:path}", include_in_schema=False)
async def routines_tail(tail: str) -> HTMLResponse:
    parts = tail.strip("/").split("/")
    if len(parts) == 1 and parts[0] in _CATALOG["routine_categories"]:
        slug = parts[0]
        heading = CATEGORY_HEADINGS.get(slug, CATEGORY_HEADINGS["beginner"])
        body = _env.get_template("routines-category.html").render(
            routines=[_routine_ctx(r) for r in _category_matches(slug)],
            title=heading,
            heading=heading,
        )
        return HTMLResponse(body)
    if len(parts) == 2 and parts[0].isdigit():
        routine_id = int(parts[0])
        if routine_id == 19113:
            return HTMLResponse(_load_page("routine-detail"))
        entry = db.routine_fixture_by_id(routine_id)
        if entry is not None:
            return HTMLResponse(_render_routine_detail_fixture(entry))
        plan = db.plan_by_id(routine_id)
        if plan is not None and plan["is_public"]:
            return HTMLResponse(_render_routine_detail_plan(plan))
        return _not_found()
    return _not_found()


def _day_ctx(title: str, exercises: list[dict]) -> dict:
    items = []
    for entry in exercises:
        fixture = db.exercise_by_id(entry["exercise_id"]) or {}
        items.append(
            {
                "id": entry["exercise_id"],
                "slug": fixture.get("slug", "exercise"),
                "name": esc(entry["name"]),
                "sets": entry["sets"],
                "reps": entry["reps"],
                "srcset": fixture.get("srcset", ""),
                "src": fixture.get("src", ""),
            }
        )
    return {
        "title": esc(title),
        "est_min": 4 + 8 * len(items),
        "count": len(items),
        "exercises": items,
    }


def _render_routine_detail_fixture(entry: dict) -> str:
    days = [
        _day_ctx(day["title"], [
            {
                "exercise_id": item["exercise_id"],
                "name": item["name"],
                "sets": item["sets"],
                "reps": item["reps"],
            }
            for item in day["exercises"]
        ])
        for day in entry["days"]
    ]
    meta = entry["meta"].split("·")[0].strip()
    summary = (
        f"The {entry['name']} routine by JefitTeam is a {meta} workout plan. "
        f"It is a {entry['level'].lower()} level plan to achieve "
        f"{entry['focus'].lower()} fitness goals."
    )
    return _env.get_template("routine-detail.html").render(
        name=esc(entry["name"]),
        focus=esc(entry["focus"]),
        level=esc(entry["level"]),
        equipment_tag="Gym",
        summary=esc(summary),
        description=esc(entry["description"]),
        days=days,
        banner_srcset=entry["srcset"],
        banner_src=entry["src"],
    )


def _render_routine_detail_plan(plan: dict) -> str:
    days = [
        _day_ctx(day["title"], day["exercises"]) for day in plan["days"]
    ]
    summary = (
        f"The {plan['name']} routine is a {len(days)} day workout plan. It "
        f"is a {plan['level'].lower()} level plan to achieve "
        f"{plan['focus'].lower()} fitness goals."
    )
    fallback = _CATALOG["routines"][0]
    return _env.get_template("routine-detail.html").render(
        name=esc(plan["name"]),
        focus=esc(plan["focus"]),
        level=esc(plan["level"]),
        equipment_tag="Any",
        summary=esc(summary),
        description=esc(plan["description"] or "This day is empty"),
        days=days,
        banner_srcset=fallback["srcset"],
        banner_src=fallback["src"],
    )


# ---------------------------------------------------------------------------
# build routine (anonymous draft flow)
# ---------------------------------------------------------------------------


@app.get("/build-routine", include_in_schema=False)
async def build_routine(request: Request):
    user = current_user(request)
    if user is not None:
        plan = db.create_plan(user["id"])
        return RedirectResponse(
            f"/my-jefit/workouts/edit?id={plan['id']}", status_code=302
        )
    code = request.query_params.get("code")
    if not code or not re.fullmatch(r"[A-Za-z0-9_-]{4,40}", code):
        code = secrets.token_urlsafe(9)
        db.create_plan(None, code=code, is_public=True)
        return RedirectResponse(f"/build-routine?code={code}", status_code=302)
    return HTMLResponse(_load_page("build-routine"))


@app.post("/api/build-routine/save", include_in_schema=False)
async def build_routine_save(request: Request) -> JSONResponse:
    body = await _json_body(request)
    code = str(body.get("code", ""))
    site_backend = db.backend()
    with site_backend.lifecycle.connection() as connection:
        row = connection.execute(
            "SELECT id FROM jefit_routines WHERE code=? AND owner_user_id "
            "IS NULL",
            (code,),
        ).fetchone()
    if row is None:
        return JSONResponse({"error": "not-found"}, status_code=404)
    plan_id = int(row[0])
    name = str(body.get("name", "")).strip()
    if name:
        db.rename_plan(plan_id, name)
    plan = db.plan_by_id(plan_id)
    slug = _slugify(plan["name"]) or "new-routine"
    return JSONResponse({"redirect": f"/routines/{plan_id}/{slug}"})


# ---------------------------------------------------------------------------
# auth: login / logout / recovery / signup
# ---------------------------------------------------------------------------


LOGIN_ERROR_SNIPPET = (
    '<p data-clone-login-error data-slot="text" style="color:#dc2626" '
    'class="text-sm/[1.4] font-normal">Invalid username or password.</p>'
)


def _login_page(error: bool = False, sent: bool = False, page: str = "login") -> str:
    doc = _load_page(page)
    if error:
        # clone-local inline error (wrong-credential copy unobserved on
        # source; disclosed): injected directly under the Log In heading.
        doc = doc.replace(
            ">Log In</", ">Log In</", 1
        )
        anchor = doc.find("</h1>")
        if anchor >= 0:
            doc = doc[: anchor + 5] + LOGIN_ERROR_SNIPPET + doc[anchor + 5 :]
    if sent:
        anchor = doc.find("</h1>")
        snippet = (
            '<p data-clone-reset-sent data-slot="text" '
            'class="text-sm/[1.4] font-normal">If that email belongs to a '
            "JEFIT account, a reset code is waiting in the local outbox.</p>"
        )
        if anchor >= 0:
            doc = doc[: anchor + 5] + snippet + doc[anchor + 5 :]
    return doc


@app.get("/login", include_in_schema=False)
async def login_page(request: Request):
    if current_user(request) is not None:
        return RedirectResponse("/my-jefit", status_code=302)
    return HTMLResponse(_login_page())


@app.post("/login", include_in_schema=False)
async def login_submit(request: Request):
    form = await request.form()
    identifier = str(form.get("username", "") or form.get("email", "")).strip()
    password = str(form.get("password", ""))
    redirect = _safe_local(str(form.get("redirect", "") or
                               request.query_params.get("redirect", "")))
    token = _session_token(request)
    token, _session = db.auth().ensure_session(token)
    if not identifier or not password:
        # Source behavior: an empty submit settles back on the untouched
        # Log In panel with no inline validation (directly observed).
        response = HTMLResponse(_login_page())
        _set_session_cookie(response, token)
        return response
    email = db.email_for_login(identifier)
    try:
        result = db.auth().sign_in(token, email=email, password=password)
    except (AuthRejected, AuthValidationError):
        response = HTMLResponse(_login_page(error=True), status_code=422)
        _set_session_cookie(response, token)
        return response
    response = RedirectResponse(redirect, status_code=302)
    _set_session_cookie(response, result["session_token"])
    return response


@app.post("/logout", include_in_schema=False)
async def logout(request: Request) -> RedirectResponse:
    token = _session_token(request)
    if token:
        db.auth().sign_out(token)
    response = RedirectResponse("/", status_code=302)
    response.delete_cookie(_cookie_name(), path="/")
    return response


@app.get("/login/forgot-password", include_in_schema=False)
async def forgot_password_page() -> HTMLResponse:
    return HTMLResponse(_login_page(page="forgot-password"))


@app.post("/login/forgot-password", include_in_schema=False)
async def forgot_password_submit(request: Request):
    form = await request.form()
    email = str(form.get("email", "")).strip()
    token = _session_token(request)
    token, _session = db.auth().ensure_session(token)
    if not email:
        return HTMLResponse(
            _login_page(error=False, page="forgot-password"), status_code=422
        )
    try:
        db.auth().start_password_reset(token, email=email,
                                       restart_invalid_flow=True)
    except AuthValidationError:
        return HTMLResponse(
            _login_page(page="forgot-password"), status_code=422
        )
    except AuthError:
        pass  # non-account emails get the same neutral confirmation
    response = HTMLResponse(_login_page(sent=True, page="forgot-password"))
    _set_session_cookie(response, token)
    return response


@app.post("/api/auth/reset-complete", include_in_schema=False)
async def reset_complete(request: Request) -> JSONResponse:
    body = await _json_body(request)
    token = _session_token(request)
    if not token:
        return JSONResponse({"error": "session"}, status_code=422)
    code = str(body.get("code", ""))
    password = str(body.get("password", ""))
    try:
        db.auth().verify_password_reset_code(token, code)
        db.auth().complete_password_reset(token, new_password=password)
    except AuthError as exc:
        return JSONResponse({"error": str(exc)}, status_code=422)
    return JSONResponse({"reset": True})


def _splice_signup(step: int) -> str:
    """Serve the signup page with one questionnaire panel in the swap slot.

    Offset-free by construction: the slot is located by matching the step-1
    panel string that the page already contains, so no byte offset can go
    stale when the document is transformed elsewhere. A slot that cannot be
    located is a hard failure — a silent fallback would ship a page whose
    questionnaire cannot advance.
    """

    base = _load_page("signup")
    panels = _SIGNUP["panels"]
    step = min(max(step, 1), 17)
    anchor = panels["1"]
    if base.count(anchor) != 1:
        raise RuntimeError(
            "signup panel slot could not be located in the served document "
            f"(matches={base.count(anchor)}); rebuild "
            "clone/frontend/signup-steps.json with tools/build_signup_steps.py"
        )
    steps_json = json.dumps(panels).replace("</", "<\\/")
    doc = base.replace(
        anchor,
        "<!--jefit-signup-slot-->"
        + panels[str(step)]
        + "<!--/jefit-signup-slot-->",
        1,
    )
    doc = doc.replace(
        "</body>",
        '<script id="jefit-signup-steps" type="application/json">'
        + steps_json
        + "</script></body>",
        1,
    )
    return doc


@app.get("/signup", include_in_schema=False)
async def signup_page(request: Request) -> HTMLResponse:
    raw = request.query_params.get("step", "1")
    try:
        step = int(raw)
    except ValueError:
        step = 1
    return HTMLResponse(_splice_signup(step))


@app.post("/signup/register", include_in_schema=False)
async def signup_register(request: Request):
    """Continue past the captured email step: create the account.

    The source flow past the email entry was never observed (the user
    registered personally); the clone completes registration in one submit
    with email + username + password (clone-local continuation, disclosed).
    """

    form = await request.form()
    email = str(form.get("email", "")).strip()
    username = str(form.get("username", "")).strip() or email.split("@")[0]
    password = str(form.get("password", ""))
    questionnaire_raw = str(form.get("questionnaire", "") or "{}")
    try:
        questionnaire = json.loads(questionnaire_raw)
        if not isinstance(questionnaire, dict):
            questionnaire = {}
    except json.JSONDecodeError:
        questionnaire = {}
    token = _session_token(request)
    token, _session = db.auth().ensure_session(token)
    if not email or not password:
        # Email-only submit is the captured register step: continue to the
        # clone-local credentials panel. A missing email is a validation
        # failure.
        response = HTMLResponse(
            _register_continuation(
                email,
                "" if email else "Enter your email address to continue.",
            ),
            status_code=200 if email else 422,
        )
        _set_session_cookie(response, token)
        return response

    def subject_factory(connection, registration):
        registration = dict(registration)
        registration["display_name"] = username
        return db.create_user_subject(connection, registration, questionnaire)

    try:
        result = db.auth().complete_externally_verified_registration(
            token,
            email=email,
            display_name=username,
            password=password,
            subject_factory=subject_factory,
        )
    except AuthConflict:
        response = HTMLResponse(
            _register_continuation(
                email, "That email already belongs to a JEFIT account."
            ),
            status_code=409,
        )
        _set_session_cookie(response, token)
        return response
    except (AuthValidationError, AuthRejected) as exc:
        response = HTMLResponse(
            _register_continuation(email, esc(str(exc))), status_code=422
        )
        _set_session_cookie(response, token)
        return response
    user = db.user_by_subject(result["account"]["subject_id"])
    if user is not None:
        db.issue_verification_mail(user)
    response = RedirectResponse("/my-jefit", status_code=302)
    _set_session_cookie(response, result["session_token"])
    return response


_REGISTER_FIELDS = """
<input type="hidden" name="email" value="{email}">
<label class="block text-sm font-medium" for="username"
style="margin-top:12px">Username</label>
<input id="username" name="username" required class="ring-border-primary
block w-full h-12 px-4 rounded-md border py-1.5 text-gray-900 shadow-sm"
style="margin-top:4px">
<label class="block text-sm font-medium" for="password"
style="margin-top:12px">Password</label>
<input id="password" name="password" type="password" required minlength="8"
class="ring-border-primary block w-full h-12 px-4 rounded-md border py-1.5
text-gray-900 shadow-sm" style="margin-top:4px">
"""


def _register_continuation(email: str, message: str = "") -> str:
    """Second register step (clone-local continuation of the captured email
    panel): same document, email fixed, username + password fields added."""

    doc = _load_page("signup-account-create")
    email_input = re.search(r'<input id="email"[^>]*>', doc)
    if email_input:
        fields = _REGISTER_FIELDS.format(email=esc(email))
        note = (
            f'<p data-clone-register-note style="color:#dc2626" '
            f'class="text-sm">{message}</p>'
            if message
            else ""
        )
        doc = (
            doc[: email_input.start()]
            + note
            + fields
            + doc[email_input.end() :]
        )
    return doc


# ---------------------------------------------------------------------------
# member area
# ---------------------------------------------------------------------------


def _member_guard(request: Request):
    user = current_user(request)
    if user is None:
        path = request.url.path
        if request.url.query:
            path = f"{path}?{request.url.query}"
        return None, _login_redirect(path)
    return user, None


def _member_ctx(user: dict) -> dict:
    return {
        "username": esc(user["username"]),
        "email": esc(user["email"]),
    }


def _render_member(template: str, user: dict, **extra) -> HTMLResponse:
    context = _member_ctx(user)
    context.update(extra)
    return HTMLResponse(_env.get_template(template).render(**context))


@app.get("/my-jefit", include_in_schema=False)
async def my_jefit(request: Request):
    user, redirect = _member_guard(request)
    if redirect:
        return redirect
    return _render_member("dashboard.html", user)


def _post_ctx(row: dict, index: int) -> dict:
    ages = ("2 hours ago", "5 hours ago", "12 hours ago", "1 day ago",
            "2 days ago", "3 days ago")
    body = row["body"]
    if row["title"]:
        body = f"{row['title']}\n\n{body}"
    return {
        "author": esc(row["author"]),
        "age": ages[index % len(ages)],
        "body": esc(body),
        "likes": row["likes"],
        "comments": row["comments"],
    }


@app.get("/my-jefit/qa", include_in_schema=False)
async def my_jefit_qa(request: Request):
    user, redirect = _member_guard(request)
    if redirect:
        return redirect
    posts = [_post_ctx(p, i) for i, p in enumerate(db.posts_for("qa"))]
    return _render_member("qa.html", user, posts=posts)


@app.get("/my-jefit/popular", include_in_schema=False)
async def my_jefit_popular(request: Request):
    user, redirect = _member_guard(request)
    if redirect:
        return redirect
    posts = [_post_ctx(p, i) for i, p in enumerate(db.posts_for("popular"))]
    return _render_member("popular.html", user, posts=posts)


def _fmt_hms(seconds: int) -> str:
    seconds = max(0, int(seconds))
    return f"{seconds // 3600:02d}:{seconds % 3600 // 60:02d}:{seconds % 60:02d}"


def _fmt_weight(value: float) -> str:
    return f"{value:g}"


def _session_ctx(session: dict) -> dict:
    groups: dict[int, dict] = {}
    for item in session["sets"]:
        group = groups.setdefault(
            item["exercise_id"],
            {
                "exercise_id": item["exercise_id"],
                "name": esc(item["name"]),
                "sets": [],
                "best": 0.0,
            },
        )
        group["sets"].append(
            {
                "set_index": item["set_index"],
                "weight_display": _fmt_weight(item["weight_lbs"]),
                "reps": item["reps"],
            }
        )
        one_rm = item["weight_lbs"] * (1 + item["reps"] / 30)
        group["best"] = max(group["best"], one_rm)
    for group in groups.values():
        fixture = db.exercise_by_id(group["exercise_id"]) or {}
        group["srcset"] = fixture.get("srcset", "")
        group["src"] = fixture.get("src", "")
        group["best_1rm"] = f"{group['best']:.2f}"
    try:
        start_h, start_m = (int(x) for x in session["start_time"].split(":"))
        end_h, end_m = (int(x) for x in session["end_time"].split(":"))
        duration = max(0, (end_h * 60 + end_m) - (start_h * 60 + start_m)) * 60
    except ValueError:
        start_h, start_m, duration = 9, 0, 0
    year, month, day = session["session_date"].split("-")
    months = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep",
              "Oct", "Nov", "Dec")
    hour12 = start_h % 12 or 12
    return {
        "date_label": f"{months[int(month) - 1]} {int(day)}, {year}",
        "time_label": f"{hour12}:{start_m:02d} {'AM' if start_h < 12 else 'PM'}",
        "records": sum(1 for s in session["sets"] if s["is_record"]),
        "training_time": _fmt_hms(duration),
        "actual_time": _fmt_hms(duration),
        "rest_time": "00:01:00",
        "complete": len(groups),
        "volume": _fmt_weight(session["volume_lbs"]),
        "groups": list(groups.values()),
    }


def _library_ctx() -> list[dict]:
    return [_exercise_ctx(e) for e in _CATALOG["exercises"]]


@app.get("/my-jefit/progress", include_in_schema=False)
async def progress_redirect(request: Request):
    user, redirect = _member_guard(request)
    if redirect:
        return redirect
    return RedirectResponse("/my-jefit/progress/history", status_code=302)


@app.get("/my-jefit/progress/history", include_in_schema=False)
async def progress_history(request: Request):
    user, redirect = _member_guard(request)
    if redirect:
        return redirect
    day = request.query_params.get("date") or db.SEED_DAY
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", day):
        day = db.SEED_DAY
    sessions = [_session_ctx(s) for s in db.sessions_for_user(user["id"], day)]
    all_dates = sorted(
        {s["session_date"] for s in db.sessions_for_user(user["id"])}
    )
    doc = _render_member(
        "progress-history.html",
        user,
        sessions=sessions,
        library=_library_ctx(),
    )
    body = doc.body.decode("utf-8")
    payload = json.dumps({"selected": day, "dates": all_dates}).replace(
        "</", "<\\/"
    )
    body = body.replace(
        "</body>",
        f'<script id="jefit-history" type="application/json">{payload}'
        "</script></body>",
        1,
    )
    return HTMLResponse(body)


@app.get("/my-jefit/progress/photos", include_in_schema=False)
async def progress_photos(request: Request):
    user, redirect = _member_guard(request)
    if redirect:
        return redirect
    return _render_member("progress-photos.html", user)


@app.get("/my-jefit/progress/insights", include_in_schema=False)
async def progress_insights(request: Request):
    user, redirect = _member_guard(request)
    if redirect:
        return redirect
    doc = _render_member("progress-insights.html", user)
    sessions = db.sessions_for_user(user["id"])
    if sessions:
        body = doc.body.decode("utf-8")
        volume = _fmt_weight(sum(s["volume_lbs"] for s in sessions))
        summary = (
            '<div data-clone-insights class="flex flex-col gap-2">'
            f'<p data-slot="text" class="text-base/[1.4] font-semibold '
            f'text-text-primary">{len(sessions)} workout'
            f"{'s' if len(sessions) != 1 else ''} logged</p>"
            f'<p data-slot="text" class="text-sm/[1.4] font-normal '
            f'text-secondary-gray">Total volume {volume} lbs</p></div>'
        )
        body = body.replace(
            "No workouts found in this period. Start logging to see your "
            "insights!",
            summary,
            1,
        )
        return HTMLResponse(body)
    return doc


BODY_STAT_SLUGS = {
    "Weight": "weight",
    "Body Fat": "fat_percentage",
    "Waist": "waist",
    "Chest": "chest",
    "Arms": "arms",
    "Forearms": "forearms",
    "Shoulders": "shoulders",
    "Hips": "hips",
    "Thighs": "thighs",
    "Calves": "calves",
    "Neck": "neck",
    "Height": "height",
}
BODY_STAT_ICONS = {
    "Weight": "weight",
    "Body Fat": "body_fat",
}


def _stat_ctx(row: dict) -> dict:
    slug = BODY_STAT_SLUGS.get(row["stat"], _slugify(row["stat"]))
    icon = BODY_STAT_ICONS.get(row["stat"], slug)
    current = row["current_value"]
    goal = row["goal_value"]
    progress = 0
    if current is not None and goal is not None and goal:
        progress = max(0, min(100, round(100 * min(current, goal) /
                                         max(current, goal))))
    return {
        "stat": esc(row["stat"]),
        "slug": slug,
        "icon": f"/my-jefit/body-stats/{icon}.svg",
        "unit": esc(row["unit"]),
        "current_display": _fmt_weight(current) if current is not None else "--",
        "goal_display": _fmt_weight(goal) if goal is not None else "--",
        "progress": progress,
        "progress_display": str(progress) if progress else "--",
    }


@app.get("/my-jefit/progress/body-stats", include_in_schema=False)
async def body_stats(request: Request):
    user, redirect = _member_guard(request)
    if redirect:
        return redirect
    stats = [_stat_ctx(row) for row in db.body_stats_for(user["id"])]
    return _render_member("progress-body-stats.html", user, stats=stats)


_MINIMAL_MEMBER_PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} - JEFIT</title>
<style>body{{font-family:-apple-system,'Segoe UI',sans-serif;margin:0;
background:#f7f9fd;color:#18202a}}main{{max-width:44rem;margin:4rem auto;
background:#fff;border:1px solid #e4e8f0;border-radius:12px;padding:2rem}}
h1{{font-size:1.5rem}}a{{color:#1c5fc9}}label{{display:block;margin-top:.8rem;
font-size:.85rem;color:#4f566b}}input{{display:block;margin-top:.25rem;
padding:.5rem;border:1px solid #cdd5e1;border-radius:6px}}button{{margin-top:1rem;
background:#1c5fc9;color:#fff;border:0;border-radius:6px;padding:.6rem 1.2rem}}
table{{border-collapse:collapse;margin-top:1rem}}td,th{{border-bottom:1px solid
#e4e8f0;padding:.4rem .8rem;text-align:left;font-size:.9rem}}</style>
</head><body><main>{body}</main></body></html>
"""


@app.get("/my-jefit/progress/body-stats/{slug}", include_in_schema=False)
async def body_stat_detail(request: Request, slug: str):
    user, redirect = _member_guard(request)
    if redirect:
        return redirect
    stat = next(
        (row for row in db.body_stats_for(user["id"])
         if BODY_STAT_SLUGS.get(row["stat"], _slugify(row["stat"])) == slug),
        None,
    )
    if stat is None:
        return _not_found()
    # Per-stat depth page was unreachable evidence (EA1 unavailable); this is
    # a disclosed minimal clone-local implementation with real edit behavior.
    body = (
        f"<h1>{esc(stat['stat'])}</h1>"
        f"<p>Current: {esc(stat['current_value'] or '--')} "
        f"{esc(stat['unit'])} &middot; Goal: "
        f"{esc(stat['goal_value'] or '--')} {esc(stat['unit'])}</p>"
        '<form method="post" action="/my-jefit/progress/body-stats/'
        f'{esc(slug)}">'
        f"<label>Current value ({esc(stat['unit'])})"
        f'<input name="current" value="{esc(stat["current_value"] or "")}">'
        "</label>"
        f"<label>Goal value ({esc(stat['unit'])})"
        f'<input name="goal" value="{esc(stat["goal_value"] or "")}">'
        "</label>"
        '<button type="submit">Edit stat</button></form>'
        '<p><a href="/my-jefit/progress/body-stats">Back to Body Stats</a></p>'
    )
    return HTMLResponse(
        _MINIMAL_MEMBER_PAGE.format(title=esc(stat["stat"]), body=body)
    )


@app.post("/my-jefit/progress/body-stats/{slug}", include_in_schema=False)
async def body_stat_update(request: Request, slug: str):
    user, redirect = _member_guard(request)
    if redirect:
        return redirect
    stat = next(
        (row for row in db.body_stats_for(user["id"])
         if BODY_STAT_SLUGS.get(row["stat"], _slugify(row["stat"])) == slug),
        None,
    )
    if stat is None:
        return _not_found()
    form = await request.form()

    def number(name: str) -> float | None:
        raw = str(form.get(name, "")).strip()
        if not raw:
            return None
        try:
            value = float(raw)
        except ValueError:
            return None
        return value if 0 <= value <= 2000 else None

    db.update_body_stat(user["id"], stat["stat"], number("current"),
                        number("goal"))
    return RedirectResponse(
        f"/my-jefit/progress/body-stats/{slug}", status_code=302
    )


@app.get("/my-jefit/progress/exercise/{exercise_id}", include_in_schema=False)
async def exercise_progress(request: Request, exercise_id: str):
    user, redirect = _member_guard(request)
    if redirect:
        return redirect
    try:
        entry = db.exercise_by_id(int(exercise_id))
    except ValueError:
        entry = None
    if entry is None:
        return _not_found()
    rows = []
    for session in db.sessions_for_user(user["id"]):
        for item in session["sets"]:
            if item["exercise_id"] == entry["id"]:
                rows.append(
                    f"<tr><td>{esc(session['session_date'])}</td>"
                    f"<td>{item['set_index']}</td>"
                    f"<td>{_fmt_weight(item['weight_lbs'])} lbs x "
                    f"{item['reps']}</td></tr>"
                )
    table = (
        "<table><tr><th>Date</th><th>Set</th><th>Result</th></tr>"
        + "".join(rows)
        + "</table>"
        if rows
        else "<p>No logged sets yet.</p>"
    )
    body = (
        f"<h1>{esc(entry['name'])} progress</h1>{table}"
        '<p><a href="/my-jefit/progress/history">Back to history</a></p>'
    )
    return HTMLResponse(
        _MINIMAL_MEMBER_PAGE.format(title=esc(entry["name"]), body=body)
    )


# ---- workouts / plans ----


def _plan_ctx(plan: dict) -> dict:
    day_count = len(plan["days"])
    return {
        "id": plan["id"],
        "name": esc(plan["name"]),
        "days_label": f"{day_count} day" if day_count == 1 else
        f"{day_count} days",
        "focus": esc(plan["focus"]),
        "level": esc(plan["level"]),
    }


@app.get("/my-jefit/workouts", include_in_schema=False)
async def workouts(request: Request):
    user, redirect = _member_guard(request)
    if redirect:
        return redirect
    plans = db.plans_for_user(user["id"])
    current = next(
        (p for p in plans if p["id"] == user["current_plan_id"]), None
    )
    return _render_member(
        "workouts.html",
        user,
        plans=[_plan_ctx(p) for p in plans],
        current=_plan_ctx(current) if current else None,
    )


@app.get("/my-jefit/workouts/edit", include_in_schema=False)
async def workouts_edit(request: Request):
    user, redirect = _member_guard(request)
    if redirect:
        return redirect
    raw = request.query_params.get("id", "")
    plan = db.plan_by_id(int(raw)) if raw.isdigit() else None
    if plan is None or plan["owner_user_id"] != user["id"]:
        return _not_found()
    days = []
    for day in plan["days"]:
        entries = []
        for entry in day["exercises"]:
            fixture = db.exercise_by_id(entry["exercise_id"]) or {}
            entries.append(
                {
                    "id": entry["id"],
                    "exercise_id": entry["exercise_id"],
                    "slug": fixture.get("slug", "exercise"),
                    "name": esc(entry["name"]),
                    "sets": entry["sets"],
                    "weight_display": _fmt_weight(entry["weight_lbs"]),
                    "reps": entry["reps"],
                    "rest_seconds": entry["rest_seconds"],
                    "srcset": fixture.get("srcset", ""),
                    "src": fixture.get("src", ""),
                }
            )
        days.append(
            {
                "id": day["id"],
                "position": day["position"],
                "title": esc(day["title"]),
                "exercises": entries,
            }
        )
    plan_ctx = {"id": plan["id"], "name": esc(plan["name"]), "days": days}
    return _render_member(
        "workouts-edit.html", user, plan=plan_ctx, library=_library_ctx()
    )


# ---- member exercises ----


@app.get("/my-jefit/exercises", include_in_schema=False)
async def member_exercises(request: Request):
    user, redirect = _member_guard(request)
    if redirect:
        return redirect
    return _render_member(
        "exercises-custom.html",
        user,
        custom_count=user["custom_exercise_count"],
    )


@app.get("/my-jefit/exercises/find", include_in_schema=False)
async def member_exercises_find(request: Request):
    user, redirect = _member_guard(request)
    if redirect:
        return redirect
    raw_page = request.query_params.get("page", "1")
    try:
        page = int(raw_page)
    except ValueError:
        page = 1
    entries = _CATALOG["exercises"]
    pages = max(1, -(-len(entries) // PAGE_SIZE))
    page = min(max(page, 1), pages)
    chunk = entries[(page - 1) * PAGE_SIZE : page * PAGE_SIZE]
    return _render_member(
        "exercises-database.html",
        user,
        exercises=[_exercise_ctx(e) for e in chunk],
        count=len(entries),
        pagination=_pagination("/my-jefit/exercises/find", page, pages),
        catalog_json=_client_catalog_json(),
    )


@app.get("/my-jefit/exercises/{exercise_id}/{slug}", include_in_schema=False)
async def member_exercise_detail(request: Request, exercise_id: str,
                                 slug: str):
    user, redirect = _member_guard(request)
    if redirect:
        return redirect
    # the captured member detail document is served for its captured entity;
    # other ids render the public detail template (member chrome depth was
    # captured only for this entity)
    if not exercise_id.isdigit():
        return _not_found()
    entry = db.exercise_by_id(int(exercise_id))
    if entry is None:
        return _not_found()
    if exercise_id == "2":  # the captured member-detail entity (bench press)
        return _render_member("exercise-detail.html", user)
    return HTMLResponse(_render_exercise_detail(entry))


# ---- settings ----


@app.get("/my-jefit/settings", include_in_schema=False)
async def settings_page(request: Request):
    user, redirect = _member_guard(request)
    if redirect:
        return redirect
    plan_label = {
        "monthly": "JEFIT Elite Monthly", "yearly": "JEFIT Elite Annual",
    }.get(user["membership_plan"] or "", "JEFIT Elite")
    membership_line = (
        f"{plan_label} · renews on {user['membership_renews_on']}"
        if user["membership_renews_on"]
        else plan_label
    )
    settings_json = json.dumps(
        {
            "birthday": user["birthday"],
            "gender": user["gender"],
            "unit_system": user["unit_system"],
            "workout_level": user["workout_level"],
            "top_goal": user["top_goal"],
            "privacy": json.loads(user["privacy_json"]),
            "email_prefs": json.loads(user["email_prefs_json"]),
            "email_verified": bool(user["email_verified"]),
            "account_type": "Free" if user["account_type"] == "free"
            else "Elite",
        }
    ).replace("</", "<\\/")
    return _render_member(
        "settings.html",
        user,
        verification_label="Verified" if user["email_verified"] else
        "Unverified",
        email_verified=bool(user["email_verified"]),
        account_type="Free" if user["account_type"] == "free" else "Elite",
        membership_line=esc(membership_line),
        settings_json=settings_json,
    )


@app.get("/my-jefit/settings/export.csv", include_in_schema=False)
async def settings_export(request: Request):
    user, redirect = _member_guard(request)
    if redirect:
        return redirect
    return PlainTextResponse(
        db.export_csv(user["id"]),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="jefit-data.csv"'},
    )


# ---------------------------------------------------------------------------
# member JSON API (clone runtime)
# ---------------------------------------------------------------------------


async def _json_body(request: Request) -> dict:
    try:
        body = await request.json()
    except Exception:
        return {}
    return body if isinstance(body, dict) else {}


def _api_user(request: Request):
    user = current_user(request)
    if user is None:
        return None, JSONResponse({"error": "unauthorized"}, status_code=401)
    return user, None


@app.post("/api/plans", include_in_schema=False)
async def api_create_plan(request: Request) -> JSONResponse:
    user, error = _api_user(request)
    if error:
        return error
    plan = db.create_plan(user["id"])
    return JSONResponse({"id": plan["id"], "name": plan["name"]},
                        status_code=201)


def _plan_authz(request: Request, plan_id: int):
    user, error = _api_user(request)
    if error:
        return None, error
    owner = db.plan_owner(plan_id)
    if owner is None:
        return None, JSONResponse({"error": "not-found"}, status_code=404)
    if owner != user["id"]:
        return None, JSONResponse({"error": "forbidden"}, status_code=403)
    return user, None


@app.post("/api/plans/{plan_id}/name", include_in_schema=False)
async def api_rename_plan(request: Request, plan_id: int) -> JSONResponse:
    user, error = _plan_authz(request, plan_id)
    if error:
        return error
    body = await _json_body(request)
    db.rename_plan(plan_id, str(body.get("name", "")))
    plan = db.plan_by_id(plan_id)
    # empty name silently keeps the prior name (source quirk)
    return JSONResponse({"id": plan_id, "name": plan["name"]})


@app.post("/api/plans/{plan_id}/meta", include_in_schema=False)
async def api_plan_meta(request: Request, plan_id: int) -> JSONResponse:
    user, error = _plan_authz(request, plan_id)
    if error:
        return error
    body = await _json_body(request)
    fields = {
        key: str(body[key])
        for key in ("focus", "level", "day_tag", "description")
        if key in body
    }
    if fields:
        db.update_plan_meta(plan_id, **fields)
    return JSONResponse({"id": plan_id, **fields})


@app.post("/api/plans/{plan_id}/days", include_in_schema=False)
async def api_add_day(request: Request, plan_id: int) -> JSONResponse:
    user, error = _plan_authz(request, plan_id)
    if error:
        return error
    day_id = db.add_day(plan_id)
    return JSONResponse({"id": day_id}, status_code=201)


@app.post("/api/plans/{plan_id}/delete", include_in_schema=False)
async def api_delete_plan(request: Request, plan_id: int) -> JSONResponse:
    user, error = _plan_authz(request, plan_id)
    if error:
        return error
    db.delete_plan(plan_id)
    return JSONResponse({"deleted": True})


@app.post("/api/plans/{plan_id}/set-current", include_in_schema=False)
async def api_set_current(request: Request, plan_id: int) -> JSONResponse:
    user, error = _plan_authz(request, plan_id)
    if error:
        return error
    db.update_user_fields(user["id"], current_plan_id=plan_id)
    return JSONResponse({"current": plan_id})


@app.post("/api/days/{day_id}/exercises", include_in_schema=False)
async def api_add_exercise(request: Request, day_id: int) -> JSONResponse:
    user, error = _api_user(request)
    if error:
        return error
    plan_id, owner = db.day_plan_owner(day_id)
    if plan_id is None:
        return JSONResponse({"error": "not-found"}, status_code=404)
    if owner != user["id"]:
        return JSONResponse({"error": "forbidden"}, status_code=403)
    body = await _json_body(request)
    try:
        exercise_id = int(body.get("exercise_id", 0))
    except (TypeError, ValueError):
        return JSONResponse({"error": "exercise_id"}, status_code=422)
    entry = db.add_day_exercise(day_id, exercise_id)
    if entry is None:
        return JSONResponse({"error": "not-found"}, status_code=404)
    return JSONResponse(entry, status_code=201)


@app.post("/api/entries/{entry_id}", include_in_schema=False)
async def api_update_entry(request: Request, entry_id: int) -> JSONResponse:
    user, error = _api_user(request)
    if error:
        return error
    plan_id, owner = db.entry_plan_owner(entry_id)
    if plan_id is None:
        return JSONResponse({"error": "not-found"}, status_code=404)
    if owner != user["id"]:
        return JSONResponse({"error": "forbidden"}, status_code=403)
    body = await _json_body(request)
    fields = {
        key: body[key]
        for key in ("sets", "weight_lbs", "reps", "rest_seconds", "position")
        if key in body
    }
    try:
        if fields:
            db.update_day_exercise(entry_id, **fields)
    except (TypeError, ValueError) as exc:
        return JSONResponse({"error": str(exc)}, status_code=422)
    return JSONResponse({"id": entry_id, **fields})


@app.post("/api/entries/{entry_id}/delete", include_in_schema=False)
async def api_delete_entry(request: Request, entry_id: int) -> JSONResponse:
    user, error = _api_user(request)
    if error:
        return error
    plan_id, owner = db.entry_plan_owner(entry_id)
    if plan_id is None:
        return JSONResponse({"error": "not-found"}, status_code=404)
    if owner != user["id"]:
        return JSONResponse({"error": "forbidden"}, status_code=403)
    db.remove_day_exercise(entry_id)
    return JSONResponse({"deleted": True})


@app.post("/api/sessions", include_in_schema=False)
async def api_create_session(request: Request) -> JSONResponse:
    user, error = _api_user(request)
    if error:
        return error
    body = await _json_body(request)
    day = str(body.get("date", db.SEED_DAY))
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", day):
        return JSONResponse({"error": "date"}, status_code=422)
    start = str(body.get("start", "09:00"))[:5]
    end = str(body.get("end", "10:00"))[:5]
    session_id = db.create_session(user["id"], day, start, end)
    return JSONResponse({"id": session_id}, status_code=201)


@app.post("/api/sessions/{session_id}/sets", include_in_schema=False)
async def api_log_set(request: Request, session_id: int) -> JSONResponse:
    user, error = _api_user(request)
    if error:
        return error
    owner = db.session_owner(session_id)
    if owner is None:
        return JSONResponse({"error": "not-found"}, status_code=404)
    if owner != user["id"]:
        return JSONResponse({"error": "forbidden"}, status_code=403)
    body = await _json_body(request)
    try:
        exercise_id = int(body.get("exercise_id", 0))
        weight = float(body.get("weight_lbs", 25.0))
        reps = int(body.get("reps", 8))
    except (TypeError, ValueError):
        return JSONResponse({"error": "fields"}, status_code=422)
    if not (0 < weight <= 2000 and 0 < reps <= 500):
        return JSONResponse({"error": "range"}, status_code=422)
    logged = db.log_set(session_id, exercise_id, weight, reps)
    if logged is None:
        return JSONResponse({"error": "not-found"}, status_code=404)
    return JSONResponse(logged, status_code=201)


@app.post("/api/sets/{set_id}", include_in_schema=False)
async def api_update_set(request: Request, set_id: int) -> JSONResponse:
    user, error = _api_user(request)
    if error:
        return error
    owner = db.set_owner(set_id)
    if owner is None:
        return JSONResponse({"error": "not-found"}, status_code=404)
    if owner != user["id"]:
        return JSONResponse({"error": "forbidden"}, status_code=403)
    body = await _json_body(request)
    try:
        weight = float(body.get("weight_lbs"))
        reps = int(body.get("reps"))
    except (TypeError, ValueError):
        return JSONResponse({"error": "fields"}, status_code=422)
    db.update_logged_set(set_id, weight, reps)
    return JSONResponse({"id": set_id, "weight_lbs": weight, "reps": reps})


@app.post("/api/posts", include_in_schema=False)
async def api_create_post(request: Request) -> JSONResponse:
    user, error = _api_user(request)
    if error:
        return error
    body = await _json_body(request)
    feed = str(body.get("feed", "qa"))
    text = str(body.get("body", "")).strip()
    if not text:
        return JSONResponse({"error": "body"}, status_code=422)
    try:
        post_id = db.create_post(feed, user, str(body.get("title", "")), text)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=422)
    return JSONResponse({"id": post_id}, status_code=201)


@app.post("/api/custom-exercises", include_in_schema=False)
async def api_custom_exercise(request: Request) -> JSONResponse:
    user, error = _api_user(request)
    if error:
        return error
    body = await _json_body(request)
    try:
        created = db.create_custom_exercise(user["id"],
                                            str(body.get("name", "")))
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=422)
    return JSONResponse(created, status_code=201)


@app.post("/api/settings/profile", include_in_schema=False)
async def api_settings_profile(request: Request) -> JSONResponse:
    user, error = _api_user(request)
    if error:
        return error
    body = await _json_body(request)
    fields = {}
    if "birthday" in body:
        raw = str(body["birthday"])[:10]
        if raw and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
            return JSONResponse({"error": "birthday"}, status_code=422)
        fields["birthday"] = raw
    if "gender" in body:
        fields["gender"] = str(body["gender"])[:20]
    if "unit_system" in body:
        if body["unit_system"] not in ("Imperial", "Metric"):
            return JSONResponse({"error": "unit_system"}, status_code=422)
        fields["unit_system"] = body["unit_system"]
    if "workout_level" in body:
        fields["workout_level"] = str(body["workout_level"])[:20]
    if "top_goal" in body:
        if body["top_goal"] not in ("Maintaining", "Bulking", "Cutting",
                                    "Strength"):
            return JSONResponse({"error": "top_goal"}, status_code=422)
        fields["top_goal"] = body["top_goal"]
    if fields:
        db.update_user_fields(user["id"], **fields)
    return JSONResponse({"saved": sorted(fields)})


@app.post("/api/settings/privacy", include_in_schema=False)
async def api_settings_privacy(request: Request) -> JSONResponse:
    user, error = _api_user(request)
    if error:
        return error
    body = await _json_body(request)
    privacy = json.loads(user["privacy_json"])
    prefs = json.loads(user["email_prefs_json"])
    choices = {"Everyone", "Members", "Friends", "Myself Only"}
    for key, value in (body.get("privacy") or {}).items():
        if key in privacy and value in choices:
            privacy[key] = value
    for key, value in (body.get("email_prefs") or {}).items():
        if key in prefs:
            prefs[key] = bool(value)
    db.update_user_fields(
        user["id"],
        privacy_json=json.dumps(privacy),
        email_prefs_json=json.dumps(prefs),
    )
    return JSONResponse({"privacy": privacy, "email_prefs": prefs})


@app.post("/api/settings/username", include_in_schema=False)
async def api_settings_username(request: Request) -> JSONResponse:
    user, error = _api_user(request)
    if error:
        return error
    body = await _json_body(request)
    username = str(body.get("username", "")).strip()
    if not re.fullmatch(r"[A-Za-z0-9_.-]{3,32}", username):
        return JSONResponse({"error": "username"}, status_code=422)
    try:
        db.update_user_fields(user["id"], username=username)
    except Exception:
        return JSONResponse({"error": "taken"}, status_code=409)
    return JSONResponse({"username": username})


@app.post("/api/settings/resend-verification", include_in_schema=False)
async def api_resend_verification(request: Request) -> JSONResponse:
    user, error = _api_user(request)
    if error:
        return error
    if user["email_verified"]:
        return JSONResponse({"status": "already-verified"})
    return JSONResponse(db.issue_verification_mail(user))


@app.post("/api/settings/verify-email", include_in_schema=False)
async def api_verify_email(request: Request) -> JSONResponse:
    user, error = _api_user(request)
    if error:
        return error
    body = await _json_body(request)
    if db.confirm_verification_code(user, str(body.get("code", ""))):
        return JSONResponse({"verified": True})
    return JSONResponse({"verified": False}, status_code=422)


@app.post("/api/settings/delete-data", include_in_schema=False)
async def api_delete_data(request: Request) -> JSONResponse:
    user, error = _api_user(request)
    if error:
        return error
    db.delete_user_data(user["id"])
    return JSONResponse({"deleted": "data"})


@app.post("/api/settings/delete-account", include_in_schema=False)
async def api_delete_account(request: Request) -> JSONResponse:
    user, error = _api_user(request)
    if error:
        return error
    db.delete_account(user)
    response = JSONResponse({"deleted": "account"})
    response.delete_cookie(_cookie_name(), path="/")
    return response


@app.get("/api/outbox", include_in_schema=False)
async def api_outbox(request: Request) -> JSONResponse:
    """Session-scoped local outbox view (never another session's mail)."""

    token = _session_token(request)
    if not token:
        return JSONResponse({"mail": []})
    mail = []
    for purpose in ("password-reset", "registration"):
        try:
            item = db.auth().local_mail_for_session(token, purpose=purpose)
        except Exception:
            item = None
        if item:
            mail.append(
                {
                    "purpose": purpose,
                    "recipient": item.get("recipient"),
                    "verification_code": item.get("verification_code"),
                    "status": item.get("status"),
                }
            )
    user = current_user(request)
    if user is not None:
        rendered = db.verification_mail_for(user)
        if rendered:
            mail.append(
                {
                    "purpose": "registration",
                    "recipient": rendered["recipient"],
                    "subject": rendered["subject"],
                    "text": rendered["text"],
                    "status": "LOCAL_ONLY",
                }
            )
    return JSONResponse({"mail": mail})


# ---------------------------------------------------------------------------
# membership checkout (task 539)
# ---------------------------------------------------------------------------


CHECKOUT_FACTS = {
    "yearly": {
        "price_today": "$52.49",
        "then_line": "Then $69.99 per year starting next year",
        "billed_label": "Billed annually",
        "list_price": "$69.99",
        "coupon": "25%OffFirstYear",
        "coupon_amount": "$17.50",
    },
    "monthly": {
        "price_today": "$12.99",
        "then_line": "Then $12.99 per month",
        "billed_label": "Billed monthly",
        "list_price": "$12.99",
        "coupon": None,
        "coupon_amount": "",
    },
}


def _checkout_page(user: dict, plan: str, error: str = "") -> HTMLResponse:
    facts = CHECKOUT_FACTS[plan]
    body = _env.get_template("checkout.html").render(
        plan=plan,
        email=esc(user["email"]),
        error=esc(error),
        **facts,
    )
    status = 402 if error else 200
    return HTMLResponse(body, status_code=status)


@app.get("/elite/checkout", include_in_schema=False)
async def elite_checkout(request: Request):
    user, redirect = _member_guard(request)
    if redirect:
        return redirect
    plan = request.query_params.get("sub", "yearly")
    if plan not in CHECKOUT_FACTS:
        plan = "yearly"
    return _checkout_page(user, plan)


@app.post("/elite/checkout", include_in_schema=False)
async def elite_checkout_submit(request: Request):
    user, redirect = _member_guard(request)
    if redirect:
        return redirect
    form = await request.form()
    payload = {key: str(value) for key, value in form.items()}
    plan = payload.get("sub", "yearly")
    if plan not in CHECKOUT_FACTS:
        plan = "yearly"
    try:
        db.reject_payment_keys(payload)
    except PaymentFieldRejected as exc:
        return _checkout_page(user, plan, str(exc))
    scenario_id = payload.get("scenario_id", "")
    if not scenario_id:
        return _checkout_page(
            user, plan, "Choose a simulated payment scenario to continue."
        )
    idempotency_key = payload.get("idempotency_key") or secrets.token_hex(12)
    if not re.fullmatch(r"[A-Za-z0-9_-]{8,64}", idempotency_key):
        idempotency_key = secrets.token_hex(12)
    try:
        result = db.purchase_membership(user, plan, scenario_id,
                                        idempotency_key)
    except PaymentError:
        return _checkout_page(
            user, plan, "The simulated payment scenario was not recognized."
        )
    if result["status"] == "approved":
        return RedirectResponse("/my-jefit/settings?upgraded=1",
                                status_code=303)
    if result["status"] == "retryable":
        return _checkout_page(
            user,
            plan,
            "The simulated payment could not be completed. Please try again.",
        )
    return _checkout_page(
        user, plan, "Your simulated payment was declined. No charge was "
        "recorded — choose another scenario to retry."
    )


if __name__ == "__main__":  # pragma: no cover - manual/offline start
    # ACCEPTANCE.md step 3 starts the clone with `python app.py`; the
    # deployment descriptor and the diagnostics use the equivalent
    # `uvicorn app:app`. HOST/PORT honour the Harbor runtime contract.
    import os

    import uvicorn

    uvicorn.run(
        app,
        host=os.environ.get("HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", "10000")),
        log_level="warning",
    )
