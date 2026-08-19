"""Boot smoke: health endpoints and the public entry."""


def test_healthz(client) -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"ok": True, "site_id": "jefit"}


def test_harbor_health(client) -> None:
    response = client.get("/__websitebench/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_home_serves_marketing_page(client) -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "Your Ultimate Workout Planner" in response.text
    assert "JEFIT" in response.text


def test_admin_reset_requires_token(client) -> None:
    assert client.post("/__admin/reset").status_code == 403
    response = client.post(
        "/__admin/reset",
        headers={"X-WebsiteBench-Admin-Token": "jefit-test-admin"},
    )
    assert response.status_code == 200
    assert response.json()["reset"] is True
