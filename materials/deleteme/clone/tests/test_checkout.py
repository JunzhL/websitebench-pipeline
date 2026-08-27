"""Invariant `no-removal-pii-collected-at-checkout`, plus the checkout journey.

DeleteMe exists to remove personal data, and its own checkout deliberately asks
for very little: a first name, a last name, an email address and one postal
address.  Age, telephone, previous names, aliases and relatives belong to the
removal profile, which the source only opens after a purchase.  Adding any of
them here would misrepresent a privacy vendor's data collection, so the field
set is asserted exhaustively and the refusal has a negative control.
"""

from __future__ import annotations

import re

from fastapi.testclient import TestClient

from conftest import BUYER, catalogue, db, purchase

# Every input the source's own checkout has, read from the frozen application
# bundle (`CheckoutPage-BGTzsYLQ.js`): four required identity fields and one
# optional attribution question.
EXPECTED_FIELDS = {
    "firstName",
    "lastName",
    "email",
    "address",
    "selfReportedSource",
}
# Machinery, not questions asked of the visitor.
ALLOWED_MACHINERY = {"term", "qty", "attempt", "scenario", "agree_billing",
                     "agree_terms", "coupon"}

REMOVAL_PII_FIELDS = (
    "age",
    "dateOfBirth",
    "birth_year",
    "phone",
    "mobileNumber",
    "previousNames",
    "maidenName",
    "aliases",
    "relatives",
    "householdMembers",
    "ssn",
)


def _fields(body: str) -> set[str]:
    names = set()
    for tag in re.findall(r"<(?:input|select|textarea)\b[^>]*>", body):
        match = re.search(r'\bname="([^"]*)"', tag)
        if match and match.group(1):
            names.add(match.group(1))
    return names


def test_checkout_field_set_matches_the_source(client: TestClient) -> None:
    body = client.get("/checkout?plan=standard&term=1&qty=1").text
    names = _fields(body)
    questions = names - ALLOWED_MACHINERY
    assert questions == EXPECTED_FIELDS, sorted(questions ^ EXPECTED_FIELDS)

    # The source's own labels, verbatim from its bundle.
    for label in (
        "First Name",
        "Last Name",
        "Email Address",
        "Address",
        "How did you hear about us?",
        "1 - Customer Information",
        "2 - Payment Details",
        "3 - Terms and Conditions",
        "Purchase &amp; Start Deleting",
    ):
        assert label in body, label

    # There is no password at checkout: the source sets it later, from a link
    # in an email sent after the purchase.
    assert 'type="password"' not in body


def test_checkout_rejects_removal_profile_fields(client: TestClient) -> None:
    """Negative control: every removal-PII field must be refused with 422."""

    base = {
        **BUYER,
        "term": "1",
        "qty": "1",
        "scenario": "sandbox-approved",
        "agree_billing": "yes",
        "agree_terms": "yes",
    }
    for name in REMOVAL_PII_FIELDS:
        response = client.post("/checkout", data={**base, name: "anything"})
        assert response.status_code == 422, (name, response.status_code)
        assert response.json()["error"] == "removal-pii-rejected", name

    # The control discriminates: the same payload without those fields is taken.
    accepted = client.post(
        "/checkout", data={**base, "attempt": "pii-control"}, follow_redirects=False
    )
    assert accepted.status_code == 303


def test_the_removal_profile_is_a_separate_labelled_surface(subscriber) -> None:
    body = subscriber.get("/account/profile").text
    names = _fields(body)
    assert {"birth_year", "phone", "previous_names", "aliases", "relatives"} <= names
    assert "dm-clone-note" in body
    assert "never observable on the source" in body


def test_validation_uses_the_sources_own_wording(client: TestClient) -> None:
    response = client.post("/checkout", data={"term": "1", "qty": "1"})
    assert response.status_code == 422
    for wording in (
        "Please enter your first name",
        "Please enter your last name",
        "Please enter your email address",
        "Please enter your address",
        "Please accept the terms and conditions",
        "Please review and accept the following to continue",
    ):
        assert wording in response.text, wording


def test_the_selected_plan_reaches_the_checkout(client: TestClient) -> None:
    for term, qty in ((1, 1), (1, 2), (1, 4), (2, 1), (2, 2), (2, 4)):
        plan = catalogue.plan_for(term, qty)
        body = client.get(f"/checkout?plan=standard&term={term}&qty={qty}").text
        assert f'data-plan-key="{plan.key}"' in body, plan.key
        assert plan.summary_line in body, plan.key
        assert plan.total_display in body, plan.key


def test_the_order_amount_is_derived_not_posted(client: TestClient) -> None:
    """A client-supplied amount must never reach the ledger."""

    response = client.post(
        "/checkout",
        data={
            **BUYER,
            "term": "1",
            "qty": "1",
            "scenario": "sandbox-approved",
            "agree_billing": "yes",
            "agree_terms": "yes",
            "amount_minor": "1",
            "total": "0.01",
            "attempt": "derived",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    subject = db.ensure_checkout_subject(BUYER["email"])
    charged = {row["amount_minor"] for row in db.orders(subject)}
    assert 1 not in charged
    assert catalogue.plan_for(1, 1).charge_minor in charged


def test_declined_then_approved_is_the_recovery_path(fresh_state) -> None:
    declined = fresh_state.post(
        "/checkout",
        data={
            **BUYER,
            "term": "1",
            "qty": "1",
            "scenario": "sandbox-declined",
            "agree_billing": "yes",
            "agree_terms": "yes",
            "attempt": "1",
        },
    )
    assert declined.status_code == 402
    assert "declined" in declined.text.casefold()
    subject = db.ensure_checkout_subject(BUYER["email"])
    assert db.subscriptions(subject) == []

    approved = purchase(fresh_state, attempt="2")
    assert approved.status_code == 303
    assert approved.headers["location"] == "/checkout/complete"
    assert len(db.subscriptions(subject)) == 1


def test_resubmitting_the_same_attempt_is_idempotent(fresh_state) -> None:
    first = purchase(fresh_state, attempt="same")
    assert first.status_code == 303
    subject = db.ensure_checkout_subject(BUYER["email"])
    before = len(db.orders(subject))
    second = purchase(fresh_state, attempt="same")
    assert second.status_code == 303
    assert len(db.orders(subject)) == before


def test_confirmation_reports_the_purchase_and_discloses_itself(fresh_state) -> None:
    purchase(fresh_state, attempt="confirm")
    body = fresh_state.get("/checkout/complete").text
    assert "Payment Successful!" in body  # the source's own copy
    assert "Local sandbox order" in body
    assert "dm-clone-note" in body
