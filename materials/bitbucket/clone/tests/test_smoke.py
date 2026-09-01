from pathlib import Path

import app as app_module


PUBLIC_ROUTES = [
    "/",
    "/why-bitbucket/",
    "/pricing/",
    "/repo/all",
    "/atlassianlabs/atlascode",
    "/atlassianlabs/atlascode/src/main",
    "/atlassianlabs/atlascode/commits/main",
    "/atlassianlabs/atlascode/branches",
    "/atlassianlabs/atlascode/downloads",
    "/account/signin/",
    "/account/signup/",
    "/account/password/reset/",
    "/legal/terms/",
    "/legal/privacy/",
    "/help",
]


def test_public_routes_and_health(client):
    for route in PUBLIC_ROUTES:
        response = client.get(route)
        assert response.status_code == 200, route
        assert response.headers["content-type"].startswith("text/html"), route
        assert "default-src 'self'" in response.headers["content-security-policy"]

    assert client.get("/healthz").json() == {"ok": True, "site_id": "bitbucket"}
    health = client.get("/__websitebench/health")
    assert health.status_code == 200
    assert health.text == '{"status":"ok"}'


def test_search_empty_state_and_not_found(client):
    no_match = client.get("/repo/all?name=zzzz-no-match-websitebench")
    assert no_match.status_code == 200
    assert "No repositories found" in no_match.text
    assert "View all repositories" in no_match.text

    missing = client.get("/websitebench-nonexistent-path-zzzz")
    assert missing.status_code == 404
    assert "Page not found" in missing.text
    assert "Return to Developer Tools records and actions" in missing.text
    assert "href=&#x27;/repo/all&#x27;" not in missing.text
    assert "href='/repo/all'" in missing.text

    api = client.get("/api/no-such-route")
    assert api.status_code == 404
    assert api.json() == {"error": "not-found"}


def test_public_account_entries_and_help_are_safe(client):
    sign_in = client.get("/account/signin/")
    assert "Username or primary email" in sign_in.text
    assert "Password" in sign_in.text
    assert "Continue with Google" in sign_in.text
    assert "Continue with Microsoft" in sign_in.text

    registration = client.get("/account/signup/")
    assert "First name" in registration.text
    assert "Last name" in registration.text
    assert "href=\"/legal/terms/\"" in registration.text
    assert "href=\"/legal/privacy/\"" in registration.text
    assert "No real email is sent" in registration.text

    reset = client.get("/account/password/reset/")
    assert "Email" in reset.text
    assert "whether or not an account exists" in reset.text
    assert "Return to sign in" in reset.text
    validation = client.post("/account/password/reset/", data={"email": ""})
    assert validation.status_code == 200
    assert "Enter your email address" in validation.text

    help_page = client.get("/support/")
    assert "Developer Tools records and actions" in help_page.text
    assert "account access and failed actions" in help_page.text
    assert "displays no private account data" in help_page.text


def test_runtime_has_no_remote_source_references():
    root = Path(app_module.__file__).resolve().parent
    runtime_files = [root / "app.py", root / "static/site.css", root / "static/site.js"]
    for path in runtime_files:
        text = path.read_text(encoding="utf-8")
        assert "https://bitbucket.org" not in text, path
        assert "https://about.bitbucket.org" not in text, path
        assert "https://docs.bitbucket.org" not in text, path


def test_admin_reset_is_guarded(client):
    assert client.post("/__admin/reset").status_code == 403
    response = client.post(
        "/__admin/reset",
        headers={"X-WebsiteBench-Admin-Token": app_module.ADMIN_TOKEN},
    )
    assert response.status_code == 200
    assert response.json() == {"reset": True, "site_id": "bitbucket"}
