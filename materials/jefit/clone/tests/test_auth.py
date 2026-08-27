"""Auth boundary: redirects, session cookie flags, registration and
recovery through the seam's local outbox, and secret hygiene."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from conftest import PRIMARY, make_client

from backend import db

CLONE_ROOT = Path(__file__).resolve().parents[1]
COOKIE = "__Host-websitebench-jefit-session"


def test_protected_routes_redirect_anonymous(fresh_state) -> None:
    for path in ("/my-jefit", "/my-jefit/workouts", "/my-jefit/settings",
                 "/my-jefit/progress/history", "/elite/checkout"):
        response = fresh_state.get(path, follow_redirects=False)
        assert response.status_code == 302, path
        location = response.headers["location"]
        assert location.startswith("/login?redirect="), path


def test_login_sets_host_cookie_with_flags(fresh_state) -> None:
    response = fresh_state.post(
        "/login",
        data={"username": PRIMARY["username"],
              "password": PRIMARY["password"]},
        follow_redirects=False,
    )
    assert response.status_code == 302
    set_cookie = response.headers["set-cookie"]
    assert COOKIE in set_cookie
    assert "HttpOnly" in set_cookie
    assert "Secure" in set_cookie
    assert "SameSite=Lax" in set_cookie
    assert "Path=/" in set_cookie
    assert "Domain" not in set_cookie


def test_login_accepts_email_identifier(fresh_state) -> None:
    response = fresh_state.post(
        "/login",
        data={"username": "demo.member@example.com",
              "password": PRIMARY["password"]},
        follow_redirects=False,
    )
    assert response.status_code == 302


def test_wrong_credentials_show_error_and_no_session(fresh_state) -> None:
    response = fresh_state.post(
        "/login",
        data={"username": PRIMARY["username"], "password": "Wrong-Pass-1!"},
    )
    assert response.status_code == 422
    assert "Invalid username or password." in response.text
    follow = fresh_state.get("/my-jefit", follow_redirects=False)
    assert follow.status_code == 302


def test_empty_login_submit_settles_on_untouched_panel(fresh_state) -> None:
    # directly-observed source behavior: no inline validation on empty submit
    response = fresh_state.post("/login", data={"username": "",
                                                "password": ""})
    assert response.status_code == 200
    assert "Invalid username or password." not in response.text


def test_authenticated_login_redirects_to_dashboard(member) -> None:
    response = member.get("/login", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "/my-jefit"


def test_login_respects_redirect_target(fresh_state) -> None:
    response = fresh_state.post(
        "/login",
        data={"username": PRIMARY["username"],
              "password": PRIMARY["password"],
              "redirect": "/my-jefit/settings"},
        follow_redirects=False,
    )
    assert response.headers["location"] == "/my-jefit/settings"
    hostile = make_client()
    response = hostile.post(
        "/login",
        data={"username": PRIMARY["username"],
              "password": PRIMARY["password"],
              "redirect": "https://evil.example.com/"},
        follow_redirects=False,
    )
    assert response.headers["location"] == "/my-jefit"


def test_logout_revokes_session(member) -> None:
    response = member.post("/logout", follow_redirects=False)
    assert response.status_code == 302
    follow = member.get("/my-jefit", follow_redirects=False)
    assert follow.status_code == 302


def test_registration_creates_signed_in_unverified_member(fresh_state) -> None:
    client = fresh_state
    step = client.post("/signup/register", data={"email": "r1@example.com"})
    assert step.status_code == 200
    assert 'name="username"' in step.text and 'name="password"' in step.text
    done = client.post(
        "/signup/register",
        data={"email": "r1@example.com", "username": "r1demo",
              "password": "Fresh-Pass-2026!"},
        follow_redirects=False,
    )
    assert done.status_code == 302
    assert done.headers["location"] == "/my-jefit"
    settings = client.get("/my-jefit/settings")
    assert "Unverified" in settings.text
    assert "Resend Verification Link" in settings.text
    # signup auto-creates the 'New Routine' current plan
    workouts = client.get("/my-jefit/workouts")
    assert "New Routine" in workouts.text


def test_duplicate_registration_conflicts(fresh_state) -> None:
    fresh_state.post(
        "/signup/register",
        data={"email": "dup@example.com", "username": "dupuser",
              "password": "Fresh-Pass-2026!"},
        follow_redirects=False,
    )
    again = make_client().post(
        "/signup/register",
        data={"email": "dup@example.com", "username": "dupuser2",
              "password": "Fresh-Pass-2026!"},
    )
    assert again.status_code == 409


def test_recovery_outbox_flow(fresh_state) -> None:
    client = fresh_state
    sent = client.post("/login/forgot-password",
                       data={"email": "demo.member@example.com"})
    assert sent.status_code == 200
    assert "reset code" in sent.text
    outbox = client.get("/api/outbox").json()["mail"]
    reset = [m for m in outbox if m["purpose"] == "password-reset"]
    assert reset and reset[0]["verification_code"]
    code = reset[0]["verification_code"]
    done = client.post(
        "/api/auth/reset-complete",
        json={"code": code, "password": "Rotated-Pass-2026!"},
    )
    assert done.status_code == 200
    relog = make_client()
    response = relog.post(
        "/login",
        data={"username": PRIMARY["username"],
              "password": "Rotated-Pass-2026!"},
        follow_redirects=False,
    )
    assert response.status_code == 302
    db.reset()  # restore the seeded credential for later tests


def test_outbox_is_session_scoped(fresh_state) -> None:
    fresh_state.post("/login/forgot-password",
                     data={"email": "demo.member@example.com"})
    stranger = make_client()
    assert stranger.get("/api/outbox").json()["mail"] == []


def test_verification_mail_and_confirm(fresh_state) -> None:
    client = fresh_state
    client.post(
        "/signup/register",
        data={"email": "v1@example.com", "username": "v1demo",
              "password": "Fresh-Pass-2026!"},
        follow_redirects=False,
    )
    outbox = client.get("/api/outbox").json()["mail"]
    verification = [m for m in outbox if m["purpose"] == "registration"]
    assert verification
    text = verification[0]["text"]
    code = next(
        word.strip(".") for word in text.split()
        if word.strip(".").isdigit() and len(word.strip(".")) == 6
    )
    confirmed = client.post("/api/settings/verify-email", json={"code": code})
    assert confirmed.status_code == 200
    settings = client.get("/my-jefit/settings")
    assert "Unverified" not in settings.text


def test_no_plaintext_secrets_in_database(fresh_state) -> None:
    client = fresh_state
    client.post(
        "/signup/register",
        data={"email": "s1@example.com", "username": "s1demo",
              "password": "Secret-Pass-2026!"},
        follow_redirects=False,
    )
    client.post("/login/forgot-password",
                data={"email": "s1@example.com"})
    outbox = client.get("/api/outbox").json()["mail"]
    reset_codes = [m.get("verification_code") for m in outbox
                   if m.get("verification_code")]
    database = Path(db.backend().lifecycle.database_path)
    blob = database.read_bytes()
    assert b"Secret-Pass-2026!" not in blob
    for code in reset_codes:
        # six-digit codes may collide with unrelated bytes; assert the code
        # is not stored in any auth/mail table row as text
        connection = sqlite3.connect(database)
        try:
            rows = connection.execute(
                "SELECT template, recipient FROM local_auth_mail_outbox"
            ).fetchall()
        finally:
            connection.close()
        for row in rows:
            for value in row:
                assert code not in str(value)
