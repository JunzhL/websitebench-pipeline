from __future__ import annotations


def sign_in(client, email="history@example.test", password="Pasta2026!"):
    response = client.post("/api/auth/sign-in", json={"email":email,"password":password})
    assert response.status_code == 200, response.text
    return response


def booking_payload(**overrides):
    value = {
        "session_id":"pasta-pa-20260926-1300",
        "party_size":1,
        "attendee_name":"History Guest",
        "attendee_email":"history@example.test",
        "scenario_id":"sandbox-approved",
        "idempotency_key":"task-883-browser-submit",
    }
    value.update(overrides)
    return value


def test_public_discovery_and_no_results(client):
    stores = client.get("/api/stores").json()["stores"]
    assert [(row["name"], row["distance_miles"]) for row in stores[:2]] == [
        ("Berkeley", 9.2),
        ("Palo Alto", 27.3),
    ]
    assert stores[0]["qualifying_pasta_session"] == 0
    assert stores[1]["qualifying_pasta_session"] == 1
    response = client.get("/api/classes", params={"q":"pasta","availability":"available","sort":"distance"})
    assert response.status_code == 200
    rows = response.json()["classes"]
    assert rows[0]["title"] == "Fresh Pasta Two Ways"
    assert rows[0]["store_name"] == "Palo Alto"
    assert rows[0]["distance_miles"] == 27.3
    assert client.get("/api/classes", params={"q":"zzzz-no-match-websitebench"}).json()["count"] == 0


def test_local_registration_creates_authenticated_account(client):
    started = client.post("/api/auth/registration", json={
        "first_name":"Task",
        "last_name":"Guest",
        "email":"task883@example.test",
        "password":"Task883Pasta!",
    })
    assert started.status_code == 200, started.text
    payload = started.json()
    assert payload["delivery"] == "local-only"
    assert payload["guidance"].startswith("No email was sent.")
    assert len(payload["verification_code"]) == 6
    verified = client.post(
        "/api/auth/registration/verify",
        json={"code":payload["verification_code"]},
    )
    assert verified.status_code == 200, verified.text
    assert verified.json()["account"]["email_normalized"] == "task883@example.test"
    assert client.get("/api/session").json()["session"]["authenticated"] is True


def test_login_empty_fields_match_observed_validation(client):
    response = client.post("/api/auth/sign-in", json={})
    assert response.status_code == 422
    assert response.json()["errors"] == {
        "email":"Email address is required",
        "password":"Password is required",
    }


def test_signed_out_booking_is_rejected(client):
    response = client.post("/api/bookings", json=booking_payload())
    assert response.status_code == 401
    assert "Sign in" in response.json()["error"]


def test_booking_rejects_payment_credentials(client):
    sign_in(client)
    response = client.post("/api/bookings", json=booking_payload(card_number=None))
    assert response.status_code == 422
    assert "credentials" in response.json()["error"]


def test_task_883_booking_and_idempotency(client):
    sign_in(client)
    first = client.post("/api/bookings", json=booking_payload())
    assert first.status_code == 201, first.text
    booking = first.json()["booking"]
    assert booking["title"] == "Fresh Pasta Two Ways"
    assert booking["store_name"] == "Palo Alto"
    assert booking["starts_at"] == "2026-09-26T13:00:00-07:00"
    assert booking["party_size"] == 1
    assert booking["subtotal_cents"] == booking["total_cents"] == 9900
    assert first.json()["payment"] == {
        "adapter":"local-sandbox","status":"approved","is_simulation":True
    }
    repeat = client.post("/api/bookings", json=booking_payload())
    assert repeat.status_code == 200
    assert repeat.json()["idempotent_replay"] is True
    assert repeat.json()["booking"]["booking_id"] == booking["booking_id"]
    history = client.get("/api/bookings").json()["bookings"]
    assert sum(item["booking_id"] == booking["booking_id"] for item in history) == 1


def test_decline_then_approval_creates_only_approved_booking(client):
    sign_in(client)
    declined = client.post("/api/bookings", json=booking_payload(
        scenario_id="sandbox-declined", idempotency_key="retryable-task-883"
    ))
    assert declined.status_code == 409
    assert declined.json()["payment_status"] == "DECLINED"
    approved = client.post("/api/bookings", json=booking_payload(
        scenario_id="sandbox-approved", idempotency_key="retryable-task-883"
    ))
    assert approved.status_code == 201, approved.text


def test_seeded_history_is_owned_and_exposes_options(client):
    sign_in(client)
    rows = client.get("/api/bookings").json()["bookings"]
    seeded = next(row for row in rows if row["booking_id"] == "SLT-SEED-1001")
    assert seeded["status"] == "confirmed"
    assert seeded["title"] == "Fresh Pasta Two Ways"
    other = client.post("/api/auth/sign-out", json={})
    assert other.status_code == 200
    sign_in(client, "isolation@example.test")
    assert client.get("/api/bookings/SLT-SEED-1001").status_code == 404


def test_branded_recovery_preserves_navigation(client):
    response = client.get("/definitely-missing")
    assert response.status_code == 410
    assert "Primary navigation" in response.text
    assert "/cooking-classes/" in response.text
