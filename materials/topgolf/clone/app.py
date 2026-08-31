"""Topgolf bay-reservation offline clone."""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import sys
import time
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
    LocalAuthStore,
)
from websitebench.site_backend import PaymentError  # noqa: E402


app = FastAPI(title="Topgolf offline clone")
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")
backend, auth = open_site_services()
SESSION_COOKIE = backend.session_cookie["name"]
_LOCAL_CODES: dict[str, str] = {}


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; img-src 'self' data:; style-src 'self'; "
        "script-src 'self'; connect-src 'self'; font-src 'self'; "
        "frame-ancestors 'none'; form-action 'self'"
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


def _set_cookie(response: JSONResponse | HTMLResponse, token: str | None) -> None:
    if token:
        response.set_cookie(
            SESSION_COOKIE, token, max_age=30 * 24 * 3600, path="/",
            secure=True, httponly=True, samesite="lax",
        )


def _json(payload: Any, *, status: int = 200, token: str | None = None) -> JSONResponse:
    response = JSONResponse(payload, status_code=status)
    _set_cookie(response, token)
    return response


async def _body(request: Request) -> dict[str, Any]:
    try:
        value = await request.json()
    except Exception as exc:
        raise AuthValidationError("Request body must be valid JSON.") from exc
    if not isinstance(value, dict):
        raise AuthValidationError("Request body must be a JSON object.")
    return value


def _required(value: Any, label: str, limit: int = 180) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AuthValidationError(f"{label} is required.")
    clean = " ".join(value.split())
    if len(clean) > limit:
        raise AuthValidationError(f"{label} is too long.")
    return clean


def _owner(request: Request, *, require_account: bool = False) -> tuple[str, dict[str, Any] | None]:
    token, state, _ = _session(request, create=False)
    if not token or state is None:
        raise AuthRejected("Start a local session to continue.")
    if require_account and not state.get("authenticated"):
        raise AuthRejected("Verify your mobile number to view reservations.")
    digest = auth.session_owner_digest(token)
    return domain.owner_key(state, digest), state


@app.exception_handler(AuthError)
async def auth_error(_request: Request, exc: AuthError):
    status = 401 if isinstance(exc, AuthRejected) else 409 if isinstance(exc, AuthConflict) else 422
    return _json({"error": str(exc)}, status=status)


@app.exception_handler(PaymentError)
async def payment_error(_request: Request, exc: PaymentError):
    return _json({"error": str(exc)}, status=409)


@app.get("/healthz")
def healthz():
    return {"ok": True, "site_id": "topgolf"}


@app.get("/__websitebench/health")
def websitebench_health():
    return {"status": "ok"}


@app.get("/api/session")
def get_session(request: Request):
    token, state, changed = _session(request)
    account = None
    if state and state.get("authenticated"):
        account = {
            "subject_id": state["account"]["subject_id"],
            "display_name": state["account"]["display_name"],
            "verified_by": "mobile-number",
        }
    return _json({"authenticated": bool(account), "account": account}, token=token if changed else None)


@app.post("/api/auth/sign-out")
def sign_out(request: Request):
    token = request.cookies.get(SESSION_COOKIE)
    auth.sign_out(token)
    response = _json({"signed_out": True})
    response.delete_cookie(SESSION_COOKIE, path="/")
    return response


@app.post("/api/auth/phone/start")
async def phone_start(request: Request):
    body = await _body(request)
    try:
        phone = domain.normalize_phone(body.get("phone"))
    except ValueError as exc:
        return _json({"errors": {"phone": str(exc)}}, status=422)
    token, state, changed = _session(request)
    if state and state.get("authenticated"):
        raise AuthConflict("Sign out before verifying another mobile number.")
    digest = auth.session_owner_digest(token)
    now = int(time.time())
    with backend.lifecycle.connection(transaction=True) as connection:
        old = connection.execute(
            "SELECT * FROM tg_phone_challenges WHERE session_digest=?", (digest,)
        ).fetchone()
        if old is not None and int(old["created_at"]) + 60 > now:
            code = _LOCAL_CODES.get(digest)
            if code is None:
                return _json({"error": "Local challenge restarted. Try again in one minute."}, status=409)
            return _json(
                {"accepted": True, "delivery": "local-only", "expires_at": int(old["expires_at"]),
                 "local_action_available": True, "guidance": "No SMS was sent. Use the local verification action."},
                token=token if changed else None,
            )
        connection.execute("DELETE FROM tg_phone_challenges WHERE session_digest=?", (digest,))
        code = f"{secrets.randbelow(1_000_000):06d}"
        salt, code_hash = domain.hash_code(code)
        connection.execute(
            "INSERT INTO tg_phone_challenges(challenge_id,session_digest,phone_normalized,code_salt,code_hash,expires_at,attempts,verified_at,created_at,updated_at) VALUES (?,?,?,?,?,?,0,NULL,?,?)",
            ("phone_" + secrets.token_urlsafe(18), digest, phone, salt, code_hash, now + 600, now, now),
        )
    _LOCAL_CODES[digest] = code
    return _json(
        {"accepted": True, "delivery": "local-only", "expires_at": now + 600,
         "local_action_available": True, "guidance": "No SMS was sent. Use the local verification action."},
        token=token if changed else None,
    )


@app.post("/api/auth/phone/verify")
async def phone_verify(request: Request):
    body = await _body(request)
    token, state, _ = _session(request, create=False)
    if not token or state is None:
        raise AuthRejected("Phone verification session is unavailable.")
    digest = auth.session_owner_digest(token)
    supplied = _LOCAL_CODES.get(digest) if body.get("use_local_code") is True else str(body.get("code", "")).strip()
    if re.fullmatch(r"\d{6}", supplied or "") is None:
        return _json({"errors": {"code": "Enter the six-digit verification code."}}, status=422)
    now = int(time.time())
    failure: str | None = None
    phone = ""
    with backend.lifecycle.connection(transaction=True) as connection:
        row = connection.execute(
            "SELECT * FROM tg_phone_challenges WHERE session_digest=?", (digest,)
        ).fetchone()
        if row is None:
            failure = "Phone verification is unavailable. Send a new code."
        elif int(row["expires_at"]) <= now:
            failure = "Phone verification expired. Send a new code."
        elif int(row["attempts"]) >= 5:
            failure = "Phone verification is locked. Send a new code later."
        else:
            phone = str(row["phone_normalized"])
            _, actual = domain.hash_code(supplied or "", bytes(row["code_salt"]))
            if not hmac.compare_digest(actual, bytes(row["code_hash"])):
                attempts = int(row["attempts"]) + 1
                connection.execute(
                    "UPDATE tg_phone_challenges SET attempts=?,updated_at=? WHERE challenge_id=?",
                    (attempts, now, row["challenge_id"]),
                )
                failure = "Phone verification is locked. Send a new code later." if attempts >= 5 else "Verification code is invalid."
            else:
                connection.execute(
                    "UPDATE tg_phone_challenges SET verified_at=?,updated_at=? WHERE challenge_id=?",
                    (now, now, row["challenge_id"]),
                )
    if failure:
        return _json({"error": failure}, status=409)

    subject_id = domain.player_subject(phone)

    def create_subject(connection, registration):
        connection.execute(
            "INSERT INTO tg_players(subject_id,phone_normalized,phone_last4,display_name,created_at) VALUES (?,?,?,?,?)",
            (subject_id, phone, phone[-4:], registration["display_name"], "2026-08-30T00:00:00Z"),
        )
        return subject_id

    def migrate_session_state(connection, old_digest, _new_digest):
        old_owner = "session:" + old_digest
        new_owner = "account:" + subject_id
        connection.execute(
            "INSERT OR IGNORE INTO tg_favorites(owner_key,venue_id,created_at) SELECT ?,venue_id,created_at FROM tg_favorites WHERE owner_key=?",
            (new_owner, old_owner),
        )
        connection.execute("DELETE FROM tg_favorites WHERE owner_key=?", (old_owner,))
        connection.execute("UPDATE tg_reservations SET owner_key=? WHERE owner_key=?", (new_owner, old_owner))

    result = auth.complete_externally_verified_identity(
        token,
        provider="phone",
        external_subject=phone,
        display_name=f"Player {phone[-4:]}",
        subject_factory=create_subject,
        session_rotation_callback=migrate_session_state,
    )
    _LOCAL_CODES.pop(digest, None)
    return _json(
        {"verified": True, "created": result["created"], "account": {"display_name": result["account"]["display_name"], "phone_last4": phone[-4:]}},
        token=str(result["session_token"]),
    )


@app.get("/api/venues")
def venues(q: str = ""):
    with backend.lifecycle.connection() as connection:
        values = domain.list_venues(connection, q)
    return {"venues": values, "count": len(values)}


@app.get("/api/venues/{venue_id}")
def venue(venue_id: str):
    with backend.lifecycle.connection() as connection:
        value = domain.venue_detail(connection, venue_id)
    return _json({"venue": value}, status=200 if value else 404)


@app.get("/api/venues/{venue_id}/availability")
def availability(venue_id: str, date: str = "2026-09-05"):
    with backend.lifecycle.connection() as connection:
        values = domain.list_slots(connection, venue_id, date)
    return {"slots": values, "count": len(values)}


@app.get("/api/favorites/{venue_id}")
def favorite_state(request: Request, venue_id: str):
    owner, _ = _owner(request)
    with backend.lifecycle.connection() as connection:
        saved = connection.execute(
            "SELECT 1 FROM tg_favorites WHERE owner_key=? AND venue_id=?", (owner, venue_id)
        ).fetchone() is not None
    return {"saved": saved}


@app.post("/api/favorites/{venue_id}")
def favorite_add(request: Request, venue_id: str):
    owner, _ = _owner(request)
    with backend.lifecycle.connection(transaction=True) as connection:
        if domain.venue_detail(connection, venue_id) is None:
            return _json({"error": "Venue is unavailable."}, status=404)
        connection.execute(
            "INSERT OR IGNORE INTO tg_favorites(owner_key,venue_id,created_at) VALUES (?,?,?)",
            (owner, venue_id, "2026-08-30T00:00:00Z"),
        )
    return {"saved": True}


@app.delete("/api/favorites/{venue_id}")
def favorite_remove(request: Request, venue_id: str):
    owner, _ = _owner(request)
    with backend.lifecycle.connection(transaction=True) as connection:
        connection.execute("DELETE FROM tg_favorites WHERE owner_key=? AND venue_id=?", (owner, venue_id))
    return {"saved": False}


@app.post("/api/booking/quote")
async def booking_quote(request: Request):
    body = await _body(request)
    try:
        party_size = int(body.get("party_size", 0))
    except (TypeError, ValueError):
        party_size = 0
    with backend.lifecycle.connection() as connection:
        try:
            value = domain.quote(connection, str(body.get("slot_id", "")), party_size)
        except ValueError as exc:
            return _json({"error": str(exc)}, status=409)
    return {"quote": value, "expires_in_seconds": 900, "creates_hold": False}


@app.get("/api/reservations")
def reservations(request: Request):
    owner, _ = _owner(request, require_account=True)
    with backend.lifecycle.connection() as connection:
        values = domain.reservation_history(connection, owner)
    return {"reservations": values}


@app.get("/api/reservations/{reservation_id}")
def reservation(request: Request, reservation_id: str):
    owner, _ = _owner(request)
    with backend.lifecycle.connection() as connection:
        value = domain.reservation_detail(connection, reservation_id, owner)
    return _json({"reservation": value}, status=200 if value else 404)


@app.post("/api/reservations")
async def create_reservation(request: Request):
    body = await _body(request)
    forbidden = {
        "amount", "amount_minor", "currency", "owner", "fingerprint", "card_number",
        "cvv", "cvc", "expiry", "bank_account", "wallet", "payment_token", "stripe_key",
    }.intersection(body)
    if forbidden:
        return _json({"error": "Payment facts and credentials are not accepted by this local sandbox."}, status=422)
    token, state, _ = _session(request, create=False)
    if not token or state is None:
        raise AuthRejected("Start a local session to book a bay.")
    digest = auth.session_owner_digest(token)
    owner = domain.owner_key(state, digest)
    try:
        party_size = int(body.get("party_size", 0))
    except (TypeError, ValueError):
        party_size = 0
    first = _required(body.get("first_name"), "First name", 80)
    last = _required(body.get("last_name"), "Last name", 80)
    phone = domain.normalize_phone(body.get("phone"))
    email = _required(body.get("email"), "Email address", 254).casefold()
    if re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email) is None:
        raise AuthValidationError("Email address is invalid.")
    if body.get("terms_accepted") is not True:
        raise AuthValidationError("Accept the Terms and cancellation policy to continue.")
    slot_id = _required(body.get("slot_id"), "Session")
    client_key = _required(body.get("idempotency_key"), "Submission key", 120)
    key_hash = hashlib.sha256(f"{owner}:{client_key}".encode()).hexdigest()
    with backend.lifecycle.connection() as connection:
        prior = connection.execute(
            "SELECT reservation_id FROM tg_reservations WHERE owner_key=? AND idempotency_key=?",
            (owner, key_hash),
        ).fetchone()
        try:
            quote = domain.quote(connection, slot_id, party_size)
        except ValueError as exc:
            return _json({"error": str(exc)}, status=409)
    if prior:
        with backend.lifecycle.connection() as connection:
            value = domain.reservation_detail(connection, str(prior["reservation_id"]), owner)
        return {"reservation": value, "idempotent_replay": True}
    amount = int(quote["total_cents"])
    fingerprint = domain.booking_fingerprint(slot_id, party_size, owner)
    payment_owner = "reservation:" + hashlib.sha256(owner.encode()).hexdigest()[:32]
    flow = backend.payments.create_intent(
        owner=payment_owner, amount_minor=amount, currency="USD", fingerprint=fingerprint,
        idempotency_key="create:" + key_hash,
    )
    scenario = str(body.get("scenario_id", "sandbox-approved"))
    attempt = backend.payments.attempt(
        flow_id=flow["flow_id"], owner=payment_owner, amount_minor=amount, currency="USD",
        fingerprint=fingerprint, scenario_id=scenario, idempotency_key=f"attempt:{scenario}:{key_hash}",
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
            value = domain.create_reservation(
                connection, owner=owner, slot_id=slot_id, party_size=party_size,
                first_name=first, last_name=last, phone=phone, email=email,
                accessibility_request=" ".join(str(body.get("accessibility_request", "")).split())[:500],
                special_request=" ".join(str(body.get("special_request", "")).split())[:500],
                payment_flow_id=flow["flow_id"], idempotency_key=key_hash,
            )
    except ValueError as exc:
        return _json({"error": str(exc)}, status=409)
    return _json(
        {"reservation": value, "payment": {"adapter": "local-sandbox", "status": "approved", "is_simulation": True}},
        status=201,
    )


@app.post("/api/reservations/{reservation_id}/actions")
async def reservation_action(request: Request, reservation_id: str):
    body = await _body(request)
    owner, _ = _owner(request, require_account=True)
    try:
        with backend.lifecycle.connection(transaction=True) as connection:
            value = domain.update_reservation(
                connection, reservation_id, owner, str(body.get("action", "")), body.get("slot_id")
            )
    except PermissionError as exc:
        return _json({"error": str(exc)}, status=403)
    except ValueError as exc:
        return _json({"error": str(exc)}, status=409)
    return {"reservation": value}


@app.post("/__admin/reset")
def reset(request: Request):
    global auth
    expected = request.headers.get("x-websitebench-admin-token")
    configured = __import__("os").environ.get("WEBSITEBENCH_ADMIN_TOKEN", "")
    if not configured or not expected or not hmac.compare_digest(configured, expected):
        return _json({"error": "Reset permission denied."}, status=403)
    backend.lifecycle.reset(confirm_site_id="topgolf")
    auth = LocalAuthStore(backend.lifecycle.database_path, site_id="topgolf")
    auth.ensure_schema()
    _LOCAL_CODES.clear()
    return {"reset": True, "site_id": "topgolf"}


PAGE_ROUTES = {
    "/": "home",
    "/us/": "home",
    "/us/experience/": "experience",
    "/us/locations/": "locations",
    "/us/cleveland/": "venue",
    "/us/cleveland/plan-a-visit/": "plan-visit",
    "/booking/review": "booking-review",
    "/account/login": "phone-login",
    "/reservations": "history",
    "/us/faq/": "faq",
    "/us/company/contact-us/": "contact",
    "/us/company/app/": "app",
    "/us/pricing/memberships/": "memberships",
}


@app.get("/booking/confirmation/{reservation_id}")
def confirmation(reservation_id: str):
    return FileResponse(ROOT / "frontend" / "index.html", media_type="text/html", headers={"X-Page-Id": "booking-confirmation"})


@app.get("/reservations/{reservation_id}")
def reservation_page(reservation_id: str):
    return FileResponse(ROOT / "frontend" / "index.html", media_type="text/html", headers={"X-Page-Id": "reservation-detail"})


@app.get("/{path:path}")
def pages(path: str):
    route = "/" + path
    if route != "/" and not route.endswith("/") and route + "/" in PAGE_ROUTES:
        route += "/"
    page = PAGE_ROUTES.get(route)
    if page:
        return FileResponse(ROOT / "frontend" / "index.html", media_type="text/html", headers={"X-Page-Id": page})
    return FileResponse(
        ROOT / "frontend" / "index.html", media_type="text/html", status_code=404,
        headers={"X-Page-Id": "not-found"},
    )
