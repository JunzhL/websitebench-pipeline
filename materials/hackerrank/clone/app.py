"""Stateful HackerRank offline clone served from local files and SQLite."""

from __future__ import annotations

import hmac
import html
import os
import re
import sqlite3
import sys
import urllib.parse
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from starlette.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

runtime_data_dir = os.environ.get("WEBSITEBENCH_DATA_DIR")
if runtime_data_dir and "WEBSITEBENCH_SITE_BACKEND_DATABASE" not in os.environ:
    os.environ["WEBSITEBENCH_SITE_BACKEND_DATABASE"] = str(
        Path(runtime_data_dir).resolve() / "hackerrank.sqlite3"
    )

from backend import domain  # noqa: E402
from backend.site_backend_integration import open_site_services  # noqa: E402
from websitebench.local_clone_auth import (  # noqa: E402
    AuthConflict,
    AuthError,
    AuthRateLimited,
    AuthRejected,
    AuthValidationError,
)

SITE_ID = "hackerrank"
BACKEND, AUTH = open_site_services()
COOKIE = BACKEND.session_cookie
COOKIE_NAME = str(COOKIE["name"])
ADMIN_TOKEN = os.environ.get(
    "WEBSITEBENCH_HACKERRANK_ADMIN_TOKEN", "hackerrank-local-admin"
)
DEMO_ACCOUNT = {
    "subject_id": domain.DEMO_SUBJECT,
    "email": "learner@hackerrank.local",
    "display_name": "Demo Learner",
    "password": "WebsiteBench!2026",
}
AUTH.seed_account(**DEMO_ACCOUNT)

CHALLENGES = [
    {"slug": "solve-me-first", "title": "Solve Me First", "difficulty": "Easy", "topic": "Algorithms", "category": "Warmup", "success": 98, "points": 1},
    {"slug": "simple-array-sum", "title": "Simple Array Sum", "difficulty": "Easy", "topic": "Algorithms", "category": "Warmup", "success": 94, "points": 10},
    {"slug": "a-very-big-sum", "title": "A Very Big Sum", "difficulty": "Easy", "topic": "Algorithms", "category": "Warmup", "success": 96, "points": 10},
    {"slug": "compare-the-triplets", "title": "Compare the Triplets", "difficulty": "Easy", "topic": "Algorithms", "category": "Implementation", "success": 91, "points": 10},
    {"slug": "js10-hello-world", "title": "Day 0: Hello, World!", "difficulty": "Easy", "topic": "JavaScript", "category": "10 Days of JavaScript", "success": 97, "points": 10},
    {"slug": "python-lists", "title": "Lists", "difficulty": "Medium", "topic": "Python", "category": "Basic Data Types", "success": 89, "points": 10},
    {"slug": "sql-select-all", "title": "Select All", "difficulty": "Easy", "topic": "SQL", "category": "Basic Select", "success": 99, "points": 10},
]
CHALLENGE_BY_SLUG = {item["slug"]: item for item in CHALLENGES}

STARTERS = {
    "python3": "def solveMeFirst(a, b):\n    # Write your code here\n    return 0\n",
    "javascript": "function solveMeFirst(a, b) {\n    // Write your code here\n    return 0;\n}\n",
    "java15": "public static int solveMeFirst(int a, int b) {\n    return 0;\n}\n",
}

CONTENT_SECURITY_POLICY = (
    "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
    "script-src 'self'; font-src 'self' data:; connect-src 'self'; "
    "frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
)

app = FastAPI(title="HackerRank offline clone", docs_url=None, redoc_url=None, openapi_url=None)
app.mount("/static", StaticFiles(directory=str(ROOT / "static")), name="static")


def esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def quote(value: object) -> str:
    return urllib.parse.quote(str(value), safe="")


async def form_data(request: Request) -> dict[str, str]:
    if "application/x-www-form-urlencoded" not in request.headers.get("content-type", ""):
        return {}
    parsed = urllib.parse.parse_qs(
        (await request.body()).decode("utf-8", "replace"), keep_blank_values=True
    )
    return {key: values[-1] for key, values in parsed.items() if values}


def session_subject(request: Request) -> str | None:
    account = (getattr(request.state, "session", None) or {}).get("account") or {}
    subject = account.get("subject_id")
    return str(subject) if subject else None


def session_account(request: Request) -> dict[str, Any] | None:
    account = (getattr(request.state, "session", None) or {}).get("account")
    return dict(account) if isinstance(account, dict) else None


def profile_for_subject(subject: str) -> dict[str, Any] | None:
    with BACKEND.lifecycle.connection() as connection:
        row = connection.execute(
            "SELECT * FROM hr_profiles WHERE subject_id=?", (subject,)
        ).fetchone()
    return dict(row) if row else None


def nav(request: Request) -> str:
    account = session_account(request)
    if account:
        actions = (
            "<a href='/dashboard'>Dashboard</a><a href='/profile'>Profile</a>"
            "<form action='/auth/logout' method='post'><button class='link-button' type='submit'>Log out</button></form>"
        )
    else:
        actions = "<a href='/auth/login'>Log in</a><a class='button primary' href='/auth/signup'>Sign up</a>"
    return (
        "<header class='topbar'><a class='brand' href='/' aria-label='HackerRank home'>"
        "<span class='brand-mark'>&lt;/&gt;</span><span>HackerRank</span></a>"
        "<nav><a href='/domains'>Prepare</a><a href='/contests'>Contests</a><a href='/support'>Support</a></nav>"
        f"<div class='top-actions'>{actions}</div></header>"
    )


def document(title: str, body: str) -> str:
    return (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>{esc(title)} | HackerRank</title>"
        "<link rel='stylesheet' href='/static/site.css'>"
        "<script src='/static/site.js' defer></script></head>"
        f"<body>{body}</body></html>"
    )


def page_response(
    request: Request,
    title: str,
    content: str,
    *,
    status_code: int = 200,
    wide: bool = False,
    headers: dict[str, str] | None = None,
) -> HTMLResponse:
    notice = request.query_params.get("notice", "")
    error = request.query_params.get("error", "")
    flash = ""
    if notice:
        flash = f"<div class='flash success' role='status'>{esc(notice)}</div>"
    elif error:
        flash = f"<div class='flash' role='alert'>{esc(error)}</div>"
    width = "wide" if wide else ""
    return HTMLResponse(
        document(title, nav(request) + f"<main class='page {width}'>{flash}{content}</main>"),
        status_code=status_code,
        headers=headers,
    )


def auth_page(
    request: Request,
    title: str,
    fields: str,
    action: str,
    button: str,
    *,
    message: str = "",
    retry_after: int = 0,
) -> HTMLResponse:
    banner = f"<div class='flash' role='alert'>{esc(message)}</div>" if message else ""
    retry = f" data-retry-after='{retry_after}'" if retry_after else ""
    body = (
        "<section class='auth-shell'><div class='form-card'>"
        f"<h1>{esc(title)}</h1>{banner}<form action='{action}' method='post' data-single-submit{retry}>"
        f"{fields}<button class='primary full' type='submit'>{esc(button)}</button>"
        "<span class='muted small' data-cooldown-label></span></form></div></section>"
    )
    headers = {"Retry-After": str(retry_after)} if retry_after else None
    return page_response(request, title, body, headers=headers)


def challenge_or_none(slug: str) -> dict[str, Any] | None:
    item = CHALLENGE_BY_SLUG.get(slug)
    return dict(item) if item else None


@app.middleware("http")
async def local_runtime(request: Request, call_next):
    incoming = request.cookies.get(COOKIE_NAME)
    token, session = AUTH.ensure_session(incoming)
    request.state.session_token = token
    request.state.session = session
    response = await call_next(request)
    outgoing = getattr(request.state, "rotated_session_token", token)
    if outgoing != incoming:
        response.set_cookie(
            COOKIE_NAME,
            outgoing,
            secure=bool(COOKIE["secure"]),
            httponly=bool(COOKIE["httponly"]),
            samesite=str(COOKIE["samesite"]),
            path=str(COOKIE["path"]),
        )
    response.headers["Content-Security-Policy"] = CONTENT_SECURITY_POLICY
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/healthz", include_in_schema=False)
async def healthz() -> JSONResponse:
    return JSONResponse({"ok": True, "site_id": SITE_ID})


@app.get("/__websitebench/health", include_in_schema=False)
async def websitebench_health() -> Response:
    return Response('{"status":"ok"}', media_type="application/json")


@app.post("/__admin/reset", include_in_schema=False)
async def admin_reset(request: Request) -> JSONResponse:
    if not hmac.compare_digest(
        request.headers.get("X-WebsiteBench-Admin-Token", ""), ADMIN_TOKEN
    ):
        return JSONResponse({"error": "forbidden"}, status_code=403)
    AUTH.reset_site_state(site_reset=domain.reset, seed_accounts=[DEMO_ACCOUNT])
    request.state.rotated_session_token = AUTH.create_anonymous_session()
    return JSONResponse({"reset": True, "site_id": SITE_ID})


@app.get("/", include_in_schema=False)
async def home(request: Request) -> HTMLResponse:
    content = """
    <section class='hero'>
      <span class='eyebrow'>Practice. Learn. Improve.</span>
      <h1>Build coding skills with hands-on challenges</h1>
      <p>Choose a track, solve problems in the editor, and follow your local progress.</p>
      <div class='actions'><a class='button primary' href='/domains'>Start practicing</a><a class='button' href='/auth/signup'>Create an account</a></div>
    </section>
    <section><div class='section-heading'><div><span class='eyebrow'>Preparation</span><h2>Pick a path and begin</h2></div></div>
      <div class='cards three'>
        <article class='card'><span class='icon-box'>{ }</span><h3>Algorithms</h3><p>Warmups, implementation, sorting, strings, and data structures.</p><a href='/domains?topic=Algorithms'>Explore algorithms</a></article>
        <article class='card'><span class='icon-box'>JS</span><h3>10 Days of JavaScript</h3><p>Short exercises covering syntax, functions, classes, and more.</p><a href='/domains/tutorials/10-days-of-javascript'>Open the tutorial</a></article>
        <article class='card'><span class='icon-box'>SQL</span><h3>SQL practice</h3><p>Query seeded tables with focused exercises from basic selects onward.</p><a href='/domains?topic=SQL'>Explore SQL</a></article>
      </div>
    </section>
    <section class='dark-callout'><div><span class='eyebrow'>Your workspace</span><h2>Keep drafts and submission history together</h2><p>Sign in to save challenges, run fixture tests, submit solutions, and review earlier versions.</p></div><a class='button light' href='/dashboard'>Open dashboard</a></section>
    """
    return page_response(request, "Practice coding", content)


def challenge_cards(items: list[dict[str, Any]], subject: str | None) -> str:
    if not items:
        return (
            "<div class='empty-state' data-no-results><h2>No challenges found</h2>"
            "<p>Clear a filter or search for another topic.</p>"
            "<a class='button' href='/domains'>Browse all challenges</a></div>"
        )
    solved: set[str] = set()
    saved: set[str] = set()
    if subject:
        with BACKEND.lifecycle.connection() as connection:
            solved = {
                str(row[0])
                for row in connection.execute(
                    "SELECT DISTINCT challenge_slug FROM hr_submissions WHERE subject_id=? AND status='Accepted'",
                    (subject,),
                ).fetchall()
            }
            saved = {
                str(row[0])
                for row in connection.execute(
                    "SELECT challenge_slug FROM hr_saved_challenges WHERE subject_id=?",
                    (subject,),
                ).fetchall()
            }
    rows = []
    for item in items:
        status = "Solved" if item["slug"] in solved else "Unsolved"
        bookmark = "Saved" if item["slug"] in saved else ""
        rows.append(
            "<article class='challenge-row' data-challenge-card>"
            f"<div><div class='meta'><span class='difficulty {str(item['difficulty']).lower()}'>{esc(item['difficulty'])}</span>"
            f"<span>{esc(item['topic'])}</span><span>{esc(item['category'])}</span></div>"
            f"<h3><a href='/challenges/{quote(item['slug'])}/problem'>{esc(item['title'])}</a></h3>"
            f"<p>{item['success']}% success rate · {item['points']} points</p></div>"
            f"<div class='row-status'><span class='status'>{status}</span><span>{bookmark}</span>"
            f"<a class='button compact' href='/challenges/{quote(item['slug'])}/problem'>Solve challenge</a></div></article>"
        )
    return "<div class='challenge-list'>" + "".join(rows) + "</div>"


@app.get("/domains", include_in_schema=False)
async def domains(request: Request) -> HTMLResponse:
    query = request.query_params.get("search", "").strip()
    difficulty = request.query_params.get("difficulty", "").strip()
    topic = request.query_params.get("topic", "").strip()
    status = request.query_params.get("status", "").strip()
    subject = session_subject(request)
    items = CHALLENGES[:]
    if query:
        lowered = query.lower()
        items = [item for item in items if lowered in f"{item['title']} {item['topic']} {item['category']}".lower()]
    if difficulty:
        items = [item for item in items if item["difficulty"] == difficulty]
    if topic:
        items = [item for item in items if item["topic"] == topic]
    if status and subject:
        with BACKEND.lifecycle.connection() as connection:
            solved = {
                str(row[0])
                for row in connection.execute(
                    "SELECT DISTINCT challenge_slug FROM hr_submissions WHERE subject_id=? AND status='Accepted'",
                    (subject,),
                ).fetchall()
            }
        items = [item for item in items if (item["slug"] in solved) == (status == "Solved")]
    content = (
        "<div class='breadcrumb'>Prepare / Practice</div><div class='section-heading'><div><h1>Practice challenges</h1>"
        "<p>Filter the local challenge catalog by topic, difficulty, or progress.</p></div></div>"
        "<form class='filter-bar' method='get' action='/domains'>"
        f"<input aria-label='Search challenges' name='search' type='search' value='{esc(query)}' placeholder='Search challenges'>"
        f"<select aria-label='Difficulty' name='difficulty'><option value=''>All difficulties</option><option{' selected' if difficulty == 'Easy' else ''}>Easy</option><option{' selected' if difficulty == 'Medium' else ''}>Medium</option></select>"
        f"<select aria-label='Topic' name='topic'><option value=''>All topics</option><option{' selected' if topic == 'Algorithms' else ''}>Algorithms</option><option{' selected' if topic == 'JavaScript' else ''}>JavaScript</option><option{' selected' if topic == 'Python' else ''}>Python</option><option{' selected' if topic == 'SQL' else ''}>SQL</option></select>"
        f"<select aria-label='Status' name='status'><option value=''>Any status</option><option{' selected' if status == 'Solved' else ''}>Solved</option><option{' selected' if status == 'Unsolved' else ''}>Unsolved</option></select>"
        "<button type='submit'>Apply filters</button></form>"
        + challenge_cards(items, subject)
    )
    return page_response(request, "Practice challenges", content, wide=True)


@app.get("/domains/tutorials/{track}", include_in_schema=False)
async def tutorial(request: Request, track: str) -> HTMLResponse:
    if track != "10-days-of-javascript":
        return not_found_response(request)
    item = CHALLENGE_BY_SLUG["js10-hello-world"]
    content = (
        "<div class='breadcrumb'><a href='/domains'>Prepare</a> / Tutorials</div>"
        "<section class='track-hero'><span class='eyebrow'>Learning plan</span><h1>10 Days of JavaScript</h1>"
        "<p>Work through one focused JavaScript challenge each day. Progress is stored only in this clone.</p>"
        f"<div class='progress'><span style='width:10%'></span></div><p>1 of 10 days complete</p></section>"
        "<h2>Challenges</h2>" + challenge_cards([dict(item)], session_subject(request))
    )
    return page_response(request, "10 Days of JavaScript", content)


@app.get("/contests", include_in_schema=False)
async def contests(request: Request) -> HTMLResponse:
    content = """
    <div class='breadcrumb'>Prepare / Contests</div><h1>Contests and assessments</h1>
    <div class='tabs'><button class='active' type='button'>Upcoming</button><button type='button'>Past</button></div>
    <div class='cards'><article class='card'><span class='status'>Practice contest</span><h2>Weekly Algorithms Sprint</h2><p>Starts Sep 5, 2026 · 90 minutes · 4 challenges</p><p>This is a browse-only local fixture. Joining an external contest is out of scope.</p></article>
    <article class='card'><span class='status'>Assessment preview</span><h2>Problem Solving Skills Test</h2><p>Review the format without starting a proctored or employer assessment.</p></article></div>
    """
    return page_response(request, "Contests", content)


@app.get("/support", include_in_schema=False)
async def support(request: Request) -> HTMLResponse:
    content = """
    <div class='breadcrumb'>Help / Support</div><h1>How can we help?</h1>
    <div class='cards three'>
      <article class='card'><h2>Practice challenges</h2><p>Find a track, understand filters, and return to available problems after an empty search.</p><a href='/domains'>Browse practice</a></article>
      <article class='card'><h2>Account access</h2><p>Use local sign-in, registration, or password recovery. No identity data leaves this clone.</p><a href='/auth/login'>Account help</a></article>
      <article class='card'><h2>Runs and submissions</h2><p>Review stdout, fixture test results, status, runtime, memory, and earlier solution versions.</p><a href='/challenges/solve-me-first/problem'>Open a challenge</a></article>
    </div>
    """
    return page_response(request, "Support", content)


def editor_source(subject: str | None, slug: str, language: str, load_id: int | None) -> tuple[str, str]:
    if subject and load_id:
        with BACKEND.lifecycle.connection() as connection:
            row = connection.execute(
                "SELECT source,language FROM hr_submissions WHERE submission_id=? AND subject_id=? AND challenge_slug=?",
                (load_id, subject, slug),
            ).fetchone()
        if row:
            return str(row["source"]), str(row["language"])
    if subject:
        with BACKEND.lifecycle.connection() as connection:
            row = connection.execute(
                "SELECT source,language FROM hr_drafts WHERE subject_id=? AND challenge_slug=?",
                (subject, slug),
            ).fetchone()
        if row:
            return str(row["source"]), str(row["language"])
    return STARTERS.get(language, STARTERS["python3"]), language


def problem_text(item: dict[str, Any]) -> str:
    if item["slug"] == "solve-me-first":
        return """
        <h2>Problem</h2><p>Complete the function <code>solveMeFirst</code> to compute the sum of two integers.</p>
        <h3>Function description</h3><p>The function accepts two integers, <code>a</code> and <code>b</code>, and returns their sum.</p>
        <h3>Input format</h3><p>The first line contains <code>a</code>. The second line contains <code>b</code>.</p>
        <h3>Output format</h3><p>Print or return the sum of the two integers.</p>
        <h3>Sample input</h3><pre>2\n3</pre><h3>Sample output</h3><pre>5</pre>
        <h3>Constraints</h3><p><code>1 ≤ a, b ≤ 1000</code></p>
        """
    return (
        f"<h2>Problem</h2><p>Complete the local {esc(item['title'])} practice task.</p>"
        "<h3>Examples</h3><pre>Input: fixture data\nOutput: expected result</pre>"
        "<h3>Constraints</h3><p>Inputs use deterministic local fixtures.</p>"
    )


@app.get("/challenges/{slug}/problem", include_in_schema=False)
async def challenge_problem(request: Request, slug: str) -> Response:
    item = challenge_or_none(slug)
    if item is None:
        return not_found_response(request)
    subject = session_subject(request)
    language = request.query_params.get("language", "python3")
    if language not in STARTERS:
        language = "python3"
    raw_load = request.query_params.get("load", "")
    load_id = int(raw_load) if raw_load.isdigit() else None
    source, language = editor_source(subject, slug, language, load_id)
    saved = False
    if subject:
        with BACKEND.lifecycle.connection() as connection:
            saved = connection.execute(
                "SELECT 1 FROM hr_saved_challenges WHERE subject_id=? AND challenge_slug=?",
                (subject, slug),
            ).fetchone() is not None
    auth_note = "" if subject else "<div class='inline-note'>Sign in to run, submit, save, and keep your draft.</div>"
    loaded_note = "<div class='flash success'>Previous submission loaded into the editor. Edit it before resubmitting.</div>" if load_id else ""
    content = (
        f"<div class='challenge-heading'><div><div class='breadcrumb'><a href='/domains'>Prepare</a> / {esc(item['topic'])}</div>"
        f"<h1>{esc(item['title'])}</h1><div class='meta'><span class='difficulty {str(item['difficulty']).lower()}'>{esc(item['difficulty'])}</span><span>{item['success']}% success</span><span>{item['points']} points</span></div></div>"
        f"<form action='/challenges/{quote(slug)}/save' method='post'><button type='submit'>{'Saved' if saved else 'Save challenge'}</button></form></div>"
        f"<div class='tabs'><a class='active' href='/challenges/{quote(slug)}/problem'>Problem</a>"
        f"<a href='/challenges/{quote(slug)}/submissions'>Submissions</a><a href='/challenges/{quote(slug)}/forum'>Discussions</a></div>"
        f"{auth_note}{loaded_note}<div class='workspace'><section class='problem-panel'>{problem_text(item)}</section>"
        "<section class='editor-panel'><div class='editor-toolbar'><label for='language'>Language</label>"
        f"<select id='language' name='language' form='solution-form'><option value='python3'{' selected' if language == 'python3' else ''}>Python 3</option><option value='javascript'{' selected' if language == 'javascript' else ''}>JavaScript</option><option value='java15'{' selected' if language == 'java15' else ''}>Java 15</option></select></div>"
        f"<form id='solution-form' action='/challenges/{quote(slug)}/run' method='post'>"
        f"<textarea class='code-editor' aria-label='Solution source' name='source' spellcheck='false'>{esc(source)}</textarea>"
        "<label for='custom_input'>Custom input</label><textarea id='custom_input' name='custom_input' class='custom-input' placeholder='2&#10;3'></textarea>"
        f"<div class='editor-actions'><button type='submit'>Run code</button><button class='primary' type='submit' formaction='/challenges/{quote(slug)}/submit'>Submit code</button></div></form>"
        "</section></div>"
    )
    return page_response(request, str(item["title"]), content, wide=True)


def judge(source: str, custom_input: str) -> dict[str, Any]:
    lowered = source.lower().replace(" ", "")
    if "syntax_error" in lowered or "compile_error" in lowered:
        return {"status": "Compilation Error", "stdout": "", "stderr": "Local fixture compiler found a syntax marker.", "summary": "0 of 3 tests passed", "runtime": 0, "accepted": False}
    accepted = any(marker in lowered for marker in ("returna+b", "returnb+a", "sum([a,b])", "print(a+b)"))
    values = re.findall(r"-?\d+", custom_input)
    stdout = str(int(values[0]) + int(values[1])) if len(values) >= 2 else ("5" if accepted else "0")
    return {
        "status": "Accepted" if accepted else "Wrong Answer",
        "stdout": stdout,
        "stderr": "",
        "summary": "3 of 3 tests passed" if accepted else "1 of 3 tests passed",
        "runtime": 18 if accepted else 21,
        "accepted": accepted,
    }


def signed_out_action(request: Request, slug: str) -> RedirectResponse | None:
    if session_subject(request):
        return None
    target = f"/challenges/{quote(slug)}/problem"
    return RedirectResponse(f"/auth/login?redirect={quote(target)}&error=Sign%20in%20to%20continue", status_code=303)


@app.post("/challenges/{slug}/save", include_in_schema=False)
async def save_challenge(request: Request, slug: str) -> Response:
    if challenge_or_none(slug) is None:
        return not_found_response(request)
    denied = signed_out_action(request, slug)
    if denied:
        return denied
    subject = session_subject(request) or ""
    with BACKEND.lifecycle.connection(transaction=True) as connection:
        existing = connection.execute(
            "SELECT 1 FROM hr_saved_challenges WHERE subject_id=? AND challenge_slug=?",
            (subject, slug),
        ).fetchone()
        if existing:
            connection.execute(
                "DELETE FROM hr_saved_challenges WHERE subject_id=? AND challenge_slug=?",
                (subject, slug),
            )
            message = "Challenge removed from saved list"
        else:
            connection.execute(
                "INSERT INTO hr_saved_challenges(subject_id,challenge_slug,saved_at) VALUES (?,?,?)",
                (subject, slug, domain.now()),
            )
            message = "Challenge saved"
    return RedirectResponse(
        f"/challenges/{quote(slug)}/problem?notice={quote(message)}", status_code=303
    )


@app.post("/challenges/{slug}/run", include_in_schema=False)
async def run_code(request: Request, slug: str) -> Response:
    item = challenge_or_none(slug)
    if item is None:
        return not_found_response(request)
    denied = signed_out_action(request, slug)
    if denied:
        return denied
    data = await form_data(request)
    source = data.get("source", "")
    language = data.get("language", "python3")
    custom_input = data.get("custom_input", "")
    if not source.strip():
        return RedirectResponse(
            f"/challenges/{quote(slug)}/problem?error=Enter%20a%20solution%20before%20running", status_code=303
        )
    outcome = judge(source, custom_input)
    subject = session_subject(request) or ""
    with BACKEND.lifecycle.connection(transaction=True) as connection:
        connection.execute(
            "INSERT INTO hr_drafts(subject_id,challenge_slug,language,source,custom_input,updated_at) VALUES (?,?,?,?,?,?) ON CONFLICT(subject_id,challenge_slug) DO UPDATE SET language=excluded.language,source=excluded.source,custom_input=excluded.custom_input,updated_at=excluded.updated_at",
            (subject, slug, language, source[:50000], custom_input[:5000], domain.now()),
        )
        cursor = connection.execute(
            "INSERT INTO hr_runs(subject_id,challenge_slug,language,source,custom_input,status,stdout,stderr,test_summary,runtime_ms,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (subject, slug, language, source[:50000], custom_input[:5000], outcome["status"], outcome["stdout"], outcome["stderr"], outcome["summary"], outcome["runtime"], domain.now()),
        )
    return RedirectResponse(f"/runs/{cursor.lastrowid}", status_code=303)


@app.get("/runs/{run_id}", include_in_schema=False)
async def run_result(request: Request, run_id: int) -> Response:
    subject = session_subject(request)
    if not subject:
        return RedirectResponse("/auth/login", status_code=303)
    with BACKEND.lifecycle.connection() as connection:
        row = connection.execute(
            "SELECT * FROM hr_runs WHERE run_id=? AND subject_id=?", (run_id, subject)
        ).fetchone()
    if row is None:
        return not_found_response(request)
    item = challenge_or_none(str(row["challenge_slug"])) or {"title": "Challenge"}
    content = (
        f"<div class='breadcrumb'><a href='/challenges/{quote(row['challenge_slug'])}/problem'>{esc(item['title'])}</a> / Run result</div>"
        f"<h1>Run result</h1><div class='result-card'><span class='result {esc(str(row['status']).lower().replace(' ', '-'))}'>{esc(row['status'])}</span>"
        f"<h2>{esc(row['test_summary'])}</h2><p>Runtime: {row['runtime_ms']} ms</p>"
        f"<h3>Stdout</h3><pre>{esc(row['stdout'] or '(no output)')}</pre>"
        f"<h3>Errors</h3><pre>{esc(row['stderr'] or '(none)')}</pre>"
        f"<a class='button primary' href='/challenges/{quote(row['challenge_slug'])}/problem'>Back to editor</a></div>"
    )
    return page_response(request, "Run result", content)


@app.post("/challenges/{slug}/submit", include_in_schema=False)
async def submit_code(request: Request, slug: str) -> Response:
    item = challenge_or_none(slug)
    if item is None:
        return not_found_response(request)
    denied = signed_out_action(request, slug)
    if denied:
        return denied
    data = await form_data(request)
    source = data.get("source", "")
    language = data.get("language", "python3")
    if not source.strip():
        return RedirectResponse(
            f"/challenges/{quote(slug)}/problem?error=Enter%20a%20solution%20before%20submitting", status_code=303
        )
    outcome = judge(source, data.get("custom_input", ""))
    subject = session_subject(request) or ""
    with BACKEND.lifecycle.connection(transaction=True) as connection:
        version = int(
            connection.execute(
                "SELECT COUNT(*) FROM hr_submissions WHERE subject_id=? AND challenge_slug=?",
                (subject, slug),
            ).fetchone()[0]
        ) + 1
        cursor = connection.execute(
            "INSERT INTO hr_submissions(subject_id,challenge_slug,language,source,status,score,runtime_ms,memory_kb,feedback,version,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (subject, slug, language, source[:50000], outcome["status"], item["points"] if outcome["accepted"] else 0, outcome["runtime"], 14832 if outcome["accepted"] else 14904, "All 3 local fixture tests passed." if outcome["accepted"] else "Local fixture test 2 expected 7 but received 0.", version, domain.now()),
        )
        connection.execute(
            "INSERT INTO hr_drafts(subject_id,challenge_slug,language,source,custom_input,updated_at) VALUES (?,?,?,?,?,?) ON CONFLICT(subject_id,challenge_slug) DO UPDATE SET language=excluded.language,source=excluded.source,custom_input=excluded.custom_input,updated_at=excluded.updated_at",
            (subject, slug, language, source[:50000], data.get("custom_input", "")[:5000], domain.now()),
        )
        connection.execute(
            "INSERT INTO hr_activity(subject_id,kind,title,status,href,created_at) VALUES (?,?,?,?,?,?)",
            (subject, "submission", item["title"], outcome["status"], f"/challenges/{slug}/submissions/{cursor.lastrowid}", domain.now()),
        )
    return RedirectResponse(
        f"/challenges/{quote(slug)}/submissions/{cursor.lastrowid}", status_code=303
    )


@app.get("/challenges/{slug}/submissions", include_in_schema=False)
async def submissions(request: Request, slug: str) -> Response:
    item = challenge_or_none(slug)
    if item is None:
        return not_found_response(request)
    subject = session_subject(request)
    if not subject:
        return RedirectResponse(
            f"/auth/login?redirect={quote(f'/challenges/{slug}/submissions')}", status_code=303
        )
    with BACKEND.lifecycle.connection() as connection:
        rows = connection.execute(
            "SELECT * FROM hr_submissions WHERE subject_id=? AND challenge_slug=? ORDER BY submission_id DESC",
            (subject, slug),
        ).fetchall()
    if rows:
        body = "".join(
            "<tr>"
            f"<td><a href='/challenges/{quote(slug)}/submissions/{row['submission_id']}'>#{row['submission_id']}</a></td>"
            f"<td>{esc(row['status'])}</td><td>{esc(row['language'])}</td><td>v{row['version']}</td><td>{row['runtime_ms']} ms</td><td>{row['memory_kb']} KB</td><td>{esc(row['created_at'])}</td></tr>"
            for row in rows
        )
        history = "<div class='table-wrap'><table><thead><tr><th>ID</th><th>Status</th><th>Language</th><th>Version</th><th>Runtime</th><th>Memory</th><th>Submitted</th></tr></thead><tbody>" + body + "</tbody></table></div>"
    else:
        history = "<div class='empty-state'><h2>No submissions yet</h2><p>Return to the editor and submit a solution.</p></div>"
    content = (
        f"<div class='breadcrumb'><a href='/challenges/{quote(slug)}/problem'>{esc(item['title'])}</a> / Submissions</div>"
        f"<h1>Your submissions</h1>{history}<a class='button' href='/challenges/{quote(slug)}/problem'>Back to problem</a>"
    )
    return page_response(request, "Submissions", content, wide=True)


@app.get("/challenges/{slug}/submissions/{submission_id}", include_in_schema=False)
async def submission_detail(request: Request, slug: str, submission_id: int) -> Response:
    item = challenge_or_none(slug)
    if item is None:
        return not_found_response(request)
    subject = session_subject(request)
    if not subject:
        return RedirectResponse("/auth/login", status_code=303)
    with BACKEND.lifecycle.connection() as connection:
        row = connection.execute(
            "SELECT * FROM hr_submissions WHERE submission_id=? AND subject_id=? AND challenge_slug=?",
            (submission_id, subject, slug),
        ).fetchone()
    if row is None:
        return not_found_response(request)
    content = (
        f"<div class='breadcrumb'><a href='/challenges/{quote(slug)}/submissions'>{esc(item['title'])} submissions</a> / #{submission_id}</div>"
        f"<div class='section-heading'><div><h1>Submission #{submission_id}</h1><p>Version {row['version']} in {esc(row['language'])}</p></div><span class='result {esc(str(row['status']).lower().replace(' ', '-'))}'>{esc(row['status'])}</span></div>"
        f"<div class='metrics'><div><strong>{row['score']}</strong><span>Score</span></div><div><strong>{row['runtime_ms']} ms</strong><span>Runtime</span></div><div><strong>{row['memory_kb']} KB</strong><span>Memory</span></div></div>"
        f"<h2>Feedback</h2><p>{esc(row['feedback'])}</p><h2>Submitted source</h2><pre class='source-view'>{esc(row['source'])}</pre>"
        f"<a class='button primary' href='/challenges/{quote(slug)}/problem?load={submission_id}'>Edit and resubmit</a>"
    )
    return page_response(request, f"Submission {submission_id}", content)


@app.get("/challenges/{slug}/forum", include_in_schema=False)
async def discussion(request: Request, slug: str) -> Response:
    item = challenge_or_none(slug)
    if item is None:
        return not_found_response(request)
    content = (
        f"<div class='breadcrumb'><a href='/challenges/{quote(slug)}/problem'>{esc(item['title'])}</a> / Discussions</div>"
        "<h1>Discussions and solutions</h1><div class='inline-note'>Posts are seeded read-only guidance. This clone does not publish comments.</div>"
        "<article class='discussion'><div class='avatar'>HR</div><div><span class='status'>Editorial</span><h2>Start with the function contract</h2><p>Read the two integers, return their sum, and check the sample before submitting.</p></div></article>"
        "<article class='discussion'><div class='avatar'>DL</div><div><span class='status'>Community</span><h2>Keep the first solution small</h2><p>The warmup needs one addition. If a fixture fails, compare stdout with the expected result.</p></div></article>"
        f"<a class='button primary' href='/challenges/{quote(slug)}/problem'>Return to problem</a>"
    )
    return page_response(request, "Discussions", content)


@app.get("/dashboard", include_in_schema=False)
async def dashboard(request: Request) -> Response:
    subject = session_subject(request)
    if not subject:
        return RedirectResponse("/auth/login?redirect=/dashboard", status_code=303)
    profile = profile_for_subject(subject)
    if profile is None:
        return not_found_response(request)
    with BACKEND.lifecycle.connection() as connection:
        accepted = int(connection.execute(
            "SELECT COUNT(DISTINCT challenge_slug) FROM hr_submissions WHERE subject_id=? AND status='Accepted'", (subject,)
        ).fetchone()[0])
        submitted = int(connection.execute(
            "SELECT COUNT(*) FROM hr_submissions WHERE subject_id=?", (subject,)
        ).fetchone()[0])
        saved_rows = connection.execute(
            "SELECT challenge_slug FROM hr_saved_challenges WHERE subject_id=? ORDER BY saved_at DESC", (subject,)
        ).fetchall()
        activity_rows = connection.execute(
            "SELECT * FROM hr_activity WHERE subject_id=? ORDER BY activity_id DESC LIMIT 6", (subject,)
        ).fetchall()
    saved_items = [CHALLENGE_BY_SLUG[str(row[0])] for row in saved_rows if str(row[0]) in CHALLENGE_BY_SLUG]
    activities = "".join(
        "<article class='activity-item'>"
        f"<div><span class='status'>{esc(row['kind'])}</span><h3>{esc(row['title'])}</h3><p>{esc(row['created_at'])}</p></div>"
        f"<div><span class='result {esc(str(row['status']).lower().replace(' ', '-'))}'>{esc(row['status'])}</span> <a href='{esc(row['href'])}'>View details</a></div></article>"
        for row in activity_rows
    ) or "<div class='empty-state'><p>No activity yet.</p></div>"
    content = (
        f"<div class='dashboard-hero'><div><span class='eyebrow'>Welcome back</span><h1>{esc(profile['full_name'])}</h1><p>@{esc(profile['username'])}</p></div>"
        "<div class='streak'><strong>4</strong><span>day streak</span></div></div>"
        f"<div class='metrics'><div><strong>{accepted}</strong><span>Challenges solved</span></div><div><strong>{submitted}</strong><span>Submissions</span></div><div><strong>120</strong><span>Points</span></div><div><strong>2</strong><span>Badges</span></div></div>"
        "<div class='dashboard-grid'><section><div class='section-heading'><div><h2>Continue learning</h2><p>10 Days of JavaScript</p></div><a href='/domains/tutorials/10-days-of-javascript'>View plan</a></div>"
        "<div class='progress'><span style='width:10%'></span></div><p>Day 1 of 10</p><h2>Saved challenges</h2>"
        + challenge_cards(saved_items, subject)
        + "</section><aside><h2>Badges</h2><div class='badge-grid'><div class='round-badge'>A</div><div><strong>Problem Solving</strong><p>Bronze badge</p></div><div class='round-badge'>30</div><div><strong>30 Days of Code</strong><p>Starter badge</p></div></div>"
        "<p><a href='/profile'>Edit profile</a> · <a href='/settings'>Settings</a></p></aside></div>"
        "<section><h2>Recent activity</h2>" + activities + "</section>"
    )
    return page_response(request, "Dashboard", content, wide=True)


@app.get("/profile", include_in_schema=False)
async def profile_page(request: Request) -> Response:
    subject = session_subject(request)
    if not subject:
        return RedirectResponse("/auth/login?redirect=/profile", status_code=303)
    profile = profile_for_subject(subject)
    if profile is None:
        return not_found_response(request)
    content = (
        "<div class='breadcrumb'><a href='/dashboard'>Dashboard</a> / Profile</div><h1>Profile</h1>"
        "<form class='form-card standalone' action='/profile' method='post' data-single-submit>"
        f"<label for='username'>Username</label><input id='username' value='{esc(profile['username'])}' disabled>"
        f"<label for='full_name'>Full name</label><input id='full_name' name='full_name' value='{esc(profile['full_name'])}' required>"
        f"<label for='bio'>Bio</label><textarea id='bio' name='bio' maxlength='500'>{esc(profile['bio'])}</textarea>"
        "<button class='primary' type='submit'>Save profile</button></form>"
    )
    return page_response(request, "Profile", content)


@app.post("/profile", include_in_schema=False)
async def profile_update(request: Request) -> Response:
    subject = session_subject(request)
    if not subject:
        return RedirectResponse("/auth/login", status_code=303)
    data = await form_data(request)
    full_name = data.get("full_name", "").strip()
    if not full_name:
        return RedirectResponse("/profile?error=Full%20name%20is%20required", status_code=303)
    with BACKEND.lifecycle.connection(transaction=True) as connection:
        connection.execute(
            "UPDATE hr_profiles SET full_name=?,bio=? WHERE subject_id=?",
            (full_name[:100], data.get("bio", "")[:500], subject),
        )
    return RedirectResponse("/profile?notice=Profile%20saved", status_code=303)


@app.get("/settings", include_in_schema=False)
async def settings_page(request: Request) -> Response:
    subject = session_subject(request)
    if not subject:
        return RedirectResponse("/auth/login?redirect=/settings", status_code=303)
    profile = profile_for_subject(subject)
    if profile is None:
        return not_found_response(request)
    language = str(profile["preferred_language"])
    checked = " checked" if profile["email_notifications"] else ""
    content = (
        "<div class='breadcrumb'><a href='/dashboard'>Dashboard</a> / Settings</div><h1>Settings</h1>"
        "<form class='form-card standalone' action='/settings' method='post' data-single-submit>"
        "<label for='preferred_language'>Preferred editor language</label>"
        f"<select id='preferred_language' name='preferred_language'><option value='python3'{' selected' if language == 'python3' else ''}>Python 3</option><option value='javascript'{' selected' if language == 'javascript' else ''}>JavaScript</option><option value='java15'{' selected' if language == 'java15' else ''}>Java 15</option></select>"
        f"<label class='check'><input type='checkbox' name='email_notifications' value='yes'{checked}> Keep local notification preferences enabled</label>"
        "<p class='muted'>This setting creates no external message or provider call.</p>"
        "<button class='primary' type='submit'>Save settings</button></form>"
    )
    return page_response(request, "Settings", content)


@app.post("/settings", include_in_schema=False)
async def settings_update(request: Request) -> Response:
    subject = session_subject(request)
    if not subject:
        return RedirectResponse("/auth/login", status_code=303)
    data = await form_data(request)
    language = data.get("preferred_language", "python3")
    if language not in STARTERS:
        language = "python3"
    with BACKEND.lifecycle.connection(transaction=True) as connection:
        connection.execute(
            "UPDATE hr_profiles SET preferred_language=?,email_notifications=? WHERE subject_id=?",
            (language, 1 if data.get("email_notifications") == "yes" else 0, subject),
        )
    return RedirectResponse("/settings?notice=Settings%20saved", status_code=303)


LOGIN_FIELDS = """
<label for='identifier'>Username or email</label><input id='identifier' name='identifier' autocomplete='username' required>
<label for='password'>Password</label><input id='password' name='password' type='password' autocomplete='current-password' required>
<div class='spread'><a href='/auth/forgot_password'>Forgot password?</a><span class='muted small'>or continue with a local account</span></div>
"""


def email_for_identifier(identifier: str) -> str:
    value = identifier.strip()
    if "@" in value:
        return value
    with BACKEND.lifecycle.connection() as connection:
        row = connection.execute(
            "SELECT a.email_normalized FROM hr_profiles p JOIN local_auth_accounts a ON a.subject_id=p.subject_id WHERE lower(p.username)=lower(?)",
            (value,),
        ).fetchone()
    return str(row[0]) if row else value


@app.get("/auth/login", include_in_schema=False)
async def login_page(request: Request) -> Response:
    if session_subject(request):
        return RedirectResponse("/dashboard", status_code=303)
    fields = (
        LOGIN_FIELDS
        + "<div class='identity-options'><button type='button' disabled>Google</button><button type='button' disabled>GitHub</button></div>"
        "<p class='muted small'>Identity providers are shown for context but disabled offline.</p>"
        "<p>New to HackerRank? <a href='/auth/signup'>Create an account</a></p>"
        "<p class='demo'>Demo: learner@hackerrank.local / WebsiteBench!2026</p>"
    )
    return auth_page(
        request,
        "Log in to HackerRank",
        fields,
        "/auth/login" + (f"?redirect={quote(request.query_params.get('redirect', ''))}" if request.query_params.get("redirect") else ""),
        "Log in",
        message=request.query_params.get("error", ""),
    )


@app.post("/auth/login", include_in_schema=False)
async def login_submit(request: Request) -> Response:
    data = await form_data(request)
    identifier = data.get("identifier", "")
    password = data.get("password", "")
    if not identifier or not password:
        return auth_page(request, "Log in to HackerRank", LOGIN_FIELDS, "/auth/login", "Log in", message="Enter your username or email and password.")
    try:
        result = AUTH.sign_in(
            request.state.session_token,
            email=email_for_identifier(identifier),
            password=password,
        )
    except AuthError:
        return auth_page(request, "Log in to HackerRank", LOGIN_FIELDS, "/auth/login", "Log in", message="The username, email, or password is incorrect.")
    request.state.rotated_session_token = result["session_token"]
    destination = request.query_params.get("redirect", "/dashboard")
    if not destination.startswith("/") or destination.startswith("//"):
        destination = "/dashboard"
    return RedirectResponse(destination, status_code=303)


@app.post("/auth/logout", include_in_schema=False)
async def logout_submit(request: Request) -> RedirectResponse:
    AUTH.sign_out(request.state.session_token)
    request.state.rotated_session_token = AUTH.create_anonymous_session()
    return RedirectResponse("/?notice=Logged%20out", status_code=303)


def signup_fields() -> str:
    return """
    <label for='full_name'>Full name</label><input id='full_name' name='full_name' autocomplete='name' required>
    <label for='username'>Username</label><input id='username' name='username' pattern='[A-Za-z0-9_]{2,40}' required>
    <label for='email'>Email</label><input id='email' name='email' type='email' autocomplete='email' required>
    <label for='password'>Password</label><input id='password' name='password' type='password' minlength='8' autocomplete='new-password' required><span class='muted small'>Use at least 8 characters.</span>
    <label class='check'><input type='checkbox' name='terms' value='yes' required> I agree to the Terms of Service and Privacy Policy.</label>
    <p class='muted small'>Verification stays in this offline clone. No real email is sent.</p>
    """


@app.get("/auth/signup", include_in_schema=False)
async def signup_page(request: Request) -> Response:
    if session_subject(request):
        return RedirectResponse("/dashboard", status_code=303)
    return auth_page(request, "Create your learner account", signup_fields(), "/auth/signup", "Create account")


@app.post("/auth/signup", include_in_schema=False)
async def signup_submit(request: Request) -> Response:
    data = await form_data(request)
    full_name = data.get("full_name", "").strip()
    username = data.get("username", "").strip().lower()
    email = data.get("email", "").strip()
    password = data.get("password", "")
    if not all((full_name, username, email, password)) or data.get("terms") != "yes":
        return auth_page(request, "Create your learner account", signup_fields(), "/auth/signup", "Create account", message="Complete every required field and accept the terms.")
    if not re.fullmatch(r"[a-z0-9_]{2,40}", username):
        return auth_page(request, "Create your learner account", signup_fields(), "/auth/signup", "Create account", message="Username must use 2 to 40 letters, numbers, or underscores.")
    with BACKEND.lifecycle.connection() as connection:
        duplicate = connection.execute(
            "SELECT 1 FROM hr_profiles WHERE lower(username)=lower(?)", (username,)
        ).fetchone()
    if duplicate:
        return auth_page(request, "Create your learner account", signup_fields(), "/auth/signup", "Create account", message="Username is already taken.")
    try:
        AUTH.start_registration(
            request.state.session_token,
            email=email,
            display_name=full_name,
            password=password,
        )
        digest = AUTH.session_owner_digest(request.state.session_token)
        with BACKEND.lifecycle.connection(transaction=True) as connection:
            connection.execute(
                "INSERT INTO hr_pending_profiles(session_digest,username,full_name) VALUES (?,?,?) ON CONFLICT(session_digest) DO UPDATE SET username=excluded.username,full_name=excluded.full_name",
                (digest, username, full_name),
            )
    except AuthRateLimited as exc:
        return auth_page(request, "Create your learner account", signup_fields(), "/auth/signup", "Create account", message="A verification request is already active.", retry_after=exc.retry_after)
    except (AuthConflict, AuthValidationError) as exc:
        return auth_page(request, "Create your learner account", signup_fields(), "/auth/signup", "Create account", message=str(exc))
    return RedirectResponse("/auth/signup/verify", status_code=303)


def verification_fields(code: str | None) -> str:
    local = ""
    if code:
        local = (
            "<div class='inline-note'><strong>Local verification message</strong>"
            f"<p>Verification code: <code>{esc(code)}</code></p>"
            "<p class='small'>The code appears only in this browser session.</p></div>"
        )
    return local + "<label for='code'>Verification code</label><input id='code' name='code' inputmode='numeric' pattern='[0-9]{6}' autocomplete='one-time-code' required>"


@app.get("/auth/signup/verify", include_in_schema=False)
async def signup_verify_page(request: Request) -> HTMLResponse:
    mail = AUTH.local_mail_for_session(request.state.session_token, purpose="registration")
    code = str(mail["verification_code"]) if mail else None
    return auth_page(request, "Verify your email", verification_fields(code), "/auth/signup/verify", "Verify account")


@app.post("/auth/signup/verify", include_in_schema=False)
async def signup_verify_submit(request: Request) -> Response:
    data = await form_data(request)
    old_digest = AUTH.session_owner_digest(request.state.session_token)

    def create_profile(connection: sqlite3.Connection, registration: dict[str, object]) -> str:
        pending = connection.execute(
            "SELECT username,full_name FROM hr_pending_profiles WHERE session_digest=?", (old_digest,)
        ).fetchone()
        if pending is None:
            raise AuthRejected("registration profile is unavailable")
        subject = f"learner:{pending['username']}"
        connection.execute(
            "INSERT INTO hr_profiles(subject_id,username,full_name,bio,preferred_language,email_notifications,created_at) VALUES (?,?,?,?,?,?,?)",
            (subject, pending["username"], pending["full_name"], "", "python3", 1, domain.now()),
        )
        connection.execute("DELETE FROM hr_pending_profiles WHERE session_digest=?", (old_digest,))
        return subject

    try:
        AUTH.verify_registration_code(request.state.session_token, data.get("code", ""))
        result = AUTH.complete_registration(
            request.state.session_token, subject_factory=create_profile
        )
    except AuthError as exc:
        mail = AUTH.local_mail_for_session(request.state.session_token, purpose="registration")
        code = str(mail["verification_code"]) if mail else None
        return auth_page(request, "Verify your email", verification_fields(code), "/auth/signup/verify", "Verify account", message=str(exc))
    request.state.rotated_session_token = result["session_token"]
    return RedirectResponse("/profile?notice=Account%20created", status_code=303)


def reset_start_fields() -> str:
    return (
        "<label for='email'>Email address</label>"
        "<input id='email' name='email' type='email' autocomplete='email' required>"
        "<p class='muted small'>The public response is the same whether or not a local account exists.</p>"
        "<p><a href='/auth/login'>Return to log in</a></p>"
    )


@app.get("/auth/forgot_password", include_in_schema=False)
async def forgot_password_page(request: Request) -> HTMLResponse:
    return auth_page(request, "Reset your password", reset_start_fields(), "/auth/forgot_password", "Send reset instructions")


@app.post("/auth/forgot_password", include_in_schema=False)
async def forgot_password_submit(request: Request) -> Response:
    data = await form_data(request)
    email = data.get("email", "").strip()
    if not email:
        return auth_page(request, "Reset your password", reset_start_fields(), "/auth/forgot_password", "Send reset instructions", message="Enter your email address.")
    active = AUTH.session_flow_status(request.state.session_token, purpose="password-reset")
    if active.get("state") == "challenge":
        return RedirectResponse("/auth/reset/verify", status_code=303)
    try:
        AUTH.start_password_reset(request.state.session_token, email=email)
    except AuthRateLimited as exc:
        return auth_page(request, "Reset your password", reset_start_fields(), "/auth/forgot_password", "Send reset instructions", message="A password reset request is already active.", retry_after=exc.retry_after)
    except AuthError as exc:
        return auth_page(request, "Reset your password", reset_start_fields(), "/auth/forgot_password", "Send reset instructions", message=str(exc))
    return RedirectResponse("/auth/reset/verify", status_code=303)


@app.get("/auth/reset/verify", include_in_schema=False)
async def reset_verify_page(request: Request) -> HTMLResponse:
    mail = AUTH.local_mail_for_session(request.state.session_token, purpose="password-reset")
    code = str(mail["verification_code"]) if mail else None
    fields = "<p>If the address belongs to a local account, a verification message is available.</p>" + verification_fields(code) + "<p><a href='/auth/login'>Return to log in</a></p>"
    return auth_page(request, "Check your local inbox", fields, "/auth/reset/verify", "Verify code")


@app.post("/auth/reset/verify", include_in_schema=False)
async def reset_verify_submit(request: Request) -> Response:
    data = await form_data(request)
    try:
        AUTH.verify_password_reset_code(request.state.session_token, data.get("code", ""))
    except AuthError as exc:
        mail = AUTH.local_mail_for_session(request.state.session_token, purpose="password-reset")
        code = str(mail["verification_code"]) if mail else None
        return auth_page(request, "Check your local inbox", verification_fields(code), "/auth/reset/verify", "Verify code", message=str(exc))
    return RedirectResponse("/auth/reset/update", status_code=303)


@app.get("/auth/reset/update", include_in_schema=False)
async def reset_update_page(request: Request) -> HTMLResponse:
    fields = "<label for='password'>New password</label><input id='password' name='password' type='password' minlength='8' autocomplete='new-password' required>"
    return auth_page(request, "Choose a new password", fields, "/auth/reset/update", "Update password")


@app.post("/auth/reset/update", include_in_schema=False)
async def reset_update_submit(request: Request) -> Response:
    data = await form_data(request)
    try:
        token = AUTH.complete_password_reset(
            request.state.session_token, new_password=data.get("password", "")
        )
    except AuthError as exc:
        fields = "<label for='password'>New password</label><input id='password' name='password' type='password' minlength='8' required>"
        return auth_page(request, "Choose a new password", fields, "/auth/reset/update", "Update password", message=str(exc))
    request.state.rotated_session_token = token
    return RedirectResponse("/dashboard?notice=Password%20updated", status_code=303)


def not_found_response(request: Request) -> HTMLResponse:
    content = """
    <div class='empty-state not-found'><div class='big-code'>404</div><h1>We could not find that page</h1>
    <p>The link may be old or the challenge may not exist in this local catalog.</p>
    <div class='actions'><a class='button primary' href='/domains'>Browse practice challenges</a><a class='button' href='/'>Return home</a></div></div>
    """
    return page_response(request, "Page not found", content, status_code=404)


@app.get("/{missing_path:path}", include_in_schema=False)
async def missing_page(request: Request, missing_path: str) -> HTMLResponse:
    return not_found_response(request)
