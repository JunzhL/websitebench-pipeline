"""Mail exists only in the seam's local outbox, and never leaks a code."""

from __future__ import annotations

from fastapi.testclient import TestClient

from backend import db
from conftest import PRIMARY


def test_reset_writes_only_to_the_local_outbox(fresh_state: TestClient) -> None:
    response = fresh_state.post(
        "/login/reset-password", data={"username": PRIMARY["email"]}
    )
    assert response.status_code == 200
    outbox = fresh_state.get("/api/outbox").json()["message"]
    assert outbox is not None
    assert outbox["purpose"] == "password-reset"
    assert outbox["status"] == "LOCAL_ONLY"
    assert outbox["recipient"] == PRIMARY["email"]
    assert len(outbox["verification_code"]) == 6
    assert outbox["verification_code"].isdigit()


def test_reset_code_never_appears_in_outbox_body(fresh_state: TestClient) -> None:
    """Negative control: the persisted row must not hold the code."""

    fresh_state.post("/login/reset-password", data={"username": PRIMARY["email"]})
    code = fresh_state.get("/api/outbox").json()["message"]["verification_code"]
    assert code
    site_backend, auth = db.services()
    with auth.connect() as connection:
        rows = connection.execute(
            "SELECT * FROM local_auth_mail_outbox"
        ).fetchall()
    assert rows, "no outbox row was written"
    for row in rows:
        serialized = "|".join("" if value is None else str(value) for value in row)
        assert code not in serialized, "the reset code was persisted in the outbox"
    # nor anywhere in the site's own business tables
    assert code not in db.business_state_dump()


def test_outbox_is_scoped_to_the_requesting_session(
    fresh_state: TestClient,
) -> None:
    from conftest import make_client

    fresh_state.post("/login/reset-password", data={"username": PRIMARY["email"]})
    assert fresh_state.get("/api/outbox").json()["message"] is not None
    stranger = make_client()
    assert stranger.get("/api/outbox").json()["message"] is None


def test_no_outbox_message_before_a_reset_is_requested(
    fresh_state: TestClient,
) -> None:
    fresh_state.get("/login/reset-password")
    assert fresh_state.get("/api/outbox").json()["message"] is None


def test_mail_purposes_come_from_the_runtime_contract() -> None:
    site_backend, _ = db.services()
    purposes = site_backend.config.mail["purposes"]
    assert set(purposes) == {"password-reset", "registration"}
    assert purposes["password-reset"]["secret_variables"] == ["code"]
    rendered = site_backend.mail.issue(
        "password-reset", PRIMARY["email"], {"code": "000000", "minutes": "30"}
    )
    assert rendered["site_id"] == "ipvanish"
    assert rendered["subject"] == "Reset your IPVanish password"
    assert rendered["contains_secret_variables"] is True
