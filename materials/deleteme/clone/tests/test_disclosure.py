"""Invariant `clone-local-surfaces-are-labelled`.

Recording inferred or unavailable evidence as observed is an unconditional
rejection.  Every surface whose behaviour was never observable on the source
therefore carries a *visible* clone-local notice naming why - and "visible"
means real text in the served body, not a comment and not a class name.
"""

from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

from conftest import BUYER, purchase, sign_in

NOTICE_MARKER = 'data-clone-local="'
UNOBSERVED_REASON = "never observable on the source"

# Every page the frozen scope records as unavailable or inferred.
ANONYMOUS_SURFACES = (
    "/password/set",
)
SUBSCRIBER_SURFACES = (
    "/account",
    "/account/profile",
    "/account/reports",
    "/account/billing",
    "/account/plan",
)


def _visible_text(body: str) -> str:
    body = re.sub(r"<script\b.*?</script>", " ", body, flags=re.S | re.I)
    body = re.sub(r"<style\b.*?</style>", " ", body, flags=re.S | re.I)
    body = re.sub(r"<!--.*?-->", " ", body, flags=re.S)
    return re.sub(r"<[^>]+>", " ", body)


def _carries_notice(body: str) -> bool:
    if NOTICE_MARKER not in body:
        return False
    text = _visible_text(body).casefold()
    return "clone-local surface" in text


def test_every_unobserved_surface_carries_a_notice(fresh_state) -> None:
    checked = 0

    for route in ANONYMOUS_SURFACES:
        body = fresh_state.get(route).text
        assert _carries_notice(body), route
        assert UNOBSERVED_REASON in body, route
        checked += 1

    # The password-reset success state.
    fresh_state.get("/password/forgot")
    submitted = fresh_state.post(
        "/password/forgot", data={"email": "robin.vale@example.invalid"}
    )
    assert submitted.status_code == 200
    assert _carries_notice(submitted.text)
    assert "The password-reset success state" in submitted.text
    checked += 1

    # The post-purchase confirmation.
    purchase(fresh_state, attempt="disclosure")
    confirmation = fresh_state.get("/checkout/complete").text
    assert _carries_notice(confirmation)
    checked += 1

    # The checkout itself: the field set is the source's, the layout is not.
    checkout = fresh_state.get("/checkout?plan=standard&term=1&qty=1").text
    assert _carries_notice(checkout)
    assert "expired session" in checkout
    checked += 1

    # The whole subscriber tree.
    sign_in(fresh_state)
    for route in SUBSCRIBER_SURFACES:
        body = fresh_state.get(route).text
        assert _carries_notice(body), route
        assert UNOBSERVED_REASON in body, route
        checked += 1

    assert checked == len(ANONYMOUS_SURFACES) + len(SUBSCRIBER_SURFACES) + 3


def test_pause_cancel_and_reactivate_are_labelled(subscriber) -> None:
    """The three subscription controls eight frozen traces describe, none of
    which was observable."""

    body = subscriber.get("/account").text
    for action in ("pause", "cancel", "reactivate"):
        assert f'data-subscription-action="{action}"' in body, action
    assert _carries_notice(body)


def test_an_observed_surface_is_not_falsely_labelled(client: TestClient) -> None:
    """The disclosure must be specific.  A notice on a page the capture *did*
    observe would misdescribe real evidence as inference, which is the same
    error in the other direction."""

    for route in ("/", "/privacy-protection-plans/", "/login", "/help", "/about-us/"):
        body = client.get(route).text
        assert NOTICE_MARKER not in body, route


def test_detects_an_unlabelled_inferred_surface(subscriber) -> None:
    """Negative control: strip the notice and the check must fail."""

    body = subscriber.get("/account").text
    assert _carries_notice(body)

    damaged = re.sub(
        r'<div class="dm-clone-note"[^>]*>.*?</div>', "", body, flags=re.S
    )
    assert damaged != body, "the control removed nothing"
    assert not _carries_notice(damaged), "the probe cannot see the notice at all"

    with pytest.raises(AssertionError):
        assert _carries_notice(damaged), "/account"


def test_the_notice_names_the_reason_not_just_the_fact(subscriber) -> None:
    body = subscriber.get("/account/profile").text
    assert "only after a purchase" in body
    assert "offline-clone inference" in body
