"""Sign-in, recovery, and the subscriber auth boundary."""

from __future__ import annotations

from fastapi.testclient import TestClient

from conftest import ISOLATION, PRIMARY, make_client, sign_in


COOKIE = "__Host-websitebench-ipvanish-session"


def test_signin_reproduces_the_captured_sso_view(client: TestClient) -> None:
    text = client.get("/login").text
    # the motto is lower-case in the DOM and upper-cased by CSS on the source
    assert "Reclaim your " in text
    assert "online privacy" in text
    assert "Welcome back!" in text
    assert "Sign in to continue to customer portal" in text
    assert ">Email address</div>" in text
    assert ">Password</div>" in text
    assert "Forgot password?" in text
    assert "Not a member?" in text
    assert "Sign up now!" in text
    assert 'name="email"' in text
    assert 'name="password"' in text


def test_signup_now_points_at_pricing(client: TestClient) -> None:
    """The only registration path this source offers."""

    text = client.get("/login").text
    assert 'href="/pricing/"' in text


def test_no_third_party_identity_provider_buttons(client: TestClient) -> None:
    """None were observed on the source, so none is invented."""

    lowered = client.get("/login").text.casefold()
    for phrase in (
        "continue with google",
        "sign in with google",
        "continue with apple",
        "sign in with apple",
        "continue with facebook",
        "sign in with microsoft",
    ):
        assert phrase not in lowered, phrase


def test_signin_sets_a_host_only_session_cookie(fresh_state: TestClient) -> None:
    response = fresh_state.post("/login", data=dict(PRIMARY), follow_redirects=False)
    assert response.status_code == 303
    header = response.headers["set-cookie"]
    assert header.startswith(COOKIE + "=")
    assert "HttpOnly" in header
    assert "Secure" in header
    assert "SameSite=Lax" in header
    assert "Path=/" in header
    assert "Domain" not in header


def test_empty_credentials_surface_validation(fresh_state: TestClient) -> None:
    response = fresh_state.post(
        "/login", data={"email": "", "password": ""}, follow_redirects=False
    )
    assert response.status_code == 422
    assert "Enter your email address and password." in response.text


def test_wrong_credentials_are_refused_without_enumerating(
    fresh_state: TestClient,
) -> None:
    response = fresh_state.post(
        "/login",
        data={"email": PRIMARY["email"], "password": "not-the-password"},
        follow_redirects=False,
    )
    assert response.status_code == 422
    assert "do not match" in response.text
    unknown = fresh_state.post(
        "/login",
        data={"email": "nobody@example.invalid", "password": "not-the-password"},
        follow_redirects=False,
    )
    assert unknown.status_code == 422
    assert "do not match" in unknown.text


def test_signed_out_subscriber_route_redirects(client: TestClient) -> None:
    """Negative control for the auth boundary, preserving the destination."""

    for route in (
        "/account/",
        "/account/billing",
        "/account/plan",
        "/account/billing-contact",
    ):
        response = client.get(route, follow_redirects=False)
        assert response.status_code == 303, route
        assert response.headers["location"] == f"/login?next={route}", route


def test_authenticated_visit_to_signin_goes_to_the_dashboard(
    subscriber: TestClient,
) -> None:
    response = subscriber.get("/login", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/account/"


def test_sign_out_revokes_the_session(subscriber: TestClient) -> None:
    response = subscriber.post("/logout", follow_redirects=False)
    assert response.status_code == 303
    follow = subscriber.get("/account/", follow_redirects=False)
    assert follow.status_code == 303
    assert follow.headers["location"].startswith("/login")


def test_login_next_only_accepts_a_local_destination(
    fresh_state: TestClient,
) -> None:
    response = fresh_state.post(
        "/login",
        data={**PRIMARY, "next": "https://evil.example.com/"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/account/"


def test_recovery_reproduces_the_source_typo(client: TestClient) -> None:
    text = client.get("/login/reset-password").text
    assert "Reset password" in text
    assert (
        "Enter you account email, you will receive a reset password code" in text
    ), "the source typo must be reproduced verbatim"
    assert ">Email address</div>" in text
    assert 'name="username"' in text
    assert "Back to sign in" in text
    assert "Send code" in text


def test_recovery_empty_address_surfaces_validation(fresh_state: TestClient) -> None:
    response = fresh_state.post(
        "/login/reset-password", data={"username": ""}, follow_redirects=False
    )
    assert response.status_code == 422
    assert "Enter you account email." in response.text


def test_recovery_answer_is_neutral_for_an_unknown_address(
    fresh_state: TestClient,
) -> None:
    known = fresh_state.post(
        "/login/reset-password", data={"username": PRIMARY["email"]}
    )
    other = make_client()
    unknown = other.post(
        "/login/reset-password", data={"username": "nobody@example.invalid"}
    )
    assert known.status_code == 200
    assert unknown.status_code == 200
    assert "local outbox" in known.text
    assert "local outbox" in unknown.text


def test_two_actors_hold_independent_sessions(fresh_state: TestClient) -> None:
    sign_in(fresh_state, PRIMARY)
    other = make_client()
    sign_in(other, ISOLATION)
    mine = fresh_state.get("/account/").text
    theirs = other.get("/account/").text
    assert PRIMARY["email"] in mine
    assert ISOLATION["email"] in theirs
    assert ISOLATION["email"] not in mine
    assert PRIMARY["email"] not in theirs
