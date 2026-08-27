"""Routes, titles and the source's 404-with-home-body behaviour."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


MARKETING = (
    ("/", "Best VPN - IP Address Changer for Online Privacy | IPVanish"),
    ("/pricing/", "Pricing Information - View All VPN Plans | IPVanish"),
    ("/why-vpn/", "<title>"),
    ("/what-is-a-vpn/", "<title>"),
    ("/servers/", "<title>"),
    ("/vpn-features/", "<title>"),
    ("/vpn-features/threat-protection/", "<title>"),
    ("/money-back-guarantee/", "<title>"),
    ("/coupons/", "<title>"),
    ("/vpn-locations/", "<title>"),
    ("/reviews/", "<title>"),
    ("/trust/", "<title>"),
    ("/no-log-vpn-policy/", "<title>"),
    ("/secure-browser/", "<title>"),
    ("/cloud-storage/", "<title>"),
    ("/vpn-setup/windows/", "<title>"),
    ("/vpn-for-streaming/", "<title>"),
    ("/resources/", "<title>"),
    ("/setup-guides/", "<title>"),
    ("/what-is-my-ip-address/", "<title>"),
    ("/blog/", "<title>"),
    ("/tos/", "<title>"),
    ("/privacy-policy/", "<title>"),
    ("/partners/", "<title>"),
    ("/press/", "<title>"),
    ("/support", "Support Center"),
    ("/login", "Welcome back!"),
    ("/login/reset-password", "Reset password"),
)


@pytest.mark.parametrize(("route", "marker"), MARKETING)
def test_route_serves_its_captured_document(
    client: TestClient, route: str, marker: str
) -> None:
    response = client.get(route)
    assert response.status_code == 200, route
    assert marker in response.text, route


def test_unslashed_marketing_paths_redirect(client: TestClient) -> None:
    """The source 301s the unslashed form; captured markup links to both."""

    for route in ("/pricing", "/why-vpn", "/servers"):
        response = client.get(route, follow_redirects=False)
        assert response.status_code == 308, route
        assert response.headers["location"] == route + "/"


def test_not_found_answers_404_with_the_home_body(client: TestClient) -> None:
    """Source behaviour: HTTP 404 whose body is the home page."""

    home = client.get("/")
    missing = client.get("/zzzz-no-match-websitebench")
    assert missing.status_code == 404
    assert missing.text == home.text


def test_not_found_is_not_a_branded_page(client: TestClient) -> None:
    """Negative control: this source ships no branded not-found view.

    Trace ht-22 expects one; the source has none, and reproducing the source is
    the contract.  If a future change introduces a branded 404 this fails.
    """

    response = client.get("/zzzz-no-match-websitebench")
    assert response.status_code == 404
    lowered = response.text.lower()
    assert "page not found" not in lowered
    assert "not found" not in lowered
    assert ">404<" not in response.text
    assert "zzzz-no-match-websitebench" not in response.text
    # navigation is intact, because the body really is the home document
    assert "Security Beyond Your VPN" in response.text
    assert 'id="ast-hf-menu-1"' in response.text


def test_home_nav_states_are_addressable(client: TestClient) -> None:
    for value, marker in (
        ("product", "menu-item-139281"),
        ("apps", "menu-item-139449"),
        ("resources", "menu-item-139506"),
    ):
        response = client.get(f"/?nav={value}")
        assert response.status_code == 200
        assert marker in response.text
        assert "ast-menu-hover" in response.text


def test_rendered_top_level_nav_is_the_captured_five(client: TestClient) -> None:
    """The rendered nav carries only these, even though markup holds more."""

    text = client.get("/").text
    for label in ("Product", "Apps", "Resources", "Help", "Pricing"):
        assert f">{label}<" in text
    assert ">My Account<" in text
    assert ">Get Started<" in text


def test_external_links_resolve_to_a_local_boundary(client: TestClient) -> None:
    text = client.get("/").text
    assert "/external/" in text
    slug = text.split("/external/", 1)[1].split('"', 1)[0]
    response = client.get(f"/external/{slug}")
    assert response.status_code == 200
    assert "This link leaves the captured site" in response.text


def test_unknown_external_slug_is_not_found(client: TestClient) -> None:
    response = client.get("/external/no-such-boundary-slug")
    assert response.status_code == 404


def test_support_no_results_offers_a_route_back_to_plans(client: TestClient) -> None:
    response = client.get("/support/search?query=zzzz-no-match-websitebench")
    assert response.status_code == 200
    assert "No results for" in response.text
    assert 'href="/pricing/"' in response.text
    assert "Support Categories" not in response.text


def test_support_home_reproduces_the_captured_centre(client: TestClient) -> None:
    text = client.get("/support").text
    assert "Support Categories" in text
    assert "Frequently Asked Questions" in text
    assert "System Status: " in text
    assert "Ongoing Maintenance" in text
    assert 'placeholder="How can we help you?"' in text


def test_api_namespace_404s_as_json(client: TestClient) -> None:
    response = client.get("/api/no-such-endpoint")
    assert response.status_code == 404
    assert response.json() == {"error": "not-found"}
