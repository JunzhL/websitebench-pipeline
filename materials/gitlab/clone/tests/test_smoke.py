from pathlib import Path

import app as app_module


PUBLIC_ROUTES = [
    "/",
    "/why-gitlab/",
    "/pricing/",
    "/explore/projects",
    "/gitlab-org/gitlab-runner",
    "/gitlab-org/gitlab-runner/-/tree/main",
    "/gitlab-org/gitlab-runner/-/commits/main",
    "/gitlab-org/gitlab-runner/-/branches",
    "/gitlab-org/gitlab-runner/-/releases",
    "/users/sign_in",
    "/users/sign_up",
    "/users/password/new",
    "/help",
]


def test_public_routes_and_health(client):
    for route in PUBLIC_ROUTES:
        response = client.get(route)
        assert response.status_code == 200, route
        assert response.headers["content-type"].startswith("text/html"), route
        assert "default-src 'self'" in response.headers["content-security-policy"]

    assert client.get("/healthz").json() == {"ok": True, "site_id": "gitlab"}
    health = client.get("/__websitebench/health")
    assert health.status_code == 200
    assert health.text == '{"status":"ok"}'


def test_search_empty_state_and_not_found(client):
    no_match = client.get("/explore/projects?name=zzzz-no-match-websitebench")
    assert no_match.status_code == 200
    assert "No projects match" in no_match.text
    assert "View all projects" in no_match.text

    missing = client.get("/websitebench-nonexistent-path-zzzz")
    assert missing.status_code == 404
    assert "Page not found" in missing.text
    assert "Explore projects" in missing.text

    api = client.get("/api/no-such-route")
    assert api.status_code == 404
    assert api.json() == {"error": "not-found"}


def test_runtime_has_no_remote_source_references():
    root = Path(app_module.__file__).resolve().parent
    runtime_files = [root / "app.py", root / "static/site.css", root / "static/site.js"]
    for path in runtime_files:
        text = path.read_text(encoding="utf-8")
        assert "https://gitlab.com" not in text, path
        assert "https://about.gitlab.com" not in text, path
        assert "https://docs.gitlab.com" not in text, path


def test_admin_reset_is_guarded(client):
    assert client.post("/__admin/reset").status_code == 403
    response = client.post(
        "/__admin/reset",
        headers={"X-WebsiteBench-Admin-Token": app_module.ADMIN_TOKEN},
    )
    assert response.status_code == 200
    assert response.json() == {"reset": True, "site_id": "gitlab"}
