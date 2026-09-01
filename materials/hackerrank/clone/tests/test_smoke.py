from pathlib import Path


def test_public_routes_and_health(client):
    routes = {
        "/": "Build coding skills",
        "/domains": "Practice challenges",
        "/domains/tutorials/10-days-of-javascript": "10 Days of JavaScript",
        "/challenges/solve-me-first/problem": "Solve Me First",
        "/challenges/solve-me-first/forum": "Discussions and solutions",
        "/contests": "Contests and assessments",
        "/auth/login": "Log in to HackerRank",
        "/auth/signup": "Create your learner account",
        "/auth/forgot_password": "Reset your password",
        "/support": "How can we help?",
    }
    for route, text in routes.items():
        response = client.get(route)
        assert response.status_code == 200, route
        assert text in response.text
    assert client.get("/__websitebench/health").json() == {"status": "ok"}


def test_search_empty_state_and_not_found(client):
    empty = client.get("/domains?search=zzzz-no-match-websitebench")
    assert empty.status_code == 200
    assert "No challenges found" in empty.text
    assert "Browse all challenges" in empty.text

    missing = client.get("/websitebench-nonexistent-path-zzzz")
    assert missing.status_code == 404
    assert "We could not find that page" in missing.text
    assert "Browse practice challenges" in missing.text


def test_runtime_has_no_remote_source_references():
    clone_root = Path(__file__).resolve().parents[1]
    for relative in ("app.py", "static/site.css", "static/site.js"):
        text = (clone_root / relative).read_text(encoding="utf-8").lower()
        assert "http://" not in text
        assert "https://" not in text


def test_admin_reset_is_guarded(client):
    assert client.post("/__admin/reset").status_code == 403
    reset = client.post(
        "/__admin/reset",
        headers={"X-WebsiteBench-Admin-Token": "hackerrank-local-admin"},
    )
    assert reset.status_code == 200
    assert reset.json() == {"reset": True, "site_id": "hackerrank"}
