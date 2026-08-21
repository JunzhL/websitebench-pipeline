"""Invariant `payment-input-boundary`.

The source collects card details inside a Stripe-hosted iframe.  This clone
reproduces no card field at all: the only payment input is a named sandbox
scenario from `backend/runtime.json`.  A live payment key or a real card field
anywhere in the candidate is an unconditional rejection, so the two negative
controls below prove the refusal actually fires rather than being asserted.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from conftest import BUYER, CLONE_ROOT, SITE_ROOT, db

RUNTIME = json.loads(
    (SITE_ROOT / "backend" / "runtime.json").read_text(encoding="utf-8")
)

# Field names a real card form would use.  None of them may exist in any served
# document, and every one of them must be refused when submitted.
CARD_FIELD_NAMES = (
    "cardnumber",
    "card_number",
    "cardNumber",
    "cc-number",
    "cvc",
    "cvv",
    "cvv2",
    "csc",
    "exp",
    "expiry",
    "exp_month",
    "expiration-date",
    "securityCode",
    "cardholderName",
    "iban",
)


def _base_payload() -> dict[str, str]:
    return {
        **BUYER,
        "term": "1",
        "qty": "1",
        "scenario": "sandbox-approved",
        "agree_billing": "yes",
        "agree_terms": "yes",
    }


def test_sandbox_scenarios_are_the_only_payment_input(client: TestClient) -> None:
    body = client.get("/checkout?plan=standard&term=1&qty=1").text

    declared = {
        item["id"] for item in RUNTIME["payments"]["local_sandbox"]["scenarios"]
    }
    assert declared == {"sandbox-approved", "sandbox-declined", "sandbox-retry"}
    for scenario in declared:
        assert f'value="{scenario}"' in body, scenario

    # The adapter is the one the runtime contract names, and nothing else.
    assert RUNTIME["payments"]["default_adapter"] == "local-sandbox"
    assert RUNTIME["payments"]["stripe_test"] is None

    # No input of any kind that could take a card.
    inputs = re.findall(r'<input\b[^>]*>', body)
    for tag in inputs:
        name = re.search(r'\bname="([^"]*)"', tag)
        field = (name.group(1) if name else "").casefold()
        assert not db.PAYMENT_FIELD_RE.search(field), tag
        assert 'type="password"' not in tag or field == "password"
    assert 'autocomplete="cc-number"' not in body
    assert "js.stripe.com" not in body
    assert "<iframe" not in body

    # And the honest label is on the page, not just in a comment.
    assert "no card is taken" in body.casefold()


def test_card_field_names_are_rejected(client: TestClient) -> None:
    """Negative control: every card-shaped field name must produce a 422.

    Asserting only that the form has no card field would pass on a server that
    happily accepted one; this proves the server refuses.
    """

    for name in CARD_FIELD_NAMES:
        payload = _base_payload()
        payload[name] = "4242424242424242"
        response = client.post("/checkout", data=payload)
        assert response.status_code == 422, (name, response.status_code)
        assert response.json()["error"] == "payment-field-rejected", name

    # ... and the control can distinguish: the same payload without the field
    # is accepted.
    accepted = client.post(
        "/checkout", data={**_base_payload(), "attempt": "control"},
        follow_redirects=False,
    )
    assert accepted.status_code == 303, accepted.status_code


def test_card_shaped_value_in_another_field_is_rejected(client: TestClient) -> None:
    """Negative control: a card number smuggled into an innocent field name."""

    for value in (
        "4242424242424242",
        "4242 4242 4242 4242",
        "4242-4242-4242-4242",
        "378282246310005",
    ):
        payload = _base_payload()
        payload["selfReportedSource"] = value
        response = client.post("/checkout", data=payload)
        assert response.status_code == 422, (value, response.status_code)
        assert response.json()["error"] == "payment-field-rejected", value

    # A value that merely contains digits is not a card and must still pass.
    ok = client.post(
        "/checkout",
        data={**_base_payload(), "selfReportedSource": "Podcast 2026", "attempt": "b"},
        follow_redirects=False,
    )
    assert ok.status_code == 303, ok.status_code


def test_every_post_surface_screens_for_card_data(client: TestClient) -> None:
    """The boundary belongs to the backend, so it holds on every write route."""

    surfaces = (
        ("/checkout", _base_payload()),
        ("/login", {"email": "a@example.invalid", "password": "x" * 12}),
        ("/password/set", {"password": "x" * 12}),
        ("/account/profile", {"birth_year": "1984"}),
        ("/account/plan", {"subscription_id": "x", "selection": "1-1"}),
    )
    for path, payload in surfaces:
        response = client.post(
            path, data={**payload, "cvc": "123"}, follow_redirects=False
        )
        assert response.status_code == 422, (path, response.status_code)
        assert response.json()["error"] == "payment-field-rejected", path


def test_no_payment_key_is_ever_persisted() -> None:
    """No table column in this clone is even shaped to hold one."""

    forbidden = re.compile(r"(?i)card|cvv|cvc|pan|stripe|secret|token|publishable")
    schema = db.SCHEMA
    columns = re.findall(r"^\s{4}([a-z_]+)\s", schema, re.M)
    assert columns, "schema did not parse"
    offenders = [name for name in columns if forbidden.search(name)]
    assert not offenders, offenders


def test_the_word_sandbox_is_not_a_disguised_card_form() -> None:
    """The shipped checkout template declares no card input on disk either."""

    for template in sorted((CLONE_ROOT / "frontend" / "fragments").glob("*.html")):
        text = template.read_text(encoding="utf-8")
        for tag in re.findall(r"<(?:input|select|textarea)\b[^>]*>", text):
            name = re.search(r'\bname="([^"]*)"', tag)
            field = (name.group(1) if name else "").casefold()
            assert not db.PAYMENT_FIELD_RE.search(field), (template.name, tag)
            autocomplete = re.search(r'\bautocomplete="([^"]*)"', tag)
            assert not (autocomplete or "") or not autocomplete.group(1).startswith(
                "cc-"
            ), (template.name, tag)


@pytest.mark.parametrize("path", ["/checkout"])
def test_unknown_scenario_is_refused(client: TestClient, path: str) -> None:
    response = client.post(path, data={**_base_payload(), "scenario": "real-card"})
    assert response.status_code == 422
    assert response.json()["error"] == "unknown-scenario"
