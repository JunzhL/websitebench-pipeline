"""Stateful GitLab offline clone served only from local files and SQLite."""

from __future__ import annotations

import hmac
import html
import json
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
        Path(runtime_data_dir).resolve() / "gitlab.sqlite3"
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

SITE_ID = "gitlab"
BACKEND, AUTH = open_site_services()
COOKIE = BACKEND.session_cookie
COOKIE_NAME = str(COOKIE["name"])
ADMIN_TOKEN = os.environ.get("WEBSITEBENCH_GITLAB_ADMIN_TOKEN", "gitlab-local-admin")
DEMO_ACCOUNT = {
    "subject_id": "fixture:developer",
    "email": "developer@gitlab.local",
    "display_name": "Demo Developer",
    "password": "WebsiteBench!2026",
}

AUTH.seed_account(**DEMO_ACCOUNT)

CONTENT_SECURITY_POLICY = (
    "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
    "script-src 'self'; font-src 'self' data:; connect-src 'self'; "
    "frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
)

app = FastAPI(title="GitLab offline clone", docs_url=None, redoc_url=None, openapi_url=None)
app.mount("/static", StaticFiles(directory=str(ROOT / "static")), name="static")


def esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def quote(value: object) -> str:
    return urllib.parse.quote(str(value), safe="")


def now() -> str:
    return domain.now()


async def form_data(request: Request) -> dict[str, str]:
    content_type = request.headers.get("content-type", "")
    if "application/x-www-form-urlencoded" not in content_type:
        return {}
    raw = (await request.body()).decode("utf-8", "replace")
    parsed = urllib.parse.parse_qs(raw, keep_blank_values=True)
    return {key: values[-1] for key, values in parsed.items() if values}


def session_subject(request: Request) -> str | None:
    session = getattr(request.state, "session", None) or {}
    account = session.get("account") or {}
    subject = account.get("subject_id")
    return str(subject) if subject else None


def session_account(request: Request) -> dict[str, Any] | None:
    session = getattr(request.state, "session", None) or {}
    account = session.get("account")
    return dict(account) if isinstance(account, dict) else None


def project_row(namespace: str, path: str) -> dict[str, Any] | None:
    with BACKEND.lifecycle.connection() as connection:
        return domain.project_by_path(connection, namespace, path)


def project_access(
    request: Request, namespace: str, path: str, *, write: bool = False
) -> tuple[dict[str, Any] | None, str | None]:
    project = project_row(namespace, path)
    if project is None:
        return None, "not-found"
    subject = session_subject(request)
    with BACKEND.lifecycle.connection() as connection:
        role = domain.member_role(connection, int(project["project_id"]), subject) if subject else None
    if project["visibility"] == "private" and role is None:
        return None, "sign-in" if subject is None else "forbidden"
    if write and role not in {"Owner", "Maintainer", "Developer"}:
        return None, "sign-in" if subject is None else "forbidden"
    project["member_role"] = role
    return project, None


def require_project(
    request: Request, namespace: str, path: str, *, write: bool = False
) -> tuple[dict[str, Any] | None, Response | None]:
    project, error = project_access(request, namespace, path, write=write)
    if project is not None:
        return project, None
    if error == "sign-in":
        return None, RedirectResponse(
            f"/users/sign_in?redirect=/{quote(namespace)}/{quote(path)}", status_code=303
        )
    if error == "forbidden":
        return None, page_response(
            request,
            "Access denied",
            "<div class='empty-state'><div class='empty-icon'>!</div>"
            "<h1>Access denied</h1><p>You do not have permission to perform this action.</p>"
            "<p><a class='button' href='/dashboard'>Return to dashboard</a></p></div>",
            status_code=403,
        )
    return None, not_found_response(request)


def topbar(request: Request, *, marketing: bool = False) -> str:
    account = session_account(request)
    if account:
        actions = (
            "<a class='button hide-mobile' href='/projects/new'>New project</a>"
            "<a class='button' href='/dashboard'>Dashboard</a>"
        )
    else:
        actions = (
            "<a class='button primary hide-mobile' href='/users/sign_up'>Get free trial</a>"
            "<a class='button' href='/users/sign_in'>Sign in</a>"
        )
    search = "" if marketing else (
        "<form class='global-search' action='/search' method='get'>"
        "<input aria-label='Search or go to' name='q' placeholder='Search or go to...' type='search'></form>"
    )
    return (
        "<header class='topbar'>"
        "<a class='brand' href='/' aria-label='GitLab homepage'><span class='tanuki'></span>"
        + ("<span>GitLab</span>" if marketing else "")
        + "</a><nav><a href='/why-gitlab/'>Why GitLab</a><a href='/pricing/'>Pricing</a>"
        "<a href='/explore/projects'>Explore</a></nav>"
        f"{search}<div class='top-actions'>{actions}</div></header>"
    )


def app_sidebar(project: dict[str, Any] | None = None, active: str = "") -> str:
    if project:
        base = f"/{quote(project['namespace'])}/{quote(project['path'])}"
        links = [
            ("project", base, project["name"]),
            ("repository", f"{base}/-/tree/{quote(project['default_branch'])}", "Repository"),
            ("branches", f"{base}/-/branches", "Branches"),
            ("commits", f"{base}/-/commits/{quote(project['default_branch'])}", "Commits"),
            ("issues", f"{base}/-/issues", "Issues"),
            ("merge-requests", f"{base}/-/merge_requests", "Merge requests"),
            ("pipelines", f"{base}/-/pipelines", "Pipelines"),
            ("releases", f"{base}/-/releases", "Releases"),
            ("members", f"{base}/-/project_members", "Members"),
            ("settings", f"{base}/-/edit", "Settings"),
        ]
        title = "Project"
    else:
        links = [
            ("dashboard", "/dashboard", "Projects"),
            ("activity", "/activity", "Your activity"),
            ("explore", "/explore/projects", "Explore"),
            ("profile", "/profile", "Profile"),
            ("help", "/help", "Help"),
        ]
        title = "GitLab"
    items = "".join(
        f"<a class='{'active' if key == active else ''}' href='{href}'>{esc(label)}</a>"
        for key, href, label in links
    )
    return f"<aside class='sidebar'><div class='section-title'>{title}</div>{items}</aside>"


def document(title: str, body: str, *, body_class: str = "") -> str:
    return (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>{esc(title)} | GitLab</title>"
        "<link rel='stylesheet' href='/static/site.css'>"
        "<script src='/static/site.js' defer></script></head>"
        f"<body class='{esc(body_class)}'>{body}</body></html>"
    )


def page_response(
    request: Request,
    title: str,
    content: str,
    *,
    project: dict[str, Any] | None = None,
    active: str = "",
    status_code: int = 200,
    headers: dict[str, str] | None = None,
) -> HTMLResponse:
    notice = request.query_params.get("notice")
    error = request.query_params.get("error")
    flash = ""
    if notice:
        flash = f"<div class='flash success' role='status'>{esc(notice)}</div>"
    elif error:
        flash = f"<div class='flash' role='alert'>{esc(error)}</div>"
    shell = (
        topbar(request)
        + "<div class='app-shell'>"
        + app_sidebar(project, active)
        + f"<main class='content'><section class='panel'>{flash}{content}</section></main></div>"
    )
    return HTMLResponse(document(title, shell), status_code=status_code, headers=headers)


def marketing_response(request: Request, title: str, content: str) -> HTMLResponse:
    announcement = (
        "<div class='announcement'>Ship at agent speed. Prove every step. "
        "Transcend returns on October 6. "
        "<a href='/users/sign_up'>Register now &rarr;</a></div>"
    )
    return HTMLResponse(
        document(
            title,
            announcement + topbar(request, marketing=True) + content,
            body_class="marketing",
        )
    )


def not_found_response(request: Request) -> HTMLResponse:
    content = (
        "<div class='empty-state'><div class='empty-icon'>404</div><h1>Page not found</h1>"
        "<p>Check the address or return to GitLab projects.</p>"
        "<p><a class='button primary' href='/explore/projects'>Explore projects</a></p></div>"
    )
    return page_response(request, "Page not found", content, status_code=404)


def breadcrumbs(project: dict[str, Any], label: str = "") -> str:
    base = f"/{quote(project['namespace'])}/{quote(project['path'])}"
    tail = f" / {esc(label)}" if label else ""
    return (
        "<div class='breadcrumbs'>"
        f"<a href='/{quote(project['namespace'])}'>{esc(project['namespace'])}</a> / "
        f"<a href='{base}'>{esc(project['name'])}</a>{tail}</div>"
    )


def auth_form_page(
    request: Request,
    title: str,
    fields: str,
    action: str,
    button: str,
    *,
    message: str = "",
    retry_after: int = 0,
) -> HTMLResponse:
    retry = f" data-retry-after='{retry_after}'" if retry_after else ""
    banner = f"<div class='flash' role='alert'>{esc(message)}</div>" if message else ""
    content = (
        f"<div class='form-card'><h1>{esc(title)}</h1>{banner}"
        f"<form action='{action}' method='post' data-single-submit{retry}>{fields}"
        f"<button class='primary' type='submit'>{esc(button)}</button>"
        "<span class='muted small' data-cooldown-label></span></form></div>"
    )
    headers = {"Retry-After": str(retry_after)} if retry_after else None
    response = page_response(request, title, content, headers=headers)
    return response


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
    supplied = request.headers.get("X-WebsiteBench-Admin-Token", "")
    if not hmac.compare_digest(supplied, ADMIN_TOKEN):
        return JSONResponse({"error": "forbidden"}, status_code=403)
    AUTH.reset_site_state(site_reset=domain.reset, seed_accounts=[DEMO_ACCOUNT])
    token = AUTH.create_anonymous_session()
    request.state.rotated_session_token = token
    return JSONResponse({"reset": True, "site_id": SITE_ID})


@app.get("/", include_in_schema=False)
async def home(request: Request) -> HTMLResponse:
    content = """
    <section class="hero">
      <h1>Ship faster with agents under your control</h1>
      <p>Agentic software engineering for your entire team</p>
      <div class="row" style="justify-content:center"><a class="button primary" href="/users/sign_up">Try for free</a><a class="button" href="/why-gitlab/">Learn more</a></div>
    </section>
    <section class="marketing-section"><h2>Built for how you work</h2><p>Join the people already using GitLab.</p>
      <div class="stack">
        <article class="card marketing-card"><h2>Define how teams and AI agents work together</h2><p>Customize workflows for development, testing, security, and deployment while your team stays in control.</p></article>
        <article class="card marketing-card"><h2>Your end-to-end delivery process in one place</h2><p>Projects, releases, source control, and CI/CD share one local workspace.</p><a class="button" href="/explore/projects">Explore our platform</a></article>
        <article class="card marketing-card"><h2>Be proactive with security built in</h2><p>Review code changes and pipeline results before you merge.</p></article>
      </div>
    </section>
    <section class="dark-section"><div class="marketing-section"><h2>One platform for teams of every size</h2>
      <div class="cards"><div class="card"><h2>Source code</h2><p>Files, branches, commits, and releases.</p></div><div class="card"><h2>Plan work</h2><p>Issues, labels, milestones, and comments.</p></div><div class="card"><h2>Deliver</h2><p>Merge requests, pipelines, jobs, and logs.</p></div></div></div></section>
    <section class="marketing-section" style="text-align:center"><h2 style="margin-left:auto;margin-right:auto">Start building faster today</h2><a class="button primary" href="/users/sign_up">Get your free trial</a></section>
    <footer class="footer"><div class="spread"><span class="brand"><span class="tanuki"></span>GitLab</span><div class="row"><a href="/pricing/">Pricing</a><a href="/help">Help</a><a href="/support/">Support</a><a href="/explore/projects">Explore</a></div></div><p class="small">Git is a trademark of Software Freedom Conservancy and our use of 'GitLab' is under license.</p></footer>
    """
    return marketing_response(request, "Speed with control for agentic software engineering", content)


@app.get("/why-gitlab/", include_in_schema=False)
async def why_gitlab(request: Request) -> HTMLResponse:
    content = """
    <section class="hero"><h1>GitLab is the most comprehensive DevSecOps platform</h1><p>Plan, build, secure, and deploy software from one application.</p><a class="button primary" href="/explore/projects">Explore projects</a></section>
    <section class="marketing-section"><h2>One application. One user interface.</h2><div class="cards"><article class="card"><h2>Collaborate</h2><p>Turn issues into reviewed merge requests.</p></article><article class="card"><h2>Automate</h2><p>Run local pipeline simulations and inspect every job.</p></article><article class="card"><h2>Control</h2><p>Manage project visibility, members, and branch history.</p></article></div></section>
    """
    return marketing_response(request, "Why GitLab", content)


@app.get("/pricing/", include_in_schema=False)
async def pricing(request: Request) -> HTMLResponse:
    content = """
    <section class="hero"><h1>Get the right plan for your team</h1><p>This offline clone does not sell subscriptions or collect payment details.</p></section>
    <section class="marketing-section"><div class="cards"><article class="card"><h2>Free</h2><p>Core source code management and CI/CD.</p><a class="button primary" href="/users/sign_up">Start locally</a></article><article class="card"><h2>Premium</h2><p>Advanced collaboration controls.</p><span class="badge">Information only</span></article><article class="card"><h2>Ultimate</h2><p>Security and compliance features.</p><span class="badge">Information only</span></article></div></section>
    """
    return marketing_response(request, "Pricing", content)


@app.get("/support/", include_in_schema=False)
@app.get("/help", include_in_schema=False)
async def help_page(request: Request) -> HTMLResponse:
    content = (
        "<h1>GitLab help</h1><div class='cards'>"
        "<article class='card'><h2>Projects and repositories</h2><p>Browse files, branches, commits, releases, and project settings.</p><a href='/explore/projects'>Explore projects</a></article>"
        "<article class='card'><h2>Account access</h2><p>Use local registration, sign-in, or password recovery. No real email is sent.</p><a href='/users/sign_in'>Sign in</a></article>"
        "<article class='card'><h2>Failed pipelines</h2><p>Open a pipeline to inspect job status and local logs, then retry it safely.</p></article>"
        "</div>"
    )
    return page_response(request, "Help", content, active="help")


@app.get("/search", include_in_schema=False)
async def global_search(request: Request) -> RedirectResponse:
    query = request.query_params.get("q", "")
    return RedirectResponse(f"/explore/projects?name={quote(query)}", status_code=303)


SIGN_IN_FIELDS = """
<div class="field"><label for="identifier">Username or primary email</label><input id="identifier" name="identifier" autocomplete="username" required></div>
<div class="field"><label for="password">Password</label><input id="password" name="password" type="password" autocomplete="current-password" required></div>
<p><a href="/users/password/new">Forgot your password?</a></p>
"""


@app.get("/users/sign_in", include_in_schema=False)
async def sign_in_page(request: Request) -> Response:
    if session_subject(request):
        return RedirectResponse("/dashboard", status_code=303)
    fields = SIGN_IN_FIELDS + (
        "<p class='muted small'>Demo account: developer@gitlab.local / WebsiteBench!2026</p>"
        "<p>New to GitLab? <a href='/users/sign_up'>Register now</a></p>"
    )
    return auth_form_page(request, "Sign in to GitLab", fields, "/users/sign_in", "Sign in")


def email_for_identifier(identifier: str) -> str:
    value = identifier.strip()
    if "@" in value:
        return value
    with BACKEND.lifecycle.connection() as connection:
        result = connection.execute(
            "SELECT a.email_normalized FROM gl_profiles p "
            "JOIN local_auth_accounts a ON a.subject_id=p.subject_id "
            "WHERE lower(p.username)=lower(?)",
            (value,),
        ).fetchone()
    return str(result[0]) if result else value


@app.post("/users/sign_in", include_in_schema=False)
async def sign_in_submit(request: Request) -> Response:
    data = await form_data(request)
    identifier = data.get("identifier", "")
    password = data.get("password", "")
    if not identifier or not password:
        return auth_form_page(
            request,
            "Sign in to GitLab",
            SIGN_IN_FIELDS,
            "/users/sign_in",
            "Sign in",
            message="Enter your username or email and password.",
        )
    try:
        result = AUTH.sign_in(
            request.state.session_token,
            email=email_for_identifier(identifier),
            password=password,
        )
    except AuthError:
        return auth_form_page(
            request,
            "Sign in to GitLab",
            SIGN_IN_FIELDS,
            "/users/sign_in",
            "Sign in",
            message="Invalid login or password.",
        )
    request.state.rotated_session_token = result["session_token"]
    destination = request.query_params.get("redirect", "/dashboard")
    if not destination.startswith("/") or destination.startswith("//"):
        destination = "/dashboard"
    return RedirectResponse(destination, status_code=303)


@app.post("/users/sign_out", include_in_schema=False)
async def sign_out_submit(request: Request) -> RedirectResponse:
    AUTH.sign_out(request.state.session_token)
    request.state.rotated_session_token = AUTH.create_anonymous_session()
    return RedirectResponse("/?notice=Signed%20out", status_code=303)


def sign_up_fields() -> str:
    return """
    <div class="grid-2">
      <div class="field"><label for="first_name">First name</label><input id="first_name" name="first_name" autocomplete="given-name" required></div>
      <div class="field"><label for="last_name">Last name</label><input id="last_name" name="last_name" autocomplete="family-name" required></div>
    </div>
    <div class="field"><label for="username">Username</label><input id="username" name="username" pattern="[A-Za-z0-9_-]{2,40}" required></div>
    <div class="field"><label for="email">Email</label><input id="email" name="email" type="email" autocomplete="email" required></div>
    <div class="field"><label for="password">Password</label><input id="password" name="password" type="password" minlength="8" autocomplete="new-password" required><span class="muted small">Use at least 8 characters.</span></div>
    <label class="checkbox"><input type="checkbox" name="terms" value="yes" required><span>I accept the Terms of Use and acknowledge the Privacy Statement.</span></label>
    <p class="muted small">Verification stays inside this offline clone. No real email is sent.</p>
    """


@app.get("/users/sign_up", include_in_schema=False)
async def sign_up_page(request: Request) -> Response:
    if session_subject(request):
        return RedirectResponse("/dashboard", status_code=303)
    return auth_form_page(
        request, "Create your GitLab account", sign_up_fields(), "/users/sign_up", "Register"
    )


@app.post("/users/sign_up", include_in_schema=False)
async def sign_up_submit(request: Request) -> Response:
    data = await form_data(request)
    first = data.get("first_name", "").strip()
    last = data.get("last_name", "").strip()
    username = data.get("username", "").strip().lower()
    email = data.get("email", "").strip()
    password = data.get("password", "")
    if not all((first, last, username, email, password)) or data.get("terms") != "yes":
        return auth_form_page(
            request,
            "Create your GitLab account",
            sign_up_fields(),
            "/users/sign_up",
            "Register",
            message="Complete every required field and accept the terms.",
        )
    if not re.fullmatch(r"[a-z0-9_-]{2,40}", username):
        return auth_form_page(
            request,
            "Create your GitLab account",
            sign_up_fields(),
            "/users/sign_up",
            "Register",
            message="Username must use 2 to 40 letters, numbers, underscores, or hyphens.",
        )
    with BACKEND.lifecycle.connection() as connection:
        existing = connection.execute(
            "SELECT 1 FROM gl_profiles WHERE lower(username)=lower(?)", (username,)
        ).fetchone()
    if existing:
        return auth_form_page(
            request,
            "Create your GitLab account",
            sign_up_fields(),
            "/users/sign_up",
            "Register",
            message="Username is already taken.",
        )
    try:
        AUTH.start_registration(
            request.state.session_token,
            email=email,
            display_name=f"{first} {last}",
            password=password,
        )
        digest = AUTH.session_owner_digest(request.state.session_token)
        with BACKEND.lifecycle.connection(transaction=True) as connection:
            connection.execute(
                "INSERT INTO gl_pending_profiles(session_digest,username,first_name,last_name) "
                "VALUES (?,?,?,?) ON CONFLICT(session_digest) DO UPDATE SET "
                "username=excluded.username,first_name=excluded.first_name,last_name=excluded.last_name",
                (digest, username, first, last),
            )
    except AuthRateLimited as exc:
        return auth_form_page(
            request,
            "Create your GitLab account",
            sign_up_fields(),
            "/users/sign_up",
            "Register",
            message="A verification request is already active.",
            retry_after=exc.retry_after,
        )
    except (AuthConflict, AuthValidationError) as exc:
        return auth_form_page(
            request,
            "Create your GitLab account",
            sign_up_fields(),
            "/users/sign_up",
            "Register",
            message=str(exc),
        )
    return RedirectResponse("/users/sign_up/verify", status_code=303)


def verification_fields(code: str | None, purpose: str) -> str:
    local = ""
    if code:
        local = (
            "<div class='alert info'><strong>Local verification message</strong>"
            f"<p>Verification code: <code>{esc(code)}</code></p>"
            "<p class='small'>This code is shown only in the local browser session.</p></div>"
        )
    return (
        local
        + "<div class='field'><label for='code'>Verification code</label>"
        "<input id='code' name='code' inputmode='numeric' pattern='[0-9]{6}' autocomplete='one-time-code' required></div>"
        + ("" if purpose == "registration" else "")
    )


@app.get("/users/sign_up/verify", include_in_schema=False)
async def sign_up_verify_page(request: Request) -> Response:
    mail = AUTH.local_mail_for_session(request.state.session_token, purpose="registration")
    code = str(mail["verification_code"]) if mail else None
    return auth_form_page(
        request,
        "Verify your email",
        verification_fields(code, "registration"),
        "/users/sign_up/verify",
        "Verify and create account",
    )


@app.post("/users/sign_up/verify", include_in_schema=False)
async def sign_up_verify_submit(request: Request) -> Response:
    data = await form_data(request)
    code = data.get("code", "")
    old_digest = AUTH.session_owner_digest(request.state.session_token)

    def create_profile(connection: sqlite3.Connection, registration: dict[str, object]) -> str:
        pending = connection.execute(
            "SELECT username,first_name,last_name FROM gl_pending_profiles WHERE session_digest=?",
            (old_digest,),
        ).fetchone()
        if pending is None:
            raise AuthRejected("registration profile is unavailable")
        subject = f"user:{pending['username']}"
        connection.execute(
            "INSERT INTO gl_profiles(subject_id,username,first_name,last_name,bio,created_at) VALUES (?,?,?,?,?,?)",
            (subject, pending["username"], pending["first_name"], pending["last_name"], "", now()),
        )
        connection.execute("DELETE FROM gl_pending_profiles WHERE session_digest=?", (old_digest,))
        return subject

    try:
        AUTH.verify_registration_code(request.state.session_token, code)
        result = AUTH.complete_registration(
            request.state.session_token, subject_factory=create_profile
        )
    except AuthError as exc:
        mail = AUTH.local_mail_for_session(request.state.session_token, purpose="registration")
        local_code = str(mail["verification_code"]) if mail else None
        return auth_form_page(
            request,
            "Verify your email",
            verification_fields(local_code, "registration"),
            "/users/sign_up/verify",
            "Verify and create account",
            message=str(exc),
        )
    request.state.rotated_session_token = result["session_token"]
    return RedirectResponse("/dashboard?notice=Account%20created", status_code=303)


def password_reset_start_fields() -> str:
    return (
        "<div class='field'><label for='email'>Email</label>"
        "<input id='email' name='email' type='email' autocomplete='email' required></div>"
        "<p class='muted small'>The response is the same whether or not an account exists.</p>"
    )


@app.get("/users/password/new", include_in_schema=False)
async def password_reset_page(request: Request) -> HTMLResponse:
    return auth_form_page(
        request,
        "Reset your password",
        password_reset_start_fields(),
        "/users/password/new",
        "Send reset instructions",
    )


@app.post("/users/password/new", include_in_schema=False)
async def password_reset_start(request: Request) -> Response:
    data = await form_data(request)
    email = data.get("email", "").strip()
    if not email:
        return auth_form_page(
            request,
            "Reset your password",
            password_reset_start_fields(),
            "/users/password/new",
            "Send reset instructions",
            message="Enter your email address.",
        )
    active = AUTH.session_flow_status(request.state.session_token, purpose="password-reset")
    if active.get("state") == "challenge":
        return RedirectResponse("/users/password/verify", status_code=303)
    try:
        AUTH.start_password_reset(request.state.session_token, email=email)
    except AuthRateLimited as exc:
        return auth_form_page(
            request,
            "Reset your password",
            password_reset_start_fields(),
            "/users/password/new",
            "Send reset instructions",
            message="A password reset request is already active.",
            retry_after=exc.retry_after,
        )
    except AuthError as exc:
        return auth_form_page(
            request,
            "Reset your password",
            password_reset_start_fields(),
            "/users/password/new",
            "Send reset instructions",
            message=str(exc),
        )
    return RedirectResponse("/users/password/verify", status_code=303)


@app.get("/users/password/verify", include_in_schema=False)
async def password_reset_verify_page(request: Request) -> HTMLResponse:
    mail = AUTH.local_mail_for_session(request.state.session_token, purpose="password-reset")
    code = str(mail["verification_code"]) if mail else None
    return auth_form_page(
        request,
        "Check your email",
        "<p>If the address belongs to a local account, a verification message is available.</p>"
        + verification_fields(code, "password-reset"),
        "/users/password/verify",
        "Verify code",
    )


@app.post("/users/password/verify", include_in_schema=False)
async def password_reset_verify(request: Request) -> Response:
    data = await form_data(request)
    try:
        AUTH.verify_password_reset_code(request.state.session_token, data.get("code", ""))
    except AuthError as exc:
        mail = AUTH.local_mail_for_session(request.state.session_token, purpose="password-reset")
        code = str(mail["verification_code"]) if mail else None
        return auth_form_page(
            request,
            "Check your email",
            verification_fields(code, "password-reset"),
            "/users/password/verify",
            "Verify code",
            message=str(exc),
        )
    return RedirectResponse("/users/password/update", status_code=303)


@app.get("/users/password/update", include_in_schema=False)
async def password_update_page(request: Request) -> HTMLResponse:
    fields = (
        "<div class='field'><label for='password'>New password</label>"
        "<input id='password' name='password' type='password' minlength='8' autocomplete='new-password' required></div>"
    )
    return auth_form_page(
        request, "Choose a new password", fields, "/users/password/update", "Update password"
    )


@app.post("/users/password/update", include_in_schema=False)
async def password_update_submit(request: Request) -> Response:
    data = await form_data(request)
    try:
        token = AUTH.complete_password_reset(
            request.state.session_token, new_password=data.get("password", "")
        )
    except AuthError as exc:
        fields = (
            "<div class='field'><label for='password'>New password</label>"
            "<input id='password' name='password' type='password' minlength='8' required></div>"
        )
        return auth_form_page(
            request,
            "Choose a new password",
            fields,
            "/users/password/update",
            "Update password",
            message=str(exc),
        )
    request.state.rotated_session_token = token
    return RedirectResponse("/dashboard?notice=Password%20updated", status_code=303)


def profile_for_subject(subject: str) -> dict[str, Any] | None:
    with BACKEND.lifecycle.connection() as connection:
        result = connection.execute(
            "SELECT * FROM gl_profiles WHERE subject_id=?", (subject,)
        ).fetchone()
    return dict(result) if result else None


def project_cards(projects: list[dict[str, Any]]) -> str:
    if not projects:
        return (
            "<div class='empty-state'><div class='empty-icon'>&lt;/&gt;</div>"
            "<h2>No projects found</h2><p>Try another search or create a local project.</p></div>"
        )
    cards = []
    for project in projects:
        topics = " ".join(
            f"<span class='badge'>{esc(topic)}</span>"
            for topic in json.loads(project.get("topics_json") or "[]")
        )
        cards.append(
            "<article class='card' data-project-card>"
            f"<h2><a href='/{quote(project['namespace'])}/{quote(project['path'])}'>{esc(project['namespace'])} / {esc(project['name'])}</a></h2>"
            f"<p>{esc(project.get('description') or 'No description provided.')}</p>"
            f"<div class='row'><span class='badge'>{esc(project['visibility'])}</span>{topics}</div>"
            "</article>"
        )
    return "<div class='cards'>" + "".join(cards) + "</div>"


@app.get("/explore/projects", include_in_schema=False)
@app.get("/explore/projects/active", include_in_schema=False)
async def explore_projects(request: Request) -> HTMLResponse:
    name = request.query_params.get("name", "").strip()
    with BACKEND.lifecycle.connection() as connection:
        if name:
            rows = connection.execute(
                "SELECT * FROM gl_projects WHERE visibility='public' AND archived=0 "
                "AND (lower(name) LIKE lower(?) OR lower(description) LIKE lower(?)) "
                "ORDER BY updated_at DESC",
                (f"%{name}%", f"%{name}%"),
            ).fetchall()
        else:
            rows = connection.execute(
                "SELECT * FROM gl_projects WHERE visibility='public' AND archived=0 ORDER BY updated_at DESC"
            ).fetchall()
    projects = [dict(item) for item in rows]
    if name and not projects:
        body = (
            "<div class='empty-state'><div class='empty-icon'>&lt;/&gt;</div>"
            f"<h2>No projects match '{esc(name)}'</h2>"
            "<p>Clear the filter to browse available projects.</p>"
            "<a class='button' href='/explore/projects'>View all projects</a></div>"
        )
    else:
        body = project_cards(projects)
    content = (
        "<div class='breadcrumbs'>Explore / Projects</div><h1>Explore projects</h1>"
        "<form method='get' action='/explore/projects'><div class='row'>"
        f"<input style='flex:1' aria-label='Filter or search projects' name='name' value='{esc(name)}' placeholder='Filter or search (3 character minimum)'>"
        "<button type='submit'>Search</button></div></form><hr>"
        + body
    )
    return page_response(request, "Explore projects", content, active="explore")


@app.get("/dashboard", include_in_schema=False)
async def dashboard(request: Request) -> Response:
    subject = session_subject(request)
    if not subject:
        return RedirectResponse("/users/sign_in?redirect=/dashboard", status_code=303)
    with BACKEND.lifecycle.connection() as connection:
        rows = connection.execute(
            "SELECT DISTINCT p.* FROM gl_projects p LEFT JOIN gl_members m ON m.project_id=p.project_id "
            "WHERE p.owner_subject=? OR m.subject_id=? ORDER BY p.updated_at DESC",
            (subject, subject),
        ).fetchall()
    projects = [dict(item) for item in rows]
    content = (
        "<div class='spread'><div><h1>Your work</h1><p class='muted'>Projects you own or can access.</p></div>"
        "<div class='row'><a class='button purple' href='/projects/new'>New project</a>"
        "<form action='/users/sign_out' method='post'><button type='submit'>Sign out</button></form></div></div>"
        "<div class='field'><label for='project-filter'>Filter projects</label>"
        "<input id='project-filter' data-project-filter placeholder='Search your projects'></div>"
        + project_cards(projects)
        + "<p data-no-project-results hidden>No local projects match this filter.</p>"
    )
    return page_response(request, "Dashboard", content, active="dashboard")


@app.get("/activity", include_in_schema=False)
async def user_activity(request: Request) -> Response:
    subject = session_subject(request)
    if not subject:
        return RedirectResponse("/users/sign_in?redirect=/activity", status_code=303)
    with BACKEND.lifecycle.connection() as connection:
        rows = connection.execute(
            "SELECT a.*,p.namespace,p.path,p.name FROM gl_activity a LEFT JOIN gl_projects p ON p.project_id=a.project_id "
            "WHERE a.subject_id=? ORDER BY a.activity_id DESC",
            (subject,),
        ).fetchall()
    entries = []
    for item in rows:
        item = dict(item)
        options = []
        if item["editable"]:
            options.append(f"<a href='{esc(item['detail_path'])}'>View details</a>")
        if item["cancellable"]:
            options.append("<span class='badge'>cancellable</span>")
        entries.append(
            "<div class='activity'>"
            f"<strong>{esc(item['action'].replace('-', ' ').title())}</strong> "
            f"<span>{esc(item['object_type'].replace('-', ' ').title())} {esc(item['object_ref'])}</span> "
            f"<span class='badge {esc(item['status'])}'>{esc(item['status'])}</span>"
            f"<p class='muted small'>{esc(item['created_at'])}</p><div class='row'>{''.join(options)}</div></div>"
        )
    if not entries:
        entries.append("<div class='empty-state'><h2>No activity yet</h2></div>")
    return page_response(
        request, "Your activity", "<h1>Your activity</h1>" + "".join(entries), active="activity"
    )


@app.get("/profile", include_in_schema=False)
async def profile_page(request: Request) -> Response:
    subject = session_subject(request)
    if not subject:
        return RedirectResponse("/users/sign_in?redirect=/profile", status_code=303)
    profile = profile_for_subject(subject)
    if profile is None:
        return not_found_response(request)
    content = (
        "<h1>Edit profile</h1><form action='/profile' method='post' data-single-submit>"
        f"<div class='field'><label>Username</label><input value='{esc(profile['username'])}' disabled></div>"
        f"<div class='field'><label for='first_name'>First name</label><input id='first_name' name='first_name' value='{esc(profile['first_name'])}' required></div>"
        f"<div class='field'><label for='last_name'>Last name</label><input id='last_name' name='last_name' value='{esc(profile['last_name'])}' required></div>"
        f"<div class='field'><label for='bio'>Bio</label><textarea id='bio' name='bio'>{esc(profile['bio'])}</textarea></div>"
        "<button class='purple' type='submit'>Update profile</button></form>"
    )
    return page_response(request, "Profile", content, active="profile")


@app.post("/profile", include_in_schema=False)
async def profile_update(request: Request) -> Response:
    subject = session_subject(request)
    if not subject:
        return RedirectResponse("/users/sign_in", status_code=303)
    data = await form_data(request)
    first = data.get("first_name", "").strip()
    last = data.get("last_name", "").strip()
    if not first or not last:
        return RedirectResponse("/profile?error=First%20and%20last%20name%20are%20required", status_code=303)
    with BACKEND.lifecycle.connection(transaction=True) as connection:
        connection.execute(
            "UPDATE gl_profiles SET first_name=?,last_name=?,bio=? WHERE subject_id=?",
            (first[:80], last[:80], data.get("bio", "")[:500], subject),
        )
    return RedirectResponse("/profile?notice=Profile%20updated", status_code=303)


def project_form(*, project: dict[str, Any] | None = None) -> str:
    name = project["name"] if project else ""
    path = project["path"] if project else ""
    description = project["description"] if project else ""
    visibility = project["visibility"] if project else "private"
    readme = bool(project["readme"]) if project else True
    options = "".join(
        f"<option value='{value}' {'selected' if visibility == value else ''}>{label}</option>"
        for value, label in (("private", "Private"), ("internal", "Internal"), ("public", "Public"))
    )
    return (
        f"<div class='field'><label for='name'>Project name</label><input id='name' name='name' value='{esc(name)}' required></div>"
        f"<div class='field'><label for='path'>Project slug</label><input id='path' name='path' value='{esc(path)}' {'readonly' if project else ''}></div>"
        f"<div class='field'><label for='description'>Project description</label><textarea id='description' name='description'>{esc(description)}</textarea></div>"
        f"<div class='field'><label for='visibility'>Visibility level</label><select id='visibility' name='visibility'>{options}</select></div>"
        + ("" if project else (
            "<div class='field'><label for='gitignore'>.gitignore template</label><select id='gitignore' name='gitignore'><option value=''>None</option><option>Python</option><option>Go</option><option>Node</option></select></div>"
            "<div class='field'><label for='license'>License</label><select id='license' name='license'><option value=''>None</option><option>MIT</option><option>Apache-2.0</option></select></div>"
            f"<label class='checkbox'><input type='checkbox' name='readme' value='yes' {'checked' if readme else ''}>Initialize repository with a README</label>"
        ))
    )


@app.get("/projects/new", include_in_schema=False)
async def new_project_page(request: Request) -> Response:
    if not session_subject(request):
        return RedirectResponse("/users/sign_in?redirect=/projects/new", status_code=303)
    content = (
        "<h1>Create a new project</h1><p>Projects keep repositories, issues, merge requests, and pipelines together.</p>"
        "<form action='/projects/new' method='post' data-single-submit>"
        + project_form()
        + "<p><button class='purple' type='submit'>Create project</button></p></form>"
    )
    return page_response(request, "New project", content, active="dashboard")


@app.post("/projects/new", include_in_schema=False)
async def create_project(request: Request) -> Response:
    subject = session_subject(request)
    if not subject:
        return RedirectResponse("/users/sign_in", status_code=303)
    profile = profile_for_subject(subject)
    if profile is None:
        return not_found_response(request)
    data = await form_data(request)
    name = data.get("name", "").strip()
    if not name:
        return RedirectResponse("/projects/new?error=Project%20name%20is%20required", status_code=303)
    try:
        path = domain.slug(data.get("path", "") or name)
    except ValueError as exc:
        return RedirectResponse(f"/projects/new?error={quote(exc)}", status_code=303)
    visibility = data.get("visibility", "private")
    if visibility not in {"private", "internal", "public"}:
        visibility = "private"
    timestamp = now()
    try:
        with BACKEND.lifecycle.connection(transaction=True) as connection:
            cursor = connection.execute(
                "INSERT INTO gl_projects(namespace,path,name,description,visibility,owner_subject,default_branch,readme,gitignore,license,topics_json,notifications,archived,forked_from,created_at,updated_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    profile["username"], path, name[:120], data.get("description", "")[:1000],
                    visibility, subject, "main", int(data.get("readme") == "yes"),
                    data.get("gitignore", "")[:40], data.get("license", "")[:40], "[]", "global", 0, None, timestamp, timestamp,
                ),
            )
            project_id = int(cursor.lastrowid)
            connection.execute("INSERT INTO gl_members VALUES (?,?,?)", (project_id, subject, "Owner"))
            head = next_commit_id(connection, project_id)
            connection.execute("INSERT INTO gl_branches VALUES (?,?,?,?,?)", (project_id, "main", head, 1, timestamp))
            connection.execute(
                "INSERT INTO gl_commits VALUES (?,?,?,?,?,?)",
                (project_id, head, "main", "Initial commit", f"{profile['first_name']} {profile['last_name']}", timestamp),
            )
            if data.get("readme") == "yes":
                connection.execute(
                    "INSERT INTO gl_files VALUES (?,?,?,?,?)",
                    (project_id, "main", "README.md", f"# {name}\n", timestamp),
                )
            domain.activity(connection, subject, project_id, "project", path, "created", "active", f"/{profile['username']}/{path}")
    except sqlite3.IntegrityError:
        return RedirectResponse("/projects/new?error=Project%20path%20already%20exists", status_code=303)
    return RedirectResponse(f"/{quote(profile['username'])}/{quote(path)}?notice=Project%20created", status_code=303)


def next_commit_id(connection: sqlite3.Connection, project_id: int) -> str:
    count = int(
        connection.execute("SELECT COUNT(*) FROM gl_commits WHERE project_id=?", (project_id,)).fetchone()[0]
    ) + 1
    return f"{project_id:04x}{count:04x}"[-8:]


@app.get("/api/{missing:path}", include_in_schema=False)
async def missing_api_early(missing: str) -> JSONResponse:
    return JSONResponse({"error": "not-found"}, status_code=404)


@app.get("/external/{slug}", include_in_schema=False)
async def external_boundary_early(request: Request, slug: str) -> HTMLResponse:
    content = (
        "<div class='empty-state'><div class='empty-icon'>↗</div><h1>External link</h1>"
        f"<p>The original page linked to {esc(slug)}. This offline clone made no remote request.</p>"
        "<a class='button' href='/'>Return to GitLab</a></div>"
    )
    return page_response(request, "External link", content)


@app.get("/{namespace}/{project_path}", include_in_schema=False)
async def project_overview(request: Request, namespace: str, project_path: str) -> Response:
    project, failure = require_project(request, namespace, project_path)
    if failure:
        return failure
    assert project is not None
    project_id = int(project["project_id"])
    with BACKEND.lifecycle.connection() as connection:
        files = connection.execute(
            "SELECT path,updated_at FROM gl_files WHERE project_id=? AND branch=? ORDER BY path",
            (project_id, project["default_branch"]),
        ).fetchall()
        counts = {
            "commits": connection.execute("SELECT COUNT(*) FROM gl_commits WHERE project_id=?", (project_id,)).fetchone()[0],
            "branches": connection.execute("SELECT COUNT(*) FROM gl_branches WHERE project_id=?", (project_id,)).fetchone()[0],
            "releases": connection.execute("SELECT COUNT(*) FROM gl_releases WHERE project_id=?", (project_id,)).fetchone()[0],
            "issues": connection.execute("SELECT COUNT(*) FROM gl_issues WHERE project_id=? AND status='opened'", (project_id,)).fetchone()[0],
        }
    base = f"/{quote(namespace)}/{quote(project_path)}"
    file_rows = "".join(
        f"<tr><td><a href='{base}/-/blob/{quote(project['default_branch'])}/{urllib.parse.quote(item['path'], safe='/')}'>{esc(item['path'])}</a></td><td>Initial repository content</td><td>{esc(item['updated_at'][:10])}</td></tr>"
        for item in files
    ) or "<tr><td colspan='3'>No files found</td></tr>"
    topics = " ".join(
        f"<span class='badge'>{esc(topic)}</span>" for topic in json.loads(project["topics_json"])
    )
    write_actions = ""
    if project.get("member_role") in {"Owner", "Maintainer", "Developer"}:
        write_actions = f"<a class='button' href='{base}/-/files/new'>New file</a>"
    content = (
        breadcrumbs(project)
        + "<div class='spread'><div>"
        f"<h1>{esc(project['name'])}</h1><p>{esc(project['description'])}</p><div class='row'><span class='badge'>{esc(project['visibility'])}</span>{topics}</div>"
        "</div><div class='row'>"
        f"<form action='{base}/-/forks' method='post'><button type='submit'>Fork</button></form>{write_actions}"
        "<button type='button' title='Clone this project locally'>Code</button></div></div>"
        "<div class='grid-2'><section>"
        f"<div class='spread'><h2>Repository</h2><a href='{base}/-/tree/{quote(project['default_branch'])}'>{esc(project['default_branch'])}</a></div>"
        "<table><thead><tr><th>Name</th><th>Last commit</th><th>Last update</th></tr></thead>"
        f"<tbody>{file_rows}</tbody></table></section>"
        "<aside><h2>Project information</h2>"
        f"<p>{esc(project['description'] or 'No description provided.')}</p>"
        f"<p><strong>{counts['commits']}</strong> Commits</p><p><strong>{counts['branches']}</strong> Branches</p>"
        f"<p><strong>{counts['releases']}</strong> Releases</p><p><strong>{counts['issues']}</strong> Open issues</p>"
        f"<p class='muted'>Created on {esc(project['created_at'][:10])}</p></aside></div>"
    )
    return page_response(request, project["name"], content, project=project, active="project")


@app.get("/{namespace}/{project_path}/-/tree/{branch:path}", include_in_schema=False)
async def repository_tree(
    request: Request, namespace: str, project_path: str, branch: str
) -> Response:
    project, failure = require_project(request, namespace, project_path)
    if failure:
        return failure
    assert project is not None
    with BACKEND.lifecycle.connection() as connection:
        branch_row = connection.execute(
            "SELECT * FROM gl_branches WHERE project_id=? AND name=?",
            (project["project_id"], branch),
        ).fetchone()
        files = connection.execute(
            "SELECT * FROM gl_files WHERE project_id=? AND branch=? ORDER BY path",
            (project["project_id"], branch),
        ).fetchall()
    if branch_row is None:
        return not_found_response(request)
    base = f"/{quote(namespace)}/{quote(project_path)}"
    rows = "".join(
        f"<tr><td><a href='{base}/-/blob/{quote(branch)}/{urllib.parse.quote(item['path'], safe='/')}'>{esc(item['path'])}</a></td><td>{esc(item['updated_at'][:10])}</td></tr>"
        for item in files
    ) or "<tr><td colspan='2'>No files found</td></tr>"
    content = (
        breadcrumbs(project, "Repository")
        + "<div class='spread'><h1>Files</h1><div class='row'>"
        f"<a class='button' href='{base}/-/branches'>{esc(branch)}</a>"
        f"<a class='button' href='{base}/-/files/new?branch={quote(branch)}'>New file</a></div></div>"
        "<table class='file-tree'><thead><tr><th>Name</th><th>Last update</th></tr></thead>"
        f"<tbody>{rows}</tbody></table>"
    )
    return page_response(request, "Repository", content, project=project, active="repository")


@app.get("/{namespace}/{project_path}/-/blob/{branch}/{file_path:path}", include_in_schema=False)
async def view_file(
    request: Request, namespace: str, project_path: str, branch: str, file_path: str
) -> Response:
    project, failure = require_project(request, namespace, project_path)
    if failure:
        return failure
    assert project is not None
    with BACKEND.lifecycle.connection() as connection:
        file = connection.execute(
            "SELECT * FROM gl_files WHERE project_id=? AND branch=? AND path=?",
            (project["project_id"], branch, file_path),
        ).fetchone()
    if file is None:
        return not_found_response(request)
    base = f"/{quote(namespace)}/{quote(project_path)}"
    edit = ""
    if project.get("member_role") in {"Owner", "Maintainer", "Developer"}:
        edit = f"<a class='button' href='{base}/-/files/{urllib.parse.quote(file_path, safe='/')}/edit?branch={quote(branch)}'>Edit</a>"
    content = (
        breadcrumbs(project, file_path)
        + f"<div class='spread'><h1>{esc(file_path)}</h1><div class='row'>{edit}<a class='button' href='{base}/-/tree/{quote(branch)}'>Back to files</a></div></div>"
        f"<pre class='code'>{esc(file['content'])}</pre>"
    )
    return page_response(request, file_path, content, project=project, active="repository")


def file_editor(project: dict[str, Any], branch: str, path: str = "", content: str = "") -> str:
    base = f"/{quote(project['namespace'])}/{quote(project['path'])}"
    return (
        f"<form action='{base}/-/files/save' method='post' data-single-submit>"
        f"<input type='hidden' name='branch' value='{esc(branch)}'>"
        f"<div class='field'><label for='file_path'>File path</label><input id='file_path' name='file_path' value='{esc(path)}' required></div>"
        f"<div class='field'><label for='content'>Content</label><textarea class='code' id='content' name='content' rows='18'>{esc(content)}</textarea></div>"
        "<div class='field'><label for='message'>Commit message</label><input id='message' name='message' value='Update file' required></div>"
        "<button class='purple' type='submit'>Commit changes</button></form>"
    )


@app.get("/{namespace}/{project_path}/-/files/new", include_in_schema=False)
async def new_file_page(request: Request, namespace: str, project_path: str) -> Response:
    project, failure = require_project(request, namespace, project_path, write=True)
    if failure:
        return failure
    assert project is not None
    branch = request.query_params.get("branch", project["default_branch"])
    return page_response(
        request,
        "New file",
        breadcrumbs(project, "New file") + "<h1>New file</h1>" + file_editor(project, branch),
        project=project,
        active="repository",
    )


@app.get("/{namespace}/{project_path}/-/files/{file_path:path}/edit", include_in_schema=False)
async def edit_file_page(
    request: Request, namespace: str, project_path: str, file_path: str
) -> Response:
    project, failure = require_project(request, namespace, project_path, write=True)
    if failure:
        return failure
    assert project is not None
    branch = request.query_params.get("branch", project["default_branch"])
    with BACKEND.lifecycle.connection() as connection:
        file = connection.execute(
            "SELECT content FROM gl_files WHERE project_id=? AND branch=? AND path=?",
            (project["project_id"], branch, file_path),
        ).fetchone()
    if file is None:
        return not_found_response(request)
    return page_response(
        request,
        "Edit file",
        breadcrumbs(project, "Edit file")
        + f"<h1>Edit {esc(file_path)}</h1>"
        + file_editor(project, branch, file_path, file["content"]),
        project=project,
        active="repository",
    )


@app.post("/{namespace}/{project_path}/-/files/save", include_in_schema=False)
async def save_file(request: Request, namespace: str, project_path: str) -> Response:
    project, failure = require_project(request, namespace, project_path, write=True)
    if failure:
        return failure
    assert project is not None
    subject = session_subject(request)
    profile = profile_for_subject(subject or "")
    data = await form_data(request)
    branch = data.get("branch", project["default_branch"])
    file_path = data.get("file_path", "").strip().strip("/")
    message = data.get("message", "").strip()
    if not file_path or ".." in file_path.split("/") or not message:
        return RedirectResponse(
            f"/{quote(namespace)}/{quote(project_path)}/-/files/new?error=File%20path%20and%20commit%20message%20are%20required",
            status_code=303,
        )
    with BACKEND.lifecycle.connection(transaction=True) as connection:
        branch_row = connection.execute(
            "SELECT 1 FROM gl_branches WHERE project_id=? AND name=?",
            (project["project_id"], branch),
        ).fetchone()
        if branch_row is None:
            return RedirectResponse(
                f"/{quote(namespace)}/{quote(project_path)}/-/branches?error=Branch%20not%20found",
                status_code=303,
            )
        stamp = now()
        connection.execute(
            "INSERT INTO gl_files(project_id,branch,path,content,updated_at) VALUES (?,?,?,?,?) "
            "ON CONFLICT(project_id,branch,path) DO UPDATE SET content=excluded.content,updated_at=excluded.updated_at",
            (project["project_id"], branch, file_path[:300], data.get("content", "")[:200000], stamp),
        )
        sha = next_commit_id(connection, int(project["project_id"]))
        author = f"{profile['first_name']} {profile['last_name']}" if profile else "GitLab User"
        connection.execute(
            "INSERT INTO gl_commits VALUES (?,?,?,?,?,?)",
            (project["project_id"], sha, branch, message[:300], author, stamp),
        )
        connection.execute(
            "UPDATE gl_branches SET head_sha=? WHERE project_id=? AND name=?",
            (sha, project["project_id"], branch),
        )
        connection.execute("UPDATE gl_projects SET updated_at=? WHERE project_id=?", (stamp, project["project_id"]))
        domain.activity(connection, subject or "", int(project["project_id"]), "file", file_path, "committed", "active", f"/{namespace}/{project_path}/-/blob/{branch}/{file_path}", cancellable=False)
    destination = f"/{quote(namespace)}/{quote(project_path)}/-/blob/{quote(branch)}/{urllib.parse.quote(file_path, safe='/')}"
    return RedirectResponse(f"{destination}?notice=Changes%20committed", status_code=303)


@app.get("/{namespace}/{project_path}/-/commits/{branch:path}", include_in_schema=False)
async def commits_page(
    request: Request, namespace: str, project_path: str, branch: str
) -> Response:
    project, failure = require_project(request, namespace, project_path)
    if failure:
        return failure
    assert project is not None
    with BACKEND.lifecycle.connection() as connection:
        commits = connection.execute(
            "SELECT * FROM gl_commits WHERE project_id=? AND branch=? ORDER BY created_at DESC,sha DESC",
            (project["project_id"], branch),
        ).fetchall()
    rows = "".join(
        f"<tr><td><code>{esc(item['sha'])}</code></td><td><strong>{esc(item['message'])}</strong><br><span class='muted small'>{esc(item['author_name'])}</span></td><td>{esc(item['created_at'][:10])}</td></tr>"
        for item in commits
    ) or "<tr><td colspan='3'>No commits found</td></tr>"
    content = (
        breadcrumbs(project, "Commits")
        + f"<div class='spread'><h1>Commits</h1><span class='badge'>{esc(branch)}</span></div>"
        + f"<table><thead><tr><th>Commit</th><th>Message</th><th>Date</th></tr></thead><tbody>{rows}</tbody></table>"
    )
    return page_response(request, "Commits", content, project=project, active="commits")


@app.get("/{namespace}/{project_path}/-/branches", include_in_schema=False)
async def branches_page(request: Request, namespace: str, project_path: str) -> Response:
    project, failure = require_project(request, namespace, project_path)
    if failure:
        return failure
    assert project is not None
    with BACKEND.lifecycle.connection() as connection:
        branches = connection.execute(
            "SELECT * FROM gl_branches WHERE project_id=? ORDER BY name", (project["project_id"],)
        ).fetchall()
    base = f"/{quote(namespace)}/{quote(project_path)}"
    rows = "".join(
        f"<tr><td><a href='{base}/-/tree/{quote(item['name'])}'>{esc(item['name'])}</a> {'<span class=badge>protected</span>' if item['protected'] else ''}</td><td><code>{esc(item['head_sha'])}</code></td><td><a href='{base}/-/compare/{quote(project['default_branch'])}...{quote(item['name'])}'>Compare</a></td></tr>"
        for item in branches
    )
    create = ""
    if project.get("member_role") in {"Owner", "Maintainer", "Developer"}:
        create = (
            f"<form class='row' action='{base}/-/branches' method='post' data-single-submit>"
            "<input style='flex:1' name='name' aria-label='Branch name' placeholder='New branch name' required>"
            f"<input type='hidden' name='source' value='{esc(project['default_branch'])}'>"
            "<button class='purple' type='submit'>New branch</button></form>"
        )
    content = breadcrumbs(project, "Branches") + "<h1>Branches</h1>" + create + f"<table><thead><tr><th>Branch</th><th>Head</th><th>Action</th></tr></thead><tbody>{rows}</tbody></table>"
    return page_response(request, "Branches", content, project=project, active="branches")


@app.post("/{namespace}/{project_path}/-/branches", include_in_schema=False)
async def create_branch(request: Request, namespace: str, project_path: str) -> Response:
    project, failure = require_project(request, namespace, project_path, write=True)
    if failure:
        return failure
    assert project is not None
    data = await form_data(request)
    name = data.get("name", "").strip().strip("/")
    source = data.get("source", project["default_branch"])
    if not name or not re.fullmatch(r"[A-Za-z0-9._/-]{1,120}", name) or ".." in name:
        return RedirectResponse(f"/{quote(namespace)}/{quote(project_path)}/-/branches?error=Invalid%20branch%20name", status_code=303)
    try:
        with BACKEND.lifecycle.connection(transaction=True) as connection:
            source_row = connection.execute(
                "SELECT head_sha FROM gl_branches WHERE project_id=? AND name=?",
                (project["project_id"], source),
            ).fetchone()
            if source_row is None:
                raise ValueError("source branch not found")
            connection.execute(
                "INSERT INTO gl_branches VALUES (?,?,?,?,?)",
                (project["project_id"], name, source_row["head_sha"], 0, now()),
            )
            connection.execute(
                "INSERT INTO gl_files(project_id,branch,path,content,updated_at) "
                "SELECT project_id,?,path,content,updated_at FROM gl_files WHERE project_id=? AND branch=?",
                (name, project["project_id"], source),
            )
            domain.activity(connection, session_subject(request) or "", int(project["project_id"]), "branch", name, "created", "active", f"/{namespace}/{project_path}/-/tree/{name}")
    except (sqlite3.IntegrityError, ValueError):
        return RedirectResponse(f"/{quote(namespace)}/{quote(project_path)}/-/branches?error=Branch%20already%20exists%20or%20source%20is%20missing", status_code=303)
    return RedirectResponse(f"/{quote(namespace)}/{quote(project_path)}/-/branches?notice=Branch%20created", status_code=303)


@app.get("/{namespace}/{project_path}/-/compare/{comparison:path}", include_in_schema=False)
async def compare_branches(
    request: Request, namespace: str, project_path: str, comparison: str
) -> Response:
    project, failure = require_project(request, namespace, project_path)
    if failure:
        return failure
    assert project is not None
    source, separator, target = comparison.partition("...")
    if not separator:
        return not_found_response(request)
    with BACKEND.lifecycle.connection() as connection:
        branches = connection.execute(
            "SELECT name,head_sha FROM gl_branches WHERE project_id=? AND name IN (?,?)",
            (project["project_id"], source, target),
        ).fetchall()
    content = (
        breadcrumbs(project, "Compare revisions")
        + f"<h1>Compare {esc(source)} and {esc(target)}</h1>"
        + ("<div class='alert info'>These branches point to the same commit.</div>" if len(branches) == 2 and branches[0]["head_sha"] == branches[1]["head_sha"] else "<div class='alert success'>Branches have different commits ready for review.</div>")
        + f"<p><a class='button purple' href='/{quote(namespace)}/{quote(project_path)}/-/merge_requests/new?source={quote(target)}&target={quote(source)}'>Create merge request</a></p>"
    )
    return page_response(request, "Compare revisions", content, project=project, active="branches")


@app.get("/{namespace}/{project_path}/-/releases", include_in_schema=False)
async def releases_page(request: Request, namespace: str, project_path: str) -> Response:
    project, failure = require_project(request, namespace, project_path)
    if failure:
        return failure
    assert project is not None
    with BACKEND.lifecycle.connection() as connection:
        releases = connection.execute(
            "SELECT * FROM gl_releases WHERE project_id=? ORDER BY released_at DESC",
            (project["project_id"],),
        ).fetchall()
    cards = "".join(
        f"<article class='card'><div class='spread'><h2>{esc(item['name'])}</h2><span class='badge'>{esc(item['tag'])}</span></div><p>{esc(item['description'])}</p><p class='muted'>{esc(item['released_at'][:10])}</p><div class='row'><button type='button'>Source code (zip)</button><button type='button'>Source code (tar.gz)</button></div></article>"
        for item in releases
    ) or "<div class='empty-state'><h2>No releases yet</h2></div>"
    return page_response(request, "Releases", breadcrumbs(project, "Releases") + "<h1>Releases</h1><div class='stack'>" + cards + "</div>", project=project, active="releases")


@app.post("/{namespace}/{project_path}/-/forks", include_in_schema=False)
async def fork_project(request: Request, namespace: str, project_path: str) -> Response:
    subject = session_subject(request)
    if not subject:
        return RedirectResponse(f"/users/sign_in?redirect=/{quote(namespace)}/{quote(project_path)}", status_code=303)
    source, failure = require_project(request, namespace, project_path)
    if failure:
        return failure
    assert source is not None
    profile = profile_for_subject(subject)
    assert profile is not None
    destination_path = source["path"]
    with BACKEND.lifecycle.connection(transaction=True) as connection:
        existing = connection.execute(
            "SELECT project_id FROM gl_projects WHERE namespace=? AND path=?",
            (profile["username"], destination_path),
        ).fetchone()
        if existing:
            return RedirectResponse(f"/{quote(profile['username'])}/{quote(destination_path)}?notice=Fork%20already%20exists", status_code=303)
        cursor = connection.execute(
            "INSERT INTO gl_projects(namespace,path,name,description,visibility,owner_subject,default_branch,readme,gitignore,license,topics_json,notifications,archived,forked_from,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (profile["username"], destination_path, source["name"], source["description"], "public", subject, source["default_branch"], source["readme"], source["gitignore"], source["license"], source["topics_json"], "global", 0, source["project_id"], now(), now()),
        )
        new_id = int(cursor.lastrowid)
        connection.execute("INSERT INTO gl_members VALUES (?,?,?)", (new_id, subject, "Owner"))
        connection.execute(
            "INSERT INTO gl_branches SELECT ?,name,head_sha,protected,created_at FROM gl_branches WHERE project_id=?",
            (new_id, source["project_id"]),
        )
        connection.execute(
            "INSERT INTO gl_files SELECT ?,branch,path,content,updated_at FROM gl_files WHERE project_id=?",
            (new_id, source["project_id"]),
        )
        connection.execute(
            "INSERT INTO gl_commits SELECT ?,sha,branch,message,author_name,created_at FROM gl_commits WHERE project_id=?",
            (new_id, source["project_id"]),
        )
        domain.activity(connection, subject, new_id, "project", destination_path, "forked", "active", f"/{profile['username']}/{destination_path}")
    return RedirectResponse(f"/{quote(profile['username'])}/{quote(destination_path)}?notice=Project%20forked", status_code=303)


@app.get("/{namespace}/{project_path}/-/issues", include_in_schema=False)
async def issues_page(request: Request, namespace: str, project_path: str) -> Response:
    project, failure = require_project(request, namespace, project_path)
    if failure:
        return failure
    assert project is not None
    state = request.query_params.get("state", "opened")
    if state not in {"opened", "closed", "all"}:
        state = "opened"
    with BACKEND.lifecycle.connection() as connection:
        if state == "all":
            issues = connection.execute(
                "SELECT * FROM gl_issues WHERE project_id=? ORDER BY iid DESC",
                (project["project_id"],),
            ).fetchall()
        else:
            issues = connection.execute(
                "SELECT * FROM gl_issues WHERE project_id=? AND status=? ORDER BY iid DESC",
                (project["project_id"], state),
            ).fetchall()
    base = f"/{quote(namespace)}/{quote(project_path)}"
    rows = "".join(
        f"<tr><td><a href='{base}/-/issues/{item['iid']}'><strong>{esc(item['title'])}</strong></a><br><span class='muted small'>#{item['iid']} opened by {esc(item['author_subject'])}</span></td><td>{' '.join(f'<span class=badge>{esc(label)}</span>' for label in json.loads(item['labels_json']))}</td><td><span class='badge {esc(item['status'])}'>{esc(item['status'])}</span></td></tr>"
        for item in issues
    ) or "<tr><td colspan='3'>No issues found</td></tr>"
    create = (
        f"<a class='button purple' href='{base}/-/issues/new'>New issue</a>"
        if project.get("member_role") in {"Owner", "Maintainer", "Developer"}
        else ""
    )
    content = (
        breadcrumbs(project, "Issues")
        + f"<div class='spread'><h1>Issues</h1>{create}</div>"
        + f"<div class='row'><a href='{base}/-/issues?state=opened'>Open</a><a href='{base}/-/issues?state=closed'>Closed</a><a href='{base}/-/issues?state=all'>All</a></div>"
        + f"<table><thead><tr><th>Title</th><th>Labels</th><th>Status</th></tr></thead><tbody>{rows}</tbody></table>"
    )
    return page_response(request, "Issues", content, project=project, active="issues")


def issue_form(project: dict[str, Any]) -> str:
    base = f"/{quote(project['namespace'])}/{quote(project['path'])}"
    return (
        f"<form action='{base}/-/issues/new' method='post' data-single-submit>"
        "<div class='field'><label for='title'>Title</label><input id='title' name='title' required></div>"
        "<div class='field'><label for='description'>Description</label><textarea id='description' name='description'></textarea></div>"
        "<div class='field'><label for='labels'>Labels</label><input id='labels' name='labels' placeholder='bug, backend'></div>"
        "<div class='field'><label for='assignee'>Assignee username</label><input id='assignee' name='assignee'></div>"
        "<div class='field'><label for='milestone'>Milestone</label><input id='milestone' name='milestone'></div>"
        "<button class='purple' type='submit'>Create issue</button></form>"
    )


@app.get("/{namespace}/{project_path}/-/issues/new", include_in_schema=False)
async def issue_new_page(request: Request, namespace: str, project_path: str) -> Response:
    project, failure = require_project(request, namespace, project_path, write=True)
    if failure:
        return failure
    assert project is not None
    return page_response(request, "New issue", breadcrumbs(project, "New issue") + "<h1>New issue</h1>" + issue_form(project), project=project, active="issues")


@app.post("/{namespace}/{project_path}/-/issues/new", include_in_schema=False)
async def issue_create(request: Request, namespace: str, project_path: str) -> Response:
    project, failure = require_project(request, namespace, project_path, write=True)
    if failure:
        return failure
    assert project is not None
    data = await form_data(request)
    title = data.get("title", "").strip()
    if not title:
        return RedirectResponse(f"/{quote(namespace)}/{quote(project_path)}/-/issues/new?error=Title%20is%20required", status_code=303)
    labels = [label.strip()[:50] for label in data.get("labels", "").split(",") if label.strip()]
    with BACKEND.lifecycle.connection(transaction=True) as connection:
        iid = int(connection.execute("SELECT COALESCE(MAX(iid),0)+1 FROM gl_issues WHERE project_id=?", (project["project_id"],)).fetchone()[0])
        stamp = now()
        connection.execute(
            "INSERT INTO gl_issues VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (project["project_id"], iid, title[:300], data.get("description", "")[:10000], "opened", json.dumps(labels), data.get("assignee", "")[:80] or None, data.get("milestone", "")[:80] or None, session_subject(request), stamp, stamp),
        )
        domain.activity(connection, session_subject(request) or "", int(project["project_id"]), "issue", str(iid), "created", "opened", f"/{namespace}/{project_path}/-/issues/{iid}")
    return RedirectResponse(f"/{quote(namespace)}/{quote(project_path)}/-/issues/{iid}?notice=Issue%20created", status_code=303)


@app.get("/{namespace}/{project_path}/-/issues/{iid:int}", include_in_schema=False)
async def issue_detail(
    request: Request, namespace: str, project_path: str, iid: int
) -> Response:
    project, failure = require_project(request, namespace, project_path)
    if failure:
        return failure
    assert project is not None
    with BACKEND.lifecycle.connection() as connection:
        issue = connection.execute("SELECT * FROM gl_issues WHERE project_id=? AND iid=?", (project["project_id"], iid)).fetchone()
        comments = connection.execute(
            "SELECT c.*,p.username FROM gl_comments c LEFT JOIN gl_profiles p ON p.subject_id=c.author_subject "
            "WHERE c.project_id=? AND c.object_type='issue' AND c.object_iid=? ORDER BY c.comment_id",
            (project["project_id"], iid),
        ).fetchall()
    if issue is None:
        return not_found_response(request)
    base = f"/{quote(namespace)}/{quote(project_path)}/-/issues/{iid}"
    labels = " ".join(f"<span class='badge'>{esc(label)}</span>" for label in json.loads(issue["labels_json"]))
    comment_html = "".join(
        f"<article class='card'><strong>{esc(item['username'] or item['author_subject'])}</strong><p>{esc(item['body'])}</p><span class='muted small'>{esc(item['created_at'])}</span></article>"
        for item in comments
    )
    controls = ""
    if project.get("member_role") in {"Owner", "Maintainer", "Developer"}:
        target = "closed" if issue["status"] == "opened" else "opened"
        controls = (
            f"<form action='{base}/state' method='post'><input type='hidden' name='status' value='{target}'><button type='submit'>{'Close' if target == 'closed' else 'Reopen'} issue</button></form>"
            f"<form action='{base}/comments' method='post' data-single-submit><div class='field'><label for='comment'>Add a comment</label><textarea id='comment' name='body' required></textarea></div><button class='purple' type='submit'>Comment</button></form>"
        )
    content = (
        breadcrumbs(project, f"Issue #{iid}")
        + f"<div class='spread'><h1>{esc(issue['title'])}</h1><span class='badge {esc(issue['status'])}'>{esc(issue['status'])}</span></div>"
        + f"<p class='muted'>#{iid} by {esc(issue['author_subject'])}</p><div>{labels}</div><div class='card'><p>{esc(issue['description'])}</p><p><strong>Assignee:</strong> {esc(issue['assignee'] or 'Unassigned')} &nbsp; <strong>Milestone:</strong> {esc(issue['milestone'] or 'None')}</p></div>"
        + "<h2>Activity</h2><div class='stack'>" + comment_html + "</div>" + controls
    )
    return page_response(request, issue["title"], content, project=project, active="issues")


@app.post("/{namespace}/{project_path}/-/issues/{iid:int}/comments", include_in_schema=False)
async def issue_comment(request: Request, namespace: str, project_path: str, iid: int) -> Response:
    project, failure = require_project(request, namespace, project_path, write=True)
    if failure:
        return failure
    assert project is not None
    data = await form_data(request)
    body = data.get("body", "").strip()
    if body:
        with BACKEND.lifecycle.connection(transaction=True) as connection:
            connection.execute(
                "INSERT INTO gl_comments(project_id,object_type,object_iid,author_subject,body,created_at) VALUES (?,?,?,?,?,?)",
                (project["project_id"], "issue", iid, session_subject(request), body[:10000], now()),
            )
            connection.execute("UPDATE gl_issues SET updated_at=? WHERE project_id=? AND iid=?", (now(), project["project_id"], iid))
    return RedirectResponse(f"/{quote(namespace)}/{quote(project_path)}/-/issues/{iid}?notice=Comment%20added", status_code=303)


@app.post("/{namespace}/{project_path}/-/issues/{iid:int}/state", include_in_schema=False)
async def issue_state(request: Request, namespace: str, project_path: str, iid: int) -> Response:
    project, failure = require_project(request, namespace, project_path, write=True)
    if failure:
        return failure
    assert project is not None
    data = await form_data(request)
    status = data.get("status", "")
    if status not in {"opened", "closed"}:
        status = "opened"
    with BACKEND.lifecycle.connection(transaction=True) as connection:
        connection.execute("UPDATE gl_issues SET status=?,updated_at=? WHERE project_id=? AND iid=?", (status, now(), project["project_id"], iid))
        domain.activity(connection, session_subject(request) or "", int(project["project_id"]), "issue", str(iid), status, status, f"/{namespace}/{project_path}/-/issues/{iid}", cancellable=False)
    return RedirectResponse(f"/{quote(namespace)}/{quote(project_path)}/-/issues/{iid}?notice=Issue%20updated", status_code=303)


@app.get("/{namespace}/{project_path}/-/merge_requests", include_in_schema=False)
async def merge_requests_page(request: Request, namespace: str, project_path: str) -> Response:
    project, failure = require_project(request, namespace, project_path)
    if failure:
        return failure
    assert project is not None
    with BACKEND.lifecycle.connection() as connection:
        merge_requests = connection.execute("SELECT * FROM gl_merge_requests WHERE project_id=? ORDER BY iid DESC", (project["project_id"],)).fetchall()
    base = f"/{quote(namespace)}/{quote(project_path)}"
    rows = "".join(
        f"<tr><td><a href='{base}/-/merge_requests/{item['iid']}'><strong>{esc(item['title'])}</strong></a><br><span class='muted small'>!{item['iid']} {esc(item['source_branch'])} into {esc(item['target_branch'])}</span></td><td>{esc(item['reviewer'] or 'No reviewer')}</td><td><span class='badge {esc(item['status'])}'>{esc(item['status'])}</span></td></tr>"
        for item in merge_requests
    ) or "<tr><td colspan='3'>No merge requests found</td></tr>"
    create = f"<a class='button purple' href='{base}/-/merge_requests/new'>New merge request</a>" if project.get("member_role") in {"Owner", "Maintainer", "Developer"} else ""
    content = breadcrumbs(project, "Merge requests") + f"<div class='spread'><h1>Merge requests</h1>{create}</div><table><thead><tr><th>Title</th><th>Reviewer</th><th>Status</th></tr></thead><tbody>{rows}</tbody></table>"
    return page_response(request, "Merge requests", content, project=project, active="merge-requests")


@app.get("/{namespace}/{project_path}/-/merge_requests/new", include_in_schema=False)
async def merge_request_new_page(request: Request, namespace: str, project_path: str) -> Response:
    project, failure = require_project(request, namespace, project_path, write=True)
    if failure:
        return failure
    assert project is not None
    with BACKEND.lifecycle.connection() as connection:
        branches = connection.execute("SELECT name FROM gl_branches WHERE project_id=? ORDER BY name", (project["project_id"],)).fetchall()
    source_default = request.query_params.get("source", branches[-1]["name"] if branches else "main")
    target_default = request.query_params.get("target", project["default_branch"])
    source_options = "".join(f"<option {'selected' if item['name'] == source_default else ''}>{esc(item['name'])}</option>" for item in branches)
    target_options = "".join(f"<option {'selected' if item['name'] == target_default else ''}>{esc(item['name'])}</option>" for item in branches)
    base = f"/{quote(namespace)}/{quote(project_path)}"
    form = (
        f"<form action='{base}/-/merge_requests/new' method='post' data-single-submit>"
        f"<div class='field'><label for='source'>Source branch</label><select id='source' name='source_branch'>{source_options}</select></div>"
        f"<div class='field'><label for='target'>Target branch</label><select id='target' name='target_branch'>{target_options}</select></div>"
        "<div class='field'><label for='title'>Title</label><input id='title' name='title' required></div>"
        "<div class='field'><label for='description'>Description</label><textarea id='description' name='description'></textarea></div>"
        "<div class='field'><label for='reviewer'>Reviewer</label><input id='reviewer' name='reviewer'></div>"
        "<label class='checkbox'><input type='checkbox' name='draft' value='yes'>Mark as draft</label><p><button class='purple' type='submit'>Create merge request</button></p></form>"
    )
    return page_response(request, "New merge request", breadcrumbs(project, "New merge request") + "<h1>New merge request</h1>" + form, project=project, active="merge-requests")


@app.post("/{namespace}/{project_path}/-/merge_requests/new", include_in_schema=False)
async def merge_request_create(request: Request, namespace: str, project_path: str) -> Response:
    project, failure = require_project(request, namespace, project_path, write=True)
    if failure:
        return failure
    assert project is not None
    data = await form_data(request)
    title = data.get("title", "").strip()
    source = data.get("source_branch", "")
    target = data.get("target_branch", "")
    if not title or not source or not target or source == target:
        return RedirectResponse(f"/{quote(namespace)}/{quote(project_path)}/-/merge_requests/new?error=Choose%20different%20branches%20and%20enter%20a%20title", status_code=303)
    with BACKEND.lifecycle.connection(transaction=True) as connection:
        valid_count = connection.execute("SELECT COUNT(*) FROM gl_branches WHERE project_id=? AND name IN (?,?)", (project["project_id"], source, target)).fetchone()[0]
        if valid_count != 2:
            return RedirectResponse(f"/{quote(namespace)}/{quote(project_path)}/-/merge_requests/new?error=Branch%20not%20found", status_code=303)
        iid = int(connection.execute("SELECT COALESCE(MAX(iid),0)+1 FROM gl_merge_requests WHERE project_id=?", (project["project_id"],)).fetchone()[0])
        stamp = now()
        connection.execute(
            "INSERT INTO gl_merge_requests VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (project["project_id"], iid, title[:300], data.get("description", "")[:10000], source, target, "opened", int(data.get("draft") == "yes"), data.get("reviewer", "")[:80] or None, session_subject(request), json.dumps(["README.md"]), stamp, stamp),
        )
        domain.activity(connection, session_subject(request) or "", int(project["project_id"]), "merge-request", str(iid), "created", "opened", f"/{namespace}/{project_path}/-/merge_requests/{iid}")
    return RedirectResponse(f"/{quote(namespace)}/{quote(project_path)}/-/merge_requests/{iid}?notice=Merge%20request%20created", status_code=303)


@app.get("/{namespace}/{project_path}/-/merge_requests/{iid:int}", include_in_schema=False)
async def merge_request_detail(
    request: Request, namespace: str, project_path: str, iid: int
) -> Response:
    project, failure = require_project(request, namespace, project_path)
    if failure:
        return failure
    assert project is not None
    with BACKEND.lifecycle.connection() as connection:
        merge_request = connection.execute(
            "SELECT * FROM gl_merge_requests WHERE project_id=? AND iid=?",
            (project["project_id"], iid),
        ).fetchone()
        comments = connection.execute(
            "SELECT c.*,p.username FROM gl_comments c LEFT JOIN gl_profiles p ON p.subject_id=c.author_subject "
            "WHERE c.project_id=? AND c.object_type='merge-request' AND c.object_iid=? ORDER BY c.comment_id",
            (project["project_id"], iid),
        ).fetchall()
    if merge_request is None:
        return not_found_response(request)
    base = f"/{quote(namespace)}/{quote(project_path)}/-/merge_requests/{iid}"
    files = "".join(f"<li><code>{esc(path)}</code></li>" for path in json.loads(merge_request["changes_json"]))
    comment_html = "".join(
        f"<article class='card'><strong>{esc(item['username'] or item['author_subject'])}</strong><p>{esc(item['body'])}</p><span class='muted small'>{esc(item['created_at'])}</span></article>"
        for item in comments
    )
    controls = ""
    if project.get("member_role") in {"Owner", "Maintainer", "Developer"}:
        status_options = "".join(
            f"<option {'selected' if merge_request['status'] == value else ''}>{value}</option>"
            for value in ("opened", "merged", "closed")
        )
        controls = (
            f"<form class='row' action='{base}/state' method='post'><label for='mr-status'>Update status</label><select id='mr-status' name='status' style='width:auto'>{status_options}</select><button type='submit'>Update</button></form>"
            f"<form action='{base}/comments' method='post' data-single-submit><div class='field'><label for='mr-comment'>Add a comment</label><textarea id='mr-comment' name='body' required></textarea></div><button class='purple' type='submit'>Comment</button></form>"
        )
    content = (
        breadcrumbs(project, f"Merge request !{iid}")
        + f"<div class='spread'><h1>{'[Draft] ' if merge_request['draft'] else ''}{esc(merge_request['title'])}</h1><span class='badge {esc(merge_request['status'])}'>{esc(merge_request['status'])}</span></div>"
        + f"<p><code>{esc(merge_request['source_branch'])}</code> into <code>{esc(merge_request['target_branch'])}</code></p>"
        + f"<div class='card'><p>{esc(merge_request['description'])}</p><p><strong>Reviewer:</strong> {esc(merge_request['reviewer'] or 'None')}</p></div>"
        + f"<h2>Changes</h2><ul>{files}</ul><h2>Discussion</h2><div class='stack'>{comment_html}</div>{controls}"
    )
    return page_response(request, merge_request["title"], content, project=project, active="merge-requests")


@app.post("/{namespace}/{project_path}/-/merge_requests/{iid:int}/comments", include_in_schema=False)
async def merge_request_comment(request: Request, namespace: str, project_path: str, iid: int) -> Response:
    project, failure = require_project(request, namespace, project_path, write=True)
    if failure:
        return failure
    assert project is not None
    data = await form_data(request)
    body = data.get("body", "").strip()
    if body:
        with BACKEND.lifecycle.connection(transaction=True) as connection:
            connection.execute(
                "INSERT INTO gl_comments(project_id,object_type,object_iid,author_subject,body,created_at) VALUES (?,?,?,?,?,?)",
                (project["project_id"], "merge-request", iid, session_subject(request), body[:10000], now()),
            )
            connection.execute("UPDATE gl_merge_requests SET updated_at=? WHERE project_id=? AND iid=?", (now(), project["project_id"], iid))
    return RedirectResponse(f"/{quote(namespace)}/{quote(project_path)}/-/merge_requests/{iid}?notice=Comment%20added", status_code=303)


@app.post("/{namespace}/{project_path}/-/merge_requests/{iid:int}/state", include_in_schema=False)
async def merge_request_state(request: Request, namespace: str, project_path: str, iid: int) -> Response:
    project, failure = require_project(request, namespace, project_path, write=True)
    if failure:
        return failure
    assert project is not None
    data = await form_data(request)
    status = data.get("status", "")
    if status not in {"opened", "merged", "closed"}:
        status = "opened"
    with BACKEND.lifecycle.connection(transaction=True) as connection:
        merge_request = connection.execute("SELECT * FROM gl_merge_requests WHERE project_id=? AND iid=?", (project["project_id"], iid)).fetchone()
        if merge_request is None:
            return not_found_response(request)
        connection.execute("UPDATE gl_merge_requests SET status=?,updated_at=? WHERE project_id=? AND iid=?", (status, now(), project["project_id"], iid))
        if status == "merged":
            source = connection.execute("SELECT head_sha FROM gl_branches WHERE project_id=? AND name=?", (project["project_id"], merge_request["source_branch"])).fetchone()
            if source:
                connection.execute("UPDATE gl_branches SET head_sha=? WHERE project_id=? AND name=?", (source["head_sha"], project["project_id"], merge_request["target_branch"]))
        domain.activity(connection, session_subject(request) or "", int(project["project_id"]), "merge-request", str(iid), status, status, f"/{namespace}/{project_path}/-/merge_requests/{iid}", cancellable=False)
    return RedirectResponse(f"/{quote(namespace)}/{quote(project_path)}/-/merge_requests/{iid}?notice=Merge%20request%20updated", status_code=303)


@app.get("/{namespace}/{project_path}/-/pipelines", include_in_schema=False)
async def pipelines_page(request: Request, namespace: str, project_path: str) -> Response:
    project, failure = require_project(request, namespace, project_path)
    if failure:
        return failure
    assert project is not None
    with BACKEND.lifecycle.connection() as connection:
        pipelines = connection.execute("SELECT * FROM gl_pipelines WHERE project_id=? ORDER BY pipeline_id DESC", (project["project_id"],)).fetchall()
    base = f"/{quote(namespace)}/{quote(project_path)}"
    rows = "".join(
        f"<tr><td><a href='{base}/-/pipelines/{item['pipeline_id']}'>#{item['pipeline_id']}</a></td><td><span class='badge {esc(item['status'])}'>{esc(item['status'])}</span></td><td>{esc(item['ref'])}</td><td><code>{esc(item['sha'])}</code></td><td>{esc(item['source'])}</td></tr>"
        for item in pipelines
    ) or "<tr><td colspan='5'>No pipelines found</td></tr>"
    trigger = ""
    if project.get("member_role") in {"Owner", "Maintainer", "Developer"}:
        trigger = f"<form action='{base}/-/pipelines' method='post' data-single-submit><button class='purple' type='submit'>Run pipeline</button></form>"
    content = breadcrumbs(project, "Pipelines") + f"<div class='spread'><h1>Pipelines</h1>{trigger}</div><table><thead><tr><th>Pipeline</th><th>Status</th><th>Ref</th><th>Commit</th><th>Source</th></tr></thead><tbody>{rows}</tbody></table>"
    return page_response(request, "Pipelines", content, project=project, active="pipelines")


@app.post("/{namespace}/{project_path}/-/pipelines", include_in_schema=False)
async def pipeline_trigger(request: Request, namespace: str, project_path: str) -> Response:
    project, failure = require_project(request, namespace, project_path, write=True)
    if failure:
        return failure
    assert project is not None
    with BACKEND.lifecycle.connection(transaction=True) as connection:
        branch = connection.execute("SELECT head_sha FROM gl_branches WHERE project_id=? AND name=?", (project["project_id"], project["default_branch"])).fetchone()
        pipeline_id = int(connection.execute("SELECT COALESCE(MAX(pipeline_id),0)+1 FROM gl_pipelines WHERE project_id=?", (project["project_id"],)).fetchone()[0])
        job_id = int(connection.execute("SELECT COALESCE(MAX(job_id),0)+1 FROM gl_jobs WHERE project_id=?", (project["project_id"],)).fetchone()[0])
        stamp = now()
        connection.execute("INSERT INTO gl_pipelines VALUES (?,?,?,?,?,?,?,?)", (project["project_id"], pipeline_id, project["default_branch"], branch["head_sha"] if branch else "00000000", "success", "web", stamp, stamp))
        connection.execute("INSERT INTO gl_jobs VALUES (?,?,?,?,?,?,?,?)", (project["project_id"], job_id, pipeline_id, "test", "test", "success", 0, "Preparing environment\nRunning local test suite\nJob succeeded"))
        domain.activity(connection, session_subject(request) or "", int(project["project_id"]), "pipeline", str(pipeline_id), "triggered", "success", f"/{namespace}/{project_path}/-/pipelines/{pipeline_id}", cancellable=False)
    return RedirectResponse(f"/{quote(namespace)}/{quote(project_path)}/-/pipelines/{pipeline_id}?notice=Pipeline%20completed", status_code=303)


@app.get("/{namespace}/{project_path}/-/pipelines/{pipeline_id:int}", include_in_schema=False)
async def pipeline_detail(request: Request, namespace: str, project_path: str, pipeline_id: int) -> Response:
    project, failure = require_project(request, namespace, project_path)
    if failure:
        return failure
    assert project is not None
    with BACKEND.lifecycle.connection() as connection:
        pipeline = connection.execute("SELECT * FROM gl_pipelines WHERE project_id=? AND pipeline_id=?", (project["project_id"], pipeline_id)).fetchone()
        jobs = connection.execute("SELECT * FROM gl_jobs WHERE project_id=? AND pipeline_id=? ORDER BY job_id", (project["project_id"], pipeline_id)).fetchall()
    if pipeline is None:
        return not_found_response(request)
    base = f"/{quote(namespace)}/{quote(project_path)}/-/pipelines/{pipeline_id}"
    job_cards = "".join(
        f"<article class='card'><div class='spread'><h2>{esc(item['name'])}</h2><span class='badge {esc(item['status'])}'>{esc(item['status'])}</span></div><p>Stage: {esc(item['stage'])}</p><pre class='code'>{esc(item['log_text'])}</pre></article>"
        for item in jobs
    )
    retry = f"<form action='{base}/retry' method='post' data-single-submit><button type='submit'>Retry pipeline</button></form>" if project.get("member_role") in {"Owner", "Maintainer", "Developer"} else ""
    content = breadcrumbs(project, f"Pipeline #{pipeline_id}") + f"<div class='spread'><div><h1>Pipeline #{pipeline_id}</h1><p><code>{esc(pipeline['sha'])}</code> on {esc(pipeline['ref'])}</p></div><div class='row'><span class='badge {esc(pipeline['status'])}'>{esc(pipeline['status'])}</span>{retry}</div></div><div class='stack'>{job_cards}</div>"
    return page_response(request, f"Pipeline #{pipeline_id}", content, project=project, active="pipelines")


@app.post("/{namespace}/{project_path}/-/pipelines/{pipeline_id:int}/retry", include_in_schema=False)
async def pipeline_retry(request: Request, namespace: str, project_path: str, pipeline_id: int) -> Response:
    project, failure = require_project(request, namespace, project_path, write=True)
    if failure:
        return failure
    assert project is not None
    with BACKEND.lifecycle.connection(transaction=True) as connection:
        exists = connection.execute("SELECT 1 FROM gl_pipelines WHERE project_id=? AND pipeline_id=?", (project["project_id"], pipeline_id)).fetchone()
        if exists is None:
            return not_found_response(request)
        connection.execute("UPDATE gl_pipelines SET status='success',source='retry',updated_at=? WHERE project_id=? AND pipeline_id=?", (now(), project["project_id"], pipeline_id))
        connection.execute("UPDATE gl_jobs SET status='success',log_text=log_text || ? WHERE project_id=? AND pipeline_id=?", ("\nRetry requested locally\nJob succeeded", project["project_id"], pipeline_id))
        domain.activity(connection, session_subject(request) or "", int(project["project_id"]), "pipeline", str(pipeline_id), "retried", "success", f"/{namespace}/{project_path}/-/pipelines/{pipeline_id}", cancellable=False)
    return RedirectResponse(f"/{quote(namespace)}/{quote(project_path)}/-/pipelines/{pipeline_id}?notice=Pipeline%20retried", status_code=303)


@app.get("/{namespace}/{project_path}/-/project_members", include_in_schema=False)
async def project_members(request: Request, namespace: str, project_path: str) -> Response:
    project, failure = require_project(request, namespace, project_path)
    if failure:
        return failure
    assert project is not None
    with BACKEND.lifecycle.connection() as connection:
        members = connection.execute(
            "SELECT m.role,p.username,p.first_name,p.last_name FROM gl_members m "
            "LEFT JOIN gl_profiles p ON p.subject_id=m.subject_id WHERE m.project_id=? ORDER BY m.role,p.username",
            (project["project_id"],),
        ).fetchall()
    rows = "".join(
        f"<tr><td>{esc(item['username'] or 'GitLab system')}</td><td>{esc(((item['first_name'] or '') + ' ' + (item['last_name'] or '')).strip())}</td><td><span class='badge'>{esc(item['role'])}</span></td></tr>"
        for item in members
    )
    base = f"/{quote(namespace)}/{quote(project_path)}"
    invite = ""
    if project.get("member_role") in {"Owner", "Maintainer"}:
        invite = (
            f"<form class='card' action='{base}/-/project_members' method='post' data-single-submit>"
            "<h2>Invite a member</h2><div class='field'><label for='member'>Username</label><input id='member' name='username' required></div>"
            "<div class='field'><label for='role'>Role</label><select id='role' name='role'><option>Guest</option><option>Reporter</option><option>Developer</option><option>Maintainer</option></select></div>"
            "<button class='purple' type='submit'>Invite</button></form>"
        )
    content = breadcrumbs(project, "Members") + "<h1>Project members</h1>" + invite + f"<table><thead><tr><th>Username</th><th>Name</th><th>Role</th></tr></thead><tbody>{rows}</tbody></table>"
    return page_response(request, "Members", content, project=project, active="members")


@app.post("/{namespace}/{project_path}/-/project_members", include_in_schema=False)
async def project_member_invite(request: Request, namespace: str, project_path: str) -> Response:
    project, failure = require_project(request, namespace, project_path, write=True)
    if failure:
        return failure
    assert project is not None
    if project.get("member_role") not in {"Owner", "Maintainer"}:
        return page_response(request, "Access denied", "<h1>Access denied</h1><p>Only owners and maintainers can invite members.</p>", project=project, status_code=403)
    data = await form_data(request)
    username = data.get("username", "").strip()
    role = data.get("role", "Guest")
    if role not in {"Guest", "Reporter", "Developer", "Maintainer"}:
        role = "Guest"
    with BACKEND.lifecycle.connection(transaction=True) as connection:
        profile = connection.execute("SELECT subject_id FROM gl_profiles WHERE lower(username)=lower(?)", (username,)).fetchone()
        if profile is None:
            return RedirectResponse(f"/{quote(namespace)}/{quote(project_path)}/-/project_members?error=Local%20user%20not%20found", status_code=303)
        connection.execute(
            "INSERT INTO gl_members(project_id,subject_id,role) VALUES (?,?,?) ON CONFLICT(project_id,subject_id) DO UPDATE SET role=excluded.role",
            (project["project_id"], profile["subject_id"], role),
        )
        domain.activity(connection, session_subject(request) or "", int(project["project_id"]), "member", username, "invited", "active", f"/{namespace}/{project_path}/-/project_members", cancellable=False)
    return RedirectResponse(f"/{quote(namespace)}/{quote(project_path)}/-/project_members?notice=Member%20updated", status_code=303)


@app.get("/{namespace}/{project_path}/-/edit", include_in_schema=False)
async def project_settings(request: Request, namespace: str, project_path: str) -> Response:
    project, failure = require_project(request, namespace, project_path, write=True)
    if failure:
        return failure
    assert project is not None
    if project.get("member_role") not in {"Owner", "Maintainer"}:
        return page_response(request, "Access denied", "<h1>Access denied</h1><p>Only owners and maintainers can change project settings.</p>", project=project, status_code=403)
    with BACKEND.lifecycle.connection() as connection:
        branches = connection.execute("SELECT name FROM gl_branches WHERE project_id=? ORDER BY name", (project["project_id"],)).fetchall()
    branch_options = "".join(f"<option {'selected' if item['name'] == project['default_branch'] else ''}>{esc(item['name'])}</option>" for item in branches)
    notification_options = "".join(f"<option {'selected' if value == project['notifications'] else ''}>{label}</option>" for value, label in (("global", "Global"), ("watch", "Watch"), ("participate", "Participate"), ("disabled", "Disabled")))
    base = f"/{quote(namespace)}/{quote(project_path)}"
    content = (
        breadcrumbs(project, "Settings") + "<h1>Project settings</h1>"
        f"<form action='{base}/-/edit' method='post' data-single-submit>"
        + project_form(project=project)
        + f"<div class='field'><label for='topics'>Topics</label><input id='topics' name='topics' value='{esc(', '.join(json.loads(project['topics_json'])))}'></div>"
        + f"<div class='field'><label for='default_branch'>Default branch</label><select id='default_branch' name='default_branch'>{branch_options}</select></div>"
        + f"<div class='field'><label for='notifications'>Notifications</label><select id='notifications' name='notifications'>{notification_options}</select></div>"
        + f"<label class='checkbox'><input type='checkbox' name='archived' value='yes' {'checked' if project['archived'] else ''}>Archive project</label>"
        + "<p><button class='purple' type='submit'>Save changes</button></p></form>"
    )
    return page_response(request, "Settings", content, project=project, active="settings")


@app.post("/{namespace}/{project_path}/-/edit", include_in_schema=False)
async def project_settings_update(request: Request, namespace: str, project_path: str) -> Response:
    project, failure = require_project(request, namespace, project_path, write=True)
    if failure:
        return failure
    assert project is not None
    if project.get("member_role") not in {"Owner", "Maintainer"}:
        return page_response(request, "Access denied", "<h1>Access denied</h1>", project=project, status_code=403)
    data = await form_data(request)
    visibility = data.get("visibility", project["visibility"])
    if visibility not in {"private", "internal", "public"}:
        visibility = project["visibility"]
    default_branch = data.get("default_branch", project["default_branch"])
    notifications = data.get("notifications", project["notifications"])
    if notifications not in {"global", "watch", "participate", "disabled"}:
        notifications = "global"
    topics = [item.strip()[:50] for item in data.get("topics", "").split(",") if item.strip()][:20]
    with BACKEND.lifecycle.connection(transaction=True) as connection:
        valid_branch = connection.execute("SELECT 1 FROM gl_branches WHERE project_id=? AND name=?", (project["project_id"], default_branch)).fetchone()
        if valid_branch is None:
            default_branch = project["default_branch"]
        connection.execute(
            "UPDATE gl_projects SET name=?,description=?,visibility=?,default_branch=?,topics_json=?,notifications=?,archived=?,updated_at=? WHERE project_id=?",
            (data.get("name", project["name"])[:120], data.get("description", project["description"])[:1000], visibility, default_branch, json.dumps(topics), notifications, int(data.get("archived") == "yes"), now(), project["project_id"]),
        )
        domain.activity(connection, session_subject(request) or "", int(project["project_id"]), "project", project_path, "settings-updated", "active", f"/{namespace}/{project_path}/-/edit", cancellable=False)
    return RedirectResponse(f"/{quote(namespace)}/{quote(project_path)}/-/edit?notice=Settings%20saved", status_code=303)


@app.get("/external/{slug}", include_in_schema=False)
async def external_boundary(request: Request, slug: str) -> HTMLResponse:
    content = (
        "<div class='empty-state'><div class='empty-icon'>↗</div><h1>External link</h1>"
        f"<p>The original page linked to {esc(slug)}. This offline clone made no remote request.</p>"
        "<a class='button' href='/'>Return to GitLab</a></div>"
    )
    return page_response(request, "External link", content)


@app.get("/api/{missing:path}", include_in_schema=False)
async def missing_api(missing: str) -> JSONResponse:
    return JSONResponse({"error": "not-found"}, status_code=404)


@app.get("/{namespace}", include_in_schema=False)
async def namespace_page(request: Request, namespace: str) -> Response:
    with BACKEND.lifecycle.connection() as connection:
        rows = connection.execute(
            "SELECT * FROM gl_projects WHERE namespace=? AND (visibility!='private' OR owner_subject=?) ORDER BY updated_at DESC",
            (namespace, session_subject(request)),
        ).fetchall()
    projects = [dict(item) for item in rows]
    if not projects:
        return not_found_response(request)
    content = f"<h1>{esc(namespace)}</h1><p class='muted'>Projects in this namespace.</p>" + project_cards(projects)
    return page_response(request, namespace, content, active="explore")


@app.get("/{missing:path}", include_in_schema=False)
async def missing_page(request: Request, missing: str) -> HTMLResponse:
    return not_found_response(request)
