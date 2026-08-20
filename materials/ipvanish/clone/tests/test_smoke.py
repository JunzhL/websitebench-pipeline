"""The clone boots, answers both health contracts, and serves its entry."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_healthz_reports_the_site_id(client: TestClient) -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"ok": True, "site_id": "ipvanish"}


def test_harbor_health_is_exactly_the_agreed_body(client: TestClient) -> None:
    response = client.get("/__websitebench/health")
    assert response.status_code == 200
    assert response.text == '{"status":"ok"}'


def test_home_serves_the_captured_entry(client: TestClient) -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "Best VPN - IP Address Changer for Online Privacy | IPVanish" in response.text
    assert "Security Beyond Your VPN" in response.text


def test_home_ships_the_source_wpml_development_banner(client: TestClient) -> None:
    """A source quirk, reproduced rather than tidied away."""

    response = client.get("/")
    assert (
        "This site is registered on " in response.text
        and "as a development site." in response.text
    )
    assert "otgs-development-site-front-end" in response.text


def test_static_assets_are_served(client: TestClient) -> None:
    response = client.get("/static/site/clone.css")
    assert response.status_code == 200
    assert "ipvanish-sandbox" in response.text
