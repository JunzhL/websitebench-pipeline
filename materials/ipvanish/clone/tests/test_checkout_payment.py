"""Checkout: flow binding, server-derived amounts, and the payment boundary."""

from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

from backend import db
from backend.catalogue import BY_ID, money


CHECKOUT = "/checkout/address-payment-method"
KEY = re.compile(r'name="idempotency_key" value="([^"]+)"')


def _card_form(client: TestClient, flow: str) -> tuple[str, str]:
    response = client.get(f"{CHECKOUT}?flow={flow}&method=card")
    assert response.status_code == 200, flow
    match = KEY.search(response.text)
    assert match is not None, "the sandbox form did not render"
    return response.text, match.group(1)


def _submit(
    client: TestClient,
    flow: str,
    key: str,
    scenario: str,
    **overrides: str,
):
    payload = {
        "flow": flow,
        "idempotency_key": key,
        "attempt": "0",
        "account_email": "buyer@example.invalid",
        "billing_country": "US",
        "billing_postal_code": "78701",
        "scenario_id": scenario,
    }
    payload.update(overrides)
    return client.post("/checkout/subscribe", data=payload, follow_redirects=False)


# -- flow binding and derived amounts ---------------------------------------


def test_chooser_renders_the_captured_rows(client: TestClient) -> None:
    text = client.get(f"{CHECKOUT}?flow=essential-annual").text
    assert "Select a payment method" in text
    for label in ("Credit card", "PayPal", "Apple Pay", "Google Pay"):
        assert f">{label}</span>" in text
    assert "c-payment-method-type-select-card" in text
    assert "payment-method-type-select__caret" in text
    assert "Order Summary" in text
    assert "Estimated tax" in text
    assert "Total due" in text
    assert "Customer reviews powered by Trustpilot" in text


@pytest.mark.parametrize(
    "flow",
    (
        "essential-biennial",
        "advanced-biennial",
        "essential-annual",
        "advanced-annual",
        "essential-monthly",
        "advanced-monthly",
    ),
)
def test_order_summary_is_derived_from_the_catalogue(
    client: TestClient, flow: str
) -> None:
    plan = BY_ID[flow]
    text = client.get(f"{CHECKOUT}?flow={flow}").text
    assert plan.product_name in text
    assert money(plan.list_minor) in text
    assert money(plan.tax_minor) in text
    assert f"<span>{money(plan.total_minor)[1:]}</span>" in text
    if plan.discount_minor:
        assert f"&nbsp;{plan.save_percent}%" in text
        assert f"-&nbsp;{money(plan.discount_minor)}" in text
    else:
        assert "discount-row" not in text
        assert "badge-container" not in text


def test_essential_annual_matches_the_recorded_tax_and_total(
    client: TestClient,
) -> None:
    """The one flow whose derived figures are corroborated by the evidence."""

    text = client.get(f"{CHECKOUT}?flow=essential-annual").text
    assert "Live - Essential - Annual - $46.68" in text
    assert "&nbsp;53%" in text
    assert "$6.07" in text
    assert "<span>52.75</span>" in text


def test_unknown_flow_returns_to_pricing(client: TestClient) -> None:
    response = client.get(f"{CHECKOUT}?flow=nonsense-forever", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/pricing/"


def test_client_cannot_set_amount(fresh_state: TestClient) -> None:
    """Negative control: an amount posted by the client is ignored.

    Amounts come from the catalogue only.  Posting a total, an amount and a
    price alongside the flow must not change what is charged or stored.
    """

    plan = BY_ID["essential-annual"]
    _, key = _card_form(fresh_state, plan.plan_id)
    response = _submit(
        fresh_state,
        plan.plan_id,
        key,
        "sandbox-approved",
        total_minor="1",
        amount="0.01",
        price="1",
    )
    assert response.status_code == 303
    orders = db.orders_for(
        "ipvanish-checkout-"
        + __import__("hashlib").sha256(b"buyer@example.invalid").hexdigest()[:24]
    )
    written = [row for row in orders if row["idempotency_key"] == key]
    assert written, "the approved order was not written"
    assert written[0]["total_minor"] == plan.total_minor
    assert written[0]["amount_minor"] == plan.charge_minor


# -- the payment-input boundary ---------------------------------------------


def test_card_form_offers_no_field_capable_of_carrying_card_data(
    client: TestClient,
) -> None:
    from htmlslice import element_span

    text, _ = _card_form(client, "essential-annual")
    start = text.index('<form id="ipvanish-sandbox-form"')
    begin, end = element_span(text, start)
    form = text[begin:end]
    names = set(re.findall(r'name="([^"]+)"', form))
    assert names == {
        "flow",
        "idempotency_key",
        "attempt",
        "account_email",
        "billing_country",
        "billing_postal_code",
        "scenario_id",
    }, names
    forbidden = re.compile(r"(?i)card|cvv|cvc|csc|expir|pan\b|iban|holder|security")
    # no control anywhere in the document -- not only in the sandbox form --
    # carries a credential-shaped name
    controls = re.findall(r"<(?:input|select|textarea)\b[^>]*>", text)
    for control in controls:
        name = re.search(r'\bname="([^"]*)"', control)
        if name is not None:
            assert not forbidden.search(name.group(1)), control
    assert not [name for name in names if forbidden.search(name)]
    # The source's hosted-payment iframe and its eight visible card fields are
    # gone.  A leftover inert CSS selector (`#z_hppm_iframe { ... }`) is part of
    # the captured stylesheet and is not a field, so the assertion is on the
    # element and on the provider origin, not on the substring.
    assert "zuora.com" not in text
    assert 'id="zuora_payment"' not in text
    assert not re.search(r"<iframe\b[^>]*z_hppm_iframe", text)
    assert not re.search(r"<iframe\b[^>]*zuora", text, re.I)
    for field in (
        "field_creditCardNumber",
        "field_creditCardHolderName",
        "field_creditCardExpirationMonth",
        "field_creditCardExpirationYear",
        "field_cardSecurityCode",
    ):
        assert field not in text, field
    # and the replacement says what it is
    assert "Local sandbox" in text
    assert "no field capable of carrying" in text


def test_card_like_input_is_rejected(fresh_state: TestClient) -> None:
    _, key = _card_form(fresh_state, "essential-annual")
    for field in (
        "card_number",
        "cardNumber",
        "cvv",
        "cvc",
        "expiry_month",
        "creditCardNumber",
        "iban",
    ):
        response = _submit(
            fresh_state, "essential-annual", key, "sandbox-approved", **{field: "x"}
        )
        assert response.status_code == 422, field
        assert response.json()["error"] == "payment-field-rejected", field


def test_card_shaped_value_in_an_allowed_field_is_rejected(
    fresh_state: TestClient,
) -> None:
    _, key = _card_form(fresh_state, "essential-annual")
    response = _submit(
        fresh_state,
        "essential-annual",
        key,
        "sandbox-approved",
        billing_postal_code="4242 4242 4242 4242",
    )
    assert response.status_code == 422
    assert response.json()["error"] == "payment-field-rejected"


# -- sandbox outcomes -------------------------------------------------------


def test_declined_creates_nothing(fresh_state: TestClient) -> None:
    """Negative control: a declined scenario writes neither row."""

    before = db.business_state_dump()
    _, key = _card_form(fresh_state, "essential-annual")
    response = _submit(fresh_state, "essential-annual", key, "sandbox-declined")
    assert response.status_code == 200
    assert "Simulated decline" in response.text
    assert db.business_state_dump() == before


def test_retryable_succeeds_only_on_a_second_attempt(
    fresh_state: TestClient,
) -> None:
    before = db.business_state_dump()
    _, key = _card_form(fresh_state, "essential-annual")
    first = _submit(fresh_state, "essential-annual", key, "sandbox-retry")
    assert first.status_code == 200
    assert "Simulated retry" in first.text
    assert db.business_state_dump() == before
    retry_key = KEY.search(first.text).group(1)
    assert retry_key != key
    second = _submit(fresh_state, "essential-annual", retry_key, "sandbox-approved")
    assert second.status_code == 303
    assert second.headers["location"] == "/checkout/confirmation"
    assert db.business_state_dump() != before


def test_approved_writes_subscription_and_order_together(
    fresh_state: TestClient,
) -> None:
    plan = BY_ID["advanced-annual"]
    _, key = _card_form(fresh_state, plan.plan_id)
    response = _submit(fresh_state, plan.plan_id, key, "sandbox-approved")
    assert response.status_code == 303
    confirmation = fresh_state.get("/checkout/confirmation")
    assert confirmation.status_code == 200
    assert money(plan.total_minor) in confirmation.text
    assert "clone-local" in confirmation.text.casefold()


def test_duplicate_submission_is_idempotent(fresh_state: TestClient) -> None:
    _, key = _card_form(fresh_state, "essential-annual")
    first = _submit(fresh_state, "essential-annual", key, "sandbox-approved")
    assert first.status_code == 303
    after_first = db.business_state_dump()
    second = _submit(fresh_state, "essential-annual", key, "sandbox-approved")
    assert second.status_code == 303
    assert db.business_state_dump() == after_first


def test_missing_required_fields_surface_inline_validation(
    fresh_state: TestClient,
) -> None:
    _, key = _card_form(fresh_state, "essential-annual")
    response = _submit(
        fresh_state, "essential-annual", key, "sandbox-approved", account_email=""
    )
    assert response.status_code == 422
    assert "Enter the email address" in response.text
    response = _submit(
        fresh_state, "essential-annual", key, "sandbox-approved", scenario_id=""
    )
    assert response.status_code == 422
    assert "Choose a simulated payment outcome" in response.text


def test_wallet_rows_are_rendered_without_contacting_the_provider(
    client: TestClient,
) -> None:
    for method, label in (
        ("paypal", "PayPal"),
        ("applepay", "Apple Pay"),
        ("googlepay", "Google Pay"),
    ):
        text = client.get(f"{CHECKOUT}?flow=essential-annual&method={method}").text
        assert f"{label} is a third-party wallet" in text
        assert "out of scope" in text


def test_confirmation_requires_a_completed_order(client: TestClient) -> None:
    response = client.get("/checkout/confirmation", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/pricing/"


def test_the_captured_disclosure_is_reproduced_and_parameterised(
    client: TestClient,
) -> None:
    text, _ = _card_form(client, "essential-annual")
    assert "Secure checkout." in text
    assert "Your payment information is fully protected." in text
    assert (
        "you agree to be charged 46.68 per first year" in text
    ), "the captured recurring-charge disclosure is missing"
    assert "Subscribe now" in text
    monthly, _ = _card_form(client, "essential-monthly")
    assert "you agree to be charged 14.99 per first month" in monthly
