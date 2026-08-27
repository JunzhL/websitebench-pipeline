"""Task-539 membership payment: transactional order + membership write,
declined/retryable handling, idempotent duplicates, and the opaque-scenario
payment-input boundary (card-like fields refused, never stored)."""

from __future__ import annotations

from pathlib import Path

from conftest import ISOLATION, login, make_client

from backend import db


def _checkout(member, scenario: str, plan: str = "yearly", **extra):
    data = {"sub": plan, "scenario_id": scenario}
    data.update(extra)
    return member.post("/elite/checkout", data=data, follow_redirects=False)


def test_checkout_page_renders_sandbox_selector_only(member) -> None:
    page = member.get("/elite/checkout?isMyJefit=true&sub=yearly")
    assert page.status_code == 200
    assert "Subscribe to JEFIT Elite Subscription" in page.text
    assert "$52.49" in page.text
    assert "25%OffFirstYear" in page.text
    assert "sandbox-approved" in page.text
    assert "Simulated approval" in page.text
    # honest labeling + no card input fields
    assert "never accepts card" in page.text
    for forbidden in ('name="card', 'name="cvc', 'name="cvv',
                      'name="expiry'):
        assert forbidden not in page.text.casefold()


def test_monthly_variant_prices(member) -> None:
    page = member.get("/elite/checkout?isMyJefit=true&sub=monthly")
    assert "$12.99" in page.text
    assert "25%OffFirstYear" not in page.text


def test_checkout_requires_login(fresh_state) -> None:
    response = fresh_state.get(
        "/elite/checkout?isMyJefit=true&sub=yearly", follow_redirects=False
    )
    assert response.status_code == 302
    assert response.headers["location"].startswith("/login?redirect=")


def test_approved_writes_order_and_membership_transactionally(member) -> None:
    result = _checkout(member, "sandbox-approved")
    assert result.status_code == 303
    assert result.headers["location"] == "/my-jefit/settings?upgraded=1"
    settings = member.get("/my-jefit/settings")
    assert ">Elite</p>" in settings.text
    assert "renews on 2027-08-18" in settings.text
    # upgrade cards are replaced by the membership line
    assert "Upgrade your account" not in settings.text
    orders = db.orders_for(1)
    assert len(orders) == 1
    order = orders[0]
    assert order["status"] == "approved"
    assert order["amount_minor"] == 5249
    assert order["currency"] == "USD"
    assert order["coupon"] == "25%OffFirstYear"


def test_declined_creates_no_order_and_allows_retry(member) -> None:
    declined = _checkout(member, "sandbox-declined")
    assert declined.status_code == 402
    assert "declined" in declined.text
    assert db.orders_for(1) == []
    settings = member.get("/my-jefit/settings")
    assert "Account Type" in settings.text
    assert ">Free</p>" in settings.text
    retried = _checkout(member, "sandbox-approved")
    assert retried.status_code == 303
    assert len(db.orders_for(1)) == 1


def test_retryable_succeeds_only_on_retry(member) -> None:
    pending = _checkout(member, "sandbox-retry")
    assert pending.status_code == 402
    assert "try again" in pending.text
    assert db.orders_for(1) == []
    second = _checkout(member, "sandbox-approved")
    assert second.status_code == 303
    assert len(db.orders_for(1)) == 1


def test_duplicate_submission_is_idempotent(member) -> None:
    key = "idem-test-0001"
    first = _checkout(member, "sandbox-approved", idempotency_key=key)
    assert first.status_code == 303
    duplicate = _checkout(member, "sandbox-approved", idempotency_key=key)
    assert duplicate.status_code == 303
    assert len(db.orders_for(1)) == 1


def test_unknown_scenario_rejected(member) -> None:
    response = _checkout(member, "sandbox-bogus")
    assert response.status_code == 402
    assert "not recognized" in response.text
    assert db.orders_for(1) == []


def test_card_like_fields_rejected_and_never_stored(member) -> None:
    response = member.post(
        "/elite/checkout",
        data={
            "sub": "yearly",
            "scenario_id": "sandbox-approved",
            "card_number": "4242424242424242",
            "cvv": "123",
            "expiry": "12/29",
        },
        follow_redirects=False,
    )
    assert response.status_code == 402
    assert "refused" in response.text
    assert db.orders_for(1) == []
    blob = Path(db.backend().lifecycle.database_path).read_bytes()
    assert b"4242424242424242" not in blob


def test_card_like_value_rejected_even_in_neutral_field(member) -> None:
    response = member.post(
        "/elite/checkout",
        data={"sub": "yearly", "scenario_id": "4242 4242 4242 4242"},
        follow_redirects=False,
    )
    assert response.status_code == 402
    assert db.orders_for(1) == []


def test_membership_is_actor_isolated(member) -> None:
    assert _checkout(member, "sandbox-approved").status_code == 303
    other = make_client()
    login(other, ISOLATION)
    settings = other.get("/my-jefit/settings")
    assert ">Free</p>" in settings.text
    assert db.orders_for(2) == []


def test_free_tier_limits_render(member) -> None:
    settings = member.get("/my-jefit/settings")
    assert ">Free</p>" in settings.text
    assert "Upgrade your account" in settings.text
    assert "$12.99" in settings.text and "$69.99" in settings.text
    exercises = member.get("/my-jefit/exercises")
    assert "(0/3)" in exercises.text
    for _ in range(3):
        member.post("/api/custom-exercises", json={"name": "Filler Move"})
    fourth = member.post("/api/custom-exercises", json={"name": "Too Many"})
    assert fourth.status_code == 422
