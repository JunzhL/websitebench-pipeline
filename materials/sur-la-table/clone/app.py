"""Sur La Table class-booking offline clone."""

from __future__ import annotations

import hashlib
import hmac
import os
import re
import sys
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from starlette.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend import domain  # noqa: E402
from backend.site_backend_integration import open_site_services  # noqa: E402
from websitebench.local_clone_auth import (  # noqa: E402
    AuthConflict,
    AuthError,
    AuthRejected,
    AuthValidationError,
)
from websitebench.site_backend import PaymentError  # noqa: E402


app = FastAPI(title="Sur La Table offline clone")
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")
backend, auth = open_site_services()
SESSION_COOKIE = "__Host-websitebench-sur-la-table-session"


def _seed_accounts_and_history() -> None:
    fixtures = [
        ("subject_history", "history@example.test", "History Guest", "Pasta2026!"),
        ("subject_empty", "empty@example.test", "Empty Guest", "Pasta2026!"),
        ("subject_isolation", "isolation@example.test", "Isolation Guest", "Pasta2026!"),
    ]
    for subject, email, name, password in fixtures:
        auth.seed_account(
            subject_id=subject,
            email=email,
            display_name=name,
            password=password,
        )
    with backend.lifecycle.connection(transaction=True) as connection:
        exists = connection.execute(
            "SELECT 1 FROM slt_bookings WHERE booking_id='SLT-SEED-1001'"
        ).fetchone()
        if exists is None:
            connection.execute(
                """INSERT INTO slt_bookings(
                   booking_id,owner_subject,session_id,party_size,attendee_name,
                   attendee_email,subtotal_cents,total_cents,status,payment_flow_id,
                   idempotency_key,created_at,updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                ("SLT-SEED-1001", "subject_history", "pasta-pa-20260926-1300", 1,
                 "History Guest", "history@example.test", 9900, 9900, "confirmed",
                 "payflow_seed_history_1001", "seed-history-1001",
                 "2026-08-29T18:00:00+00:00", "2026-08-29T18:00:00+00:00"),
            )


_seed_accounts_and_history()


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; img-src 'self' data:; style-src 'self'; "
        "script-src 'self'; connect-src 'self'; font-src 'self'; frame-ancestors 'none'"
    )
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


def _session(request: Request, *, create: bool = True) -> tuple[str | None, dict[str, Any] | None, bool]:
    token = request.cookies.get(SESSION_COOKIE)
    if not create:
        return token, auth.resolve_session(token), False
    current, state = auth.ensure_session(token)
    return current, state, current != token


def _cookie(response: JSONResponse | HTMLResponse, token: str | None) -> None:
    if token:
        response.set_cookie(
            SESSION_COOKIE,
            token,
            max_age=30 * 24 * 3600,
            path="/",
            secure=True,
            httponly=True,
            samesite="lax",
        )


def _json(payload: Any, *, status: int = 200, token: str | None = None) -> JSONResponse:
    response = JSONResponse(payload, status_code=status)
    _cookie(response, token)
    return response


async def _body(request: Request) -> dict[str, Any]:
    try:
        value = await request.json()
    except Exception:
        raise AuthValidationError("Request body must be valid JSON.")
    if not isinstance(value, dict):
        raise AuthValidationError("Request body must be a JSON object.")
    return value


def _owner(state: dict[str, Any] | None) -> str:
    if not state or not state.get("authenticated"):
        raise AuthRejected("Sign in to continue with this booking.")
    return str(state["account"]["subject_id"])


def _required(value: Any, label: str, limit: int = 160) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AuthValidationError(f"{label} is required.")
    clean = " ".join(value.split())
    if len(clean) > limit:
        raise AuthValidationError(f"{label} is too long.")
    return clean


@app.exception_handler(AuthError)
async def auth_error(_request: Request, exc: AuthError):
    status = 401 if isinstance(exc, AuthRejected) else 409 if isinstance(exc, AuthConflict) else 422
    return _json({"error": str(exc)}, status=status)


@app.exception_handler(PaymentError)
async def payment_error(_request: Request, exc: PaymentError):
    return _json({"error": str(exc)}, status=409)


@app.get("/healthz")
def healthz():
    return {"ok": True, "site_id": "sur-la-table"}


@app.get("/api/session")
def get_session(request: Request):
    token, state, changed = _session(request)
    return _json({"session": state}, token=token if changed else None)


@app.get("/api/stores")
def stores():
    with backend.lifecycle.connection() as connection:
        return {"stores": domain.list_stores(connection)}


@app.get("/api/classes")
def classes(
    q: str = "",
    store: str = "",
    cuisine: str = "",
    availability: str = "",
    sort: str = "date",
):
    with backend.lifecycle.connection() as connection:
        rows = domain.list_sessions(
            connection, query=q, store=store, cuisine=cuisine,
            availability=availability, sort=sort,
        )
    return {"classes": rows, "count": len(rows)}


@app.get("/api/classes/{session_id}")
def class_detail(session_id: str):
    with backend.lifecycle.connection() as connection:
        row = domain.session_detail(connection, session_id)
    return _json({"class": row}, status=200 if row else 404)


@app.post("/api/auth/sign-in")
async def sign_in(request: Request):
    body = await _body(request)
    errors: dict[str, str] = {}
    if not str(body.get("email", "")).strip():
        errors["email"] = "Email address is required"
    if not str(body.get("password", "")):
        errors["password"] = "Password is required"
    if errors:
        return _json({"errors": errors}, status=422)
    token, _state, _changed = _session(request)
    result = auth.sign_in(token or "", email=str(body["email"]), password=str(body["password"]))
    return _json({"account": result["account"]}, token=str(result["session_token"]))


@app.post("/api/auth/sign-out")
def sign_out(request: Request):
    token = request.cookies.get(SESSION_COOKIE)
    auth.sign_out(token)
    response = _json({"signed_out": True})
    response.delete_cookie(SESSION_COOKIE, path="/")
    return response


@app.post("/api/auth/registration")
async def registration(request: Request):
    body = await _body(request)
    first = _required(body.get("first_name"), "First name", 60)
    last = _required(body.get("last_name"), "Last name", 60)
    token, _state, changed = _session(request)
    result = auth.start_registration(
        token or "",
        email=str(body.get("email", "")),
        display_name=f"{first} {last}",
        password=str(body.get("password", "")),
    )
    local = auth.local_mail_for_session(token or "", purpose="registration")
    return _json(
        {
            "accepted": result["accepted"],
            "delivery": "local-only",
            "verification_code": local["verification_code"] if local else None,
            "guidance": "No email was sent. Use this local verification code to finish the offline registration.",
        },
        token=token if changed else None,
    )


@app.post("/api/auth/registration/verify")
async def registration_verify(request: Request):
    body = await _body(request)
    token, _state, _changed = _session(request, create=False)
    auth.verify_registration_code(token or "", str(body.get("code", "")))
    result = auth.complete_registration(token or "")
    return _json({"account": result["account"]}, token=str(result["session_token"]))


@app.post("/api/auth/recovery")
async def recovery(request: Request):
    body = await _body(request)
    email = _required(body.get("email"), "Email address", 254)
    token, _state, changed = _session(request)
    result = auth.start_password_reset(token or "", email=email)
    return _json(
        {
            "accepted": result["accepted"],
            "message": "If that email belongs to a local account, a verification message is available.",
            "delivery": "local-only",
        },
        token=token if changed else None,
    )


@app.get("/api/bookings")
def bookings(request: Request):
    _token, state, _changed = _session(request, create=False)
    owner = _owner(state)
    with backend.lifecycle.connection() as connection:
        return {"bookings": domain.booking_history(connection, owner)}


@app.get("/api/bookings/{booking_id}")
def booking(request: Request, booking_id: str):
    _token, state, _changed = _session(request, create=False)
    owner = _owner(state)
    with backend.lifecycle.connection() as connection:
        value = domain.booking_detail(connection, booking_id, owner)
    return _json({"booking": value}, status=200 if value else 404)


@app.post("/api/bookings")
async def create_booking(request: Request):
    body = await _body(request)
    forbidden = {"card_number", "cvv", "expiry", "bank_account"}.intersection(body)
    if forbidden:
        return _json({"error": "Payment credentials are not accepted by this local sandbox."}, status=422)
    _token, state, _changed = _session(request, create=False)
    owner = _owner(state)
    session_id = _required(body.get("session_id"), "Class session")
    try:
        party_size = int(body.get("party_size", 0))
    except (TypeError, ValueError):
        party_size = 0
    if party_size < 1 or party_size > 8:
        raise AuthValidationError("Party size must be between 1 and 8.")
    attendee_name = _required(body.get("attendee_name"), "Attendee name")
    attendee_email = _required(body.get("attendee_email"), "Attendee email", 254)
    if re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", attendee_email) is None:
        raise AuthValidationError("Attendee email is invalid.")
    client_key = _required(body.get("idempotency_key"), "Submission key", 120)
    key_hash = hashlib.sha256(f"{owner}:{client_key}".encode()).hexdigest()
    with backend.lifecycle.connection() as connection:
        prior = connection.execute(
            "SELECT booking_id FROM slt_bookings WHERE owner_subject=? AND idempotency_key=?",
            (owner, key_hash),
        ).fetchone()
        detail = domain.session_detail(connection, session_id)
    if prior:
        with backend.lifecycle.connection() as connection:
            value = domain.booking_detail(connection, prior["booking_id"], owner)
        return {"booking": value, "idempotent_replay": True}
    if detail is None:
        return _json({"error": "Selected class session is unavailable."}, status=404)
    amount = int(detail["price_cents"]) * party_size
    fingerprint = domain.booking_fingerprint(session_id, party_size, owner)
    payment_owner = f"account:{owner}"
    flow = backend.payments.create_intent(
        owner=payment_owner, amount_minor=amount, currency="USD",
        fingerprint=fingerprint, idempotency_key=f"create:{key_hash}",
    )
    attempt = backend.payments.attempt(
        flow_id=flow["flow_id"], owner=payment_owner, amount_minor=amount,
        currency="USD", fingerprint=fingerprint,
        scenario_id=str(body.get("scenario_id", "sandbox-approved")),
        idempotency_key=f"attempt:{str(body.get('scenario_id', 'sandbox-approved'))}:{key_hash}",
    )
    if attempt["status"] != "APPROVED":
        message = "Sandbox payment was declined." if attempt["status"] == "DECLINED" else "Sandbox payment needs a retry."
        return _json({"error": message, "payment_status": attempt["status"]}, status=409)
    try:
        with backend.lifecycle.connection(transaction=True) as connection:
            backend.payments.consume_approval(
                connection, flow_id=flow["flow_id"], owner=payment_owner,
                amount_minor=amount, currency="USD", fingerprint=fingerprint,
            )
            value = domain.create_booking(
                connection, owner=owner, session_id=session_id,
                party_size=party_size, attendee_name=attendee_name,
                attendee_email=attendee_email, payment_flow_id=flow["flow_id"],
                idempotency_key=key_hash,
            )
    except ValueError as exc:
        return _json({"error": str(exc)}, status=409)
    with backend.lifecycle.connection() as connection:
        complete = domain.booking_detail(connection, value["booking_id"], owner)
    return _json({"booking": complete, "payment": {"adapter": "local-sandbox", "status": "approved", "is_simulation": True}}, status=201)


@app.post("/api/bookings/{booking_id}/actions")
async def booking_action(request: Request, booking_id: str):
    body = await _body(request)
    _token, state, _changed = _session(request, create=False)
    owner = _owner(state)
    try:
        with backend.lifecycle.connection(transaction=True) as connection:
            value = domain.update_booking(
                connection, booking_id=booking_id, owner=owner,
                action=str(body.get("action", "")),
                session_id=body.get("session_id"),
            )
    except PermissionError as exc:
        return _json({"error": str(exc)}, status=403)
    except ValueError as exc:
        return _json({"error": str(exc)}, status=409)
    return {"booking": value}


@app.post("/__admin/reset")
def reset(request: Request):
    global auth
    expected = os.environ.get("WEBSITEBENCH_ADMIN_TOKEN", "")
    supplied = request.headers.get("x-websitebench-admin-token", "")
    if not expected or not hmac.compare_digest(expected, supplied):
        return _json({"error": "Reset permission denied."}, status=403)
    backend.lifecycle.reset(confirm_site_id="sur-la-table")
    auth = type(auth)(
        backend.lifecycle.database_path,
        site_id=backend.config.site_id,
    )
    auth.ensure_schema()
    _seed_accounts_and_history()
    return {"reset": True, "site_id": "sur-la-table"}


PAGE_ROUTES = {
    "/": "home",
    "/cooking-classes/": "classes-landing",
    "/cooking-classes/in-store-cooking-classes/": "class-results",
    "/cooking-class/fresh-pasta-workshop-kitchenaid/CFA-10544591": "class-detail",
    "/locations": "locations",
    "/account/login": "login",
    "/account/registration": "registration",
    "/account/forgot-password": "recovery",
    "/order-history": "history",
    "/contactus": "contact",
    "/cooking-class-faq.html": "faq",
    "/booking/review": "booking-review",
}


@app.get("/booking/confirmation/{booking_id}")
def confirmation(booking_id: str):
    return FileResponse(ROOT / "frontend" / "index.html", media_type="text/html", headers={"X-Page-Id": "confirmation"})


@app.get("/{path:path}")
def pages(path: str):
    route = "/" + path
    if route != "/" and route.endswith("/") is False and route + "/" in PAGE_ROUTES:
        route += "/"
    page = PAGE_ROUTES.get(route)
    if page:
        return FileResponse(ROOT / "frontend" / "index.html", media_type="text/html", headers={"X-Page-Id": page})
    return FileResponse(
        ROOT / "frontend" / "index.html", media_type="text/html",
        status_code=410, headers={"X-Page-Id": "not-found"},
    )
