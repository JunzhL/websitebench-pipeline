import re


def test_sign_in_dashboard_and_sign_out(client):
    rejected = client.post(
        "/auth/login",
        data={"identifier": "demo_learner", "password": "wrong-password"},
    )
    assert rejected.status_code == 200
    assert "incorrect" in rejected.text

    signed_in = client.post(
        "/auth/login",
        data={"identifier": "demo_learner", "password": "WebsiteBench!2026"},
        follow_redirects=False,
    )
    assert signed_in.status_code == 303
    dashboard = client.get("/dashboard")
    assert dashboard.status_code == 200
    assert "Demo Learner" in dashboard.text
    assert "Solve Me First" in dashboard.text

    assert client.post("/auth/logout", follow_redirects=False).status_code == 303
    assert client.get("/dashboard", follow_redirects=False).status_code == 303


def test_invalid_sign_in_and_guarded_dashboard(client):
    assert client.get("/dashboard", follow_redirects=False).status_code == 303
    empty = client.post("/auth/login", data={})
    assert "Enter your username or email and password" in empty.text


def test_local_registration(client):
    payload = {
        "full_name": "Local Learner",
        "username": "local_learner",
        "email": "local-learner@example.test",
        "password": "LocalPassword!2026",
        "terms": "yes",
    }
    assert client.post("/auth/signup", data=payload, follow_redirects=False).status_code == 303
    verify = client.get("/auth/signup/verify")
    code = re.search(r"Verification code: <code>(\d{6})</code>", verify.text)
    assert code
    completed = client.post(
        "/auth/signup/verify", data={"code": code.group(1)}, follow_redirects=False
    )
    assert completed.status_code == 303
    profile = client.get("/profile")
    assert "Local Learner" in profile.text
    assert "local_learner" in profile.text


def test_password_reset_local_flow(client):
    payload = {"email": "learner@hackerrank.local"}
    for _ in range(3):
        assert client.post(
            "/auth/forgot_password", data=payload, follow_redirects=False
        ).status_code == 303
    verify = client.get("/auth/reset/verify")
    code = re.search(r"Verification code: <code>(\d{6})</code>", verify.text)
    assert code
    assert client.post(
        "/auth/reset/verify", data={"code": code.group(1)}, follow_redirects=False
    ).status_code == 303
    assert client.post(
        "/auth/reset/update",
        data={"password": "Replacement!2026"},
        follow_redirects=False,
    ).status_code == 303
    assert client.get("/dashboard").status_code == 200
