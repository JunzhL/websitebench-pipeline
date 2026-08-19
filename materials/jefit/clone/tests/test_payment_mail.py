"""Mail stays in the local outbox only: no purchase-confirmation purpose is
modeled (none was observed on source), and the two modeled purposes never
leave the seam or persist their secrets."""

from __future__ import annotations

from pathlib import Path

from backend import db


def test_runtime_declares_only_observed_mail_purposes() -> None:
    purposes = set(db.backend().config.mail["purposes"])
    assert purposes == {"registration", "password-reset"}


def test_approved_purchase_sends_no_mail(member) -> None:
    before = member.get("/api/outbox").json()["mail"]
    result = member.post(
        "/elite/checkout",
        data={"sub": "yearly", "scenario_id": "sandbox-approved"},
        follow_redirects=False,
    )
    assert result.status_code == 303
    after = member.get("/api/outbox").json()["mail"]
    assert [m["purpose"] for m in after] == [m["purpose"] for m in before]


def test_verification_mail_is_local_only(member) -> None:
    issued = member.post("/api/settings/resend-verification")
    assert issued.status_code == 200
    assert issued.json()["status"] == "LOCAL_ONLY"
    outbox = member.get("/api/outbox").json()["mail"]
    registration = [m for m in outbox if m["purpose"] == "registration"]
    assert registration
    assert registration[0]["status"] == "LOCAL_ONLY"
    # rendered through the seam template
    assert "Verify your JEFIT account" in registration[0]["subject"]


def test_verification_code_never_persisted(member) -> None:
    member.post("/api/settings/resend-verification")
    outbox = member.get("/api/outbox").json()["mail"]
    text = next(
        m["text"] for m in outbox
        if m["purpose"] == "registration" and m.get("text")
    )
    code = next(
        word.strip(".") for word in text.split()
        if word.strip(".").isdigit() and len(word.strip(".")) == 6
    )
    blob = Path(db.backend().lifecycle.database_path).read_bytes()
    assert f"verification code is {code}".encode() not in blob


def test_reset_mail_recorded_in_seam_outbox_table(fresh_state) -> None:
    fresh_state.post(
        "/login/forgot-password", data={"email": "demo.member@example.com"}
    )
    with db.backend().lifecycle.connection() as connection:
        rows = connection.execute(
            "SELECT purpose, status FROM local_auth_mail_outbox"
        ).fetchall()
    assert ("password-reset", "LOCAL_ONLY") in [tuple(r) for r in rows]
