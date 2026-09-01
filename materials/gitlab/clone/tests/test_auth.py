import re


def test_sign_in_dashboard_and_sign_out(client):
    rejected = client.post(
        "/users/sign_in",
        data={"identifier": "developer", "password": "wrong-password"},
    )
    assert rejected.status_code == 200
    assert "Invalid login or password" in rejected.text

    signed_in = client.post(
        "/users/sign_in",
        data={"identifier": "developer", "password": "WebsiteBench!2026"},
        follow_redirects=False,
    )
    assert signed_in.status_code == 303
    dashboard = client.get("/dashboard")
    assert dashboard.status_code == 200
    assert "platform-demo" in dashboard.text

    signed_out = client.post("/users/sign_out", follow_redirects=False)
    assert signed_out.status_code == 303
    assert client.get("/dashboard", follow_redirects=False).status_code == 303


def test_registration_duplicate_submit_reuses_active_flow(client):
    payload = {
        "first_name": "Local",
        "last_name": "User",
        "username": "local-user",
        "email": "local-user@example.test",
        "password": "local-password",
        "terms": "yes",
    }
    responses = [
        client.post("/users/sign_up", data=payload, follow_redirects=False)
        for _ in range(12)
    ]
    assert {response.status_code for response in responses} == {303}
    assert all(response.headers.get("retry-after") is None for response in responses)

    verify_page = client.get("/users/sign_up/verify")
    code = re.search(r"Verification code: <code>(\d{6})</code>", verify_page.text)
    assert code
    completed = client.post(
        "/users/sign_up/verify",
        data={"code": code.group(1)},
        follow_redirects=False,
    )
    assert completed.status_code == 303
    assert "local-user" in client.get("/profile").text


def test_registration_cooldown_returns_retryable_page_not_http_429(client):
    first = {
        "first_name": "Local",
        "last_name": "User",
        "username": "local-user",
        "email": "local-user@example.test",
        "password": "local-password",
        "terms": "yes",
    }
    changed = {
        **first,
        "username": "changed-user",
        "email": "changed-user@example.test",
    }

    assert client.post("/users/sign_up", data=first, follow_redirects=False).status_code == 303
    limited = client.post("/users/sign_up", data=changed, follow_redirects=False)

    assert limited.status_code == 200
    assert int(limited.headers["retry-after"]) > 0
    assert "A verification request is already active." in limited.text
    assert "data-retry-after" in limited.text


def test_password_reset_repeat_does_not_issue_another_request(client):
    payload = {"email": "developer@gitlab.local"}
    responses = [
        client.post("/users/password/new", data=payload, follow_redirects=False)
        for _ in range(12)
    ]
    assert {response.status_code for response in responses} == {303}
    assert all(response.headers.get("retry-after") is None for response in responses)

    verify_page = client.get("/users/password/verify")
    code = re.search(r"Verification code: <code>(\d{6})</code>", verify_page.text)
    assert code
    assert client.post(
        "/users/password/verify",
        data={"code": code.group(1)},
        follow_redirects=False,
    ).status_code == 303
    updated = client.post(
        "/users/password/update",
        data={"password": "Replacement!2026"},
        follow_redirects=False,
    )
    assert updated.status_code == 303
    assert client.get("/dashboard").status_code == 200
