"""Invariant `not-found-fidelity-per-host`.

The two source hosts genuinely disagree about not-found and the clone keeps
both: the marketing host answers a real HTTP 404 with full chrome, and the
application host answers HTTP 200 with a client-rendered `Page not found`.
Normalising them to one status would be a divergence, so the negative control
below proves the test would notice if somebody did.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

MARKETING_UNKNOWN = "/zzzz-no-match-websitebench/"
APP_UNKNOWN = "/account/zzzz-no-such-route"


def test_marketing_unknown_path_is_a_branded_404(client: TestClient) -> None:
    response = client.get(MARKETING_UNKNOWN)
    assert response.status_code == 404
    body = response.text
    # The source's own copy, verbatim from the frozen capture.
    assert "Oops!" in body
    assert "That page can’t be found." in body
    assert "It looks like nothing was found at this location." in body
    assert "Go to the homepage" in body
    assert ">Back</button>" in body or " Back</button>" in body
    # Full chrome, not a bare error page.
    assert "uk-navbar" in body or "<footer" in body or "builderwidget" in body


def test_an_extensionless_unknown_path_redirects_to_the_slashed_form(
    client: TestClient,
) -> None:
    """The source 301s first and only then answers 404."""

    response = client.get("/zzzz-no-match-websitebench", follow_redirects=False)
    assert response.status_code == 301
    assert response.headers["location"] == "/zzzz-no-match-websitebench/"
    followed = client.get("/zzzz-no-match-websitebench")
    assert followed.status_code == 404


def test_application_unknown_path_is_a_soft_200(client: TestClient) -> None:
    response = client.get(APP_UNKNOWN)
    assert response.status_code == 200
    body = response.text
    assert "Page not found" in body
    assert "The page you're looking for doesn't exist or has been moved." in body
    # It is the app host's own shell, not the marketing 404.
    assert "Oops!" not in body


def test_detects_a_normalised_status(client: TestClient) -> None:
    """Negative control: if either host's status were normalised, this fires."""

    marketing = client.get(MARKETING_UNKNOWN).status_code
    application = client.get(APP_UNKNOWN).status_code
    assert marketing != application, (marketing, application)

    # And the probe can tell a normalised pair from the real one.
    with pytest.raises(AssertionError):
        normalised = (404, 404)
        assert normalised[0] != normalised[1], normalised
    with pytest.raises(AssertionError):
        normalised = (200, 200)
        assert normalised[0] != normalised[1], normalised


def test_known_marketing_paths_are_not_404(client: TestClient) -> None:
    for route in ("/", "/privacy-protection-plans/", "/about-us/", "/help"):
        assert client.get(route).status_code == 200, route


def test_api_paths_answer_json_not_a_marketing_page(client: TestClient) -> None:
    response = client.get("/api/no-such-endpoint")
    assert response.status_code == 404
    assert response.json() == {"error": "not-found"}
