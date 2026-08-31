from __future__ import annotations

from fastapi.testclient import TestClient


def payload(**overrides):
    value = {
        "slot_id": "cle-20260905-1400-120",
        "party_size": 4,
        "first_name": "Test",
        "last_name": "Player",
        "phone": "416-555-0188",
        "email": "player@example.test",
        "accessibility_request": "",
        "special_request": "Near the entrance",
        "terms_accepted": True,
        "scenario_id": "sandbox-approved",
        "idempotency_key": "task-886-browser-submit",
    }
    value.update(overrides)
    return value


def start_session(client):
    response = client.get("/api/session")
    assert response.status_code == 200
    return response


def verify_phone(client, phone="416-555-0188"):
    start_session(client)
    started = client.post("/api/auth/phone/start", json={"phone": phone})
    assert started.status_code == 200, started.text
    assert started.json()["delivery"] == "local-only"
    assert started.json()["guidance"].startswith("No SMS was sent.")
    assert "code" not in started.json()
    verified = client.post("/api/auth/phone/verify", json={"use_local_code": True})
    assert verified.status_code == 200, verified.text
    return verified


def test_public_discovery_nearest_location_and_no_results(client):
    venues = client.get("/api/venues").json()["venues"]
    assert [(row["venue_id"], row["distance_km"]) for row in venues] == [
        ("cleveland", 311.3),
        ("avon", 324.5),
        ("detroit-auburn-hills", 333.9),
    ]
    no_match = client.get("/api/venues", params={"q": "zzzz-no-match-websitebench"})
    assert no_match.status_code == 200
    assert no_match.json()["count"] == 0
    page = client.get("/us/experience/")
    assert page.status_code == 200
    assert page.headers["x-page-id"] == "experience"


def test_task_886_availability_and_quote(client):
    slots = client.get(
        "/api/venues/cleveland/availability", params={"date": "2026-09-05"}
    ).json()["slots"]
    at_two = [row for row in slots if row["starts_at"].startswith("2026-09-05T14:00")]
    assert [(row["duration_minutes"], row["price_cents"], row["available"]) for row in at_two] == [
        (120, 8800, 1), (90, 6600, 1), (60, 4400, 0)
    ]
    quote = client.post(
        "/api/booking/quote",
        json={"slot_id": "cle-20260905-1400-120", "party_size": 4},
    )
    assert quote.status_code == 200
    value = quote.json()["quote"]
    assert value["venue_name"] == "Topgolf Cleveland"
    assert value["starts_at"] == "2026-09-05T14:00:00-04:00"
    assert value["duration_minutes"] == 120
    assert value["party_size"] == 4
    assert value["bay_count"] == 1
    assert value["subtotal_cents"] == value["total_cents"] == 8800
    assert quote.json()["creates_hold"] is False


def test_task_886_guest_booking_confirmation_and_idempotency(client):
    start_session(client)
    first = client.post("/api/reservations", json=payload())
    assert first.status_code == 201, first.text
    reservation = first.json()["reservation"]
    assert reservation["venue_name"] == "Topgolf Cleveland"
    assert reservation["starts_at"] == "2026-09-05T14:00:00-04:00"
    assert reservation["duration_minutes"] == 120
    assert reservation["party_size"] == 4
    assert reservation["bay_count"] == 1
    assert reservation["subtotal_cents"] == reservation["total_cents"] == 8800
    assert first.json()["payment"] == {
        "adapter": "local-sandbox", "status": "approved", "is_simulation": True
    }
    replay = client.post("/api/reservations", json=payload())
    assert replay.status_code == 200
    assert replay.json()["idempotent_replay"] is True
    assert replay.json()["reservation"]["reservation_id"] == reservation["reservation_id"]
    persisted = client.get(f"/api/reservations/{reservation['reservation_id']}")
    assert persisted.status_code == 200
    assert persisted.json()["reservation"]["total_cents"] == 8800


def test_required_fields_and_payment_credentials_fail_before_effect(client):
    start_session(client)
    missing = client.post("/api/reservations", json={})
    assert missing.status_code == 422
    assert "First name" in missing.json()["error"]
    probe = client.post("/api/reservations", json=payload(card_number="synthetic-probe"))
    assert probe.status_code == 422
    assert "credentials" in probe.json()["error"]


def test_decline_retry_and_then_approval(client):
    start_session(client)
    declined = client.post(
        "/api/reservations",
        json=payload(scenario_id="sandbox-declined", idempotency_key="task-886-decline"),
    )
    assert declined.status_code == 409
    assert declined.json()["payment_status"] == "DECLINED"
    retry = client.post(
        "/api/reservations",
        json=payload(scenario_id="sandbox-retry", idempotency_key="task-886-retry"),
    )
    assert retry.status_code == 409
    assert retry.json()["payment_status"] == "RETRYABLE"
    approved = client.post(
        "/api/reservations",
        json=payload(idempotency_key="task-886-approved"),
    )
    assert approved.status_code == 201


def test_phone_validation_favorite_migration_history_and_management(client):
    start_session(client)
    invalid = client.post("/api/auth/phone/start", json={"phone": "12"})
    assert invalid.status_code == 422
    assert "valid mobile" in invalid.json()["errors"]["phone"]
    assert client.post("/api/favorites/cleveland", json={}).json()["saved"] is True
    booked = client.post("/api/reservations", json=payload(idempotency_key="phone-owner-booking"))
    reservation_id = booked.json()["reservation"]["reservation_id"]
    verify_phone(client)
    session = client.get("/api/session").json()
    assert session["authenticated"] is True
    assert session["account"]["verified_by"] == "mobile-number"
    assert client.get("/api/favorites/cleveland").json()["saved"] is True
    rows = client.get("/api/reservations").json()["reservations"]
    assert [row["reservation_id"] for row in rows] == [reservation_id]
    moved = client.post(
        f"/api/reservations/{reservation_id}/actions",
        json={"action": "reschedule", "slot_id": "cle-20260912-1400-120"},
    )
    assert moved.status_code == 200, moved.text
    assert moved.json()["reservation"]["status"] == "rescheduled"
    cancelled = client.post(
        f"/api/reservations/{reservation_id}/actions", json={"action": "cancel"}
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["reservation"]["status"] == "cancelled"
    assert cancelled.json()["reservation"]["refund_status"] == "refunded"


def test_phone_invalid_code_budget_and_returning_identity(client):
    start_session(client)
    assert client.post("/api/auth/phone/start", json={"phone": "416-555-0188"}).status_code == 200
    for attempt in range(5):
        response = client.post("/api/auth/phone/verify", json={"code": "000000"})
        assert response.status_code == 409
        if attempt == 4:
            assert "locked" in response.json()["error"]

    client.post("/__admin/reset", headers={"x-websitebench-admin-token": "test-reset-token"})
    first = verify_phone(client)
    assert first.json()["created"] is True
    client.post("/api/auth/sign-out", json={})
    second = verify_phone(client)
    assert second.json()["created"] is False


def test_history_permission_and_owner_isolation(client, app_module):
    start_session(client)
    assert client.get("/api/reservations").status_code == 401
    booked = client.post("/api/reservations", json=payload(idempotency_key="owner-a"))
    reservation_id = booked.json()["reservation"]["reservation_id"]
    with TestClient(app_module.app, base_url="https://testserver") as other:
        verify_phone(other, "647-555-0199")
        assert other.get(f"/api/reservations/{reservation_id}").status_code == 404
        forbidden = other.post(
            f"/api/reservations/{reservation_id}/actions", json={"action": "cancel"}
        )
        assert forbidden.status_code == 403


def test_branded_404_and_protected_reset(client):
    missing = client.get("/definitely-missing")
    assert missing.status_code == 404
    assert missing.headers["x-page-id"] == "not-found"
    assert "/us/experience/" in missing.text
    assert client.post("/__admin/reset").status_code == 403
