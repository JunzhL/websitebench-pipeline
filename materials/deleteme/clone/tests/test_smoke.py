"""The clone boots, answers both health contracts, and serves its entry page."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_site_health_names_the_site(client: TestClient) -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"ok": True, "site_id": "deleteme"}


def test_harbor_health_is_exactly_status_ok(client: TestClient) -> None:
    response = client.get("/__websitebench/health")
    assert response.status_code == 200
    # Byte-exact: Harbor's ABI reads this literal.
    assert response.text == '{"status":"ok"}'
    assert response.json() == {"status": "ok"}


def test_entry_page_is_the_captured_home_document(client: TestClient) -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "Your Personal Data is Yours Again with DeleteMe." in response.text
    assert "DeleteMe: Remove Personal Data from Internet &amp; Data Brokers" in (
        response.text
    ) or "<title>DeleteMe: Remove Personal Data" in response.text


def test_static_mount_serves_the_mirror(client: TestClient) -> None:
    response = client.get("/static/site/clone.css")
    assert response.status_code == 200
    assert "dm-clone-note" in response.text


def test_every_declared_route_answers(client: TestClient) -> None:
    from conftest import JOURNEY_ROUTES

    for route in JOURNEY_ROUTES:
        response = client.get(route)
        assert response.status_code in {200, 404}, (route, response.status_code)
        assert response.text.strip(), route


def test_the_dead_join_now_anchor_is_reproduced(client: TestClient) -> None:
    """The desktop header CTA points at `#pricing`, and the home page has no
    such element.  The source ships it broken; a "fix" would be a divergence."""

    body = client.get("/").text
    assert 'href="#pricing"' in body
    assert 'id="pricing"' not in body
