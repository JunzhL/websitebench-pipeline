"""Invariant `subscriber-isolation`.

A signed-in seeded subscriber never sees the other seeded subscriber's removal
records, reports, addresses or billing history.  Reads are owner-scoped in
`backend/db.py`, so another actor's identifier resolves to nothing at all rather
than to a refusal that would confirm the row exists.
"""

from __future__ import annotations

import pytest

from conftest import (
    ISOLATION,
    ISOLATION_SUBSCRIPTION,
    PRIMARY,
    PRIMARY_SUBSCRIPTION,
    db,
    make_client,
    sign_in,
)

# Values that belong to the *other* actor and must never appear.
ISOLATION_FINGERPRINTS = (
    ISOLATION["email"],
    "Morgan",
    "Pell",
    "77 Example Row",
    "+1 555-0188",
    ISOLATION_SUBSCRIPTION,
    "rep-second-0001",
    "bil-second-0001",
    "rec-second-0000",
)
PRIMARY_FINGERPRINTS = (
    PRIMARY["email"],
    "Avery",
    "418 Placeholder Avenue",
    PRIMARY_SUBSCRIPTION,
)


def test_second_subscriber_records_are_invisible(fresh_state) -> None:
    sign_in(fresh_state, PRIMARY)
    seen = ""
    for route in (
        "/account",
        "/account/profile",
        "/account/reports",
        "/account/billing",
        "/account/plan",
    ):
        response = fresh_state.get(route)
        assert response.status_code == 200, route
        seen += response.text

    for fingerprint in ISOLATION_FINGERPRINTS:
        assert fingerprint not in seen, fingerprint
    # ... and the actor does see their own, so the probe is not vacuous.
    for fingerprint in PRIMARY_FINGERPRINTS:
        assert fingerprint in seen, fingerprint

    # The mirror image: the second actor sees theirs and not the first's.
    other = make_client()
    sign_in(other, ISOLATION)
    seen_other = "".join(
        other.get(route).text
        for route in ("/account", "/account/profile", "/account/billing")
    )
    assert ISOLATION["email"] in seen_other
    assert PRIMARY["email"] not in seen_other
    assert "418 Placeholder Avenue" not in seen_other


def test_a_cross_actor_write_is_refused(fresh_state) -> None:
    sign_in(fresh_state, PRIMARY)
    before = db.subscription(ISOLATION["subject_id"], ISOLATION_SUBSCRIPTION)
    response = fresh_state.post(
        f"/account/subscription/{ISOLATION_SUBSCRIPTION}/cancel",
        follow_redirects=False,
    )
    # The application host answers an unknown route with 200, so a foreign id
    # is indistinguishable from a route that does not exist - which is the
    # point.
    assert response.status_code == 200
    assert "Page not found" in response.text
    after = db.subscription(ISOLATION["subject_id"], ISOLATION_SUBSCRIPTION)
    assert after == before

    response = fresh_state.post(
        "/account/plan",
        data={"subscription_id": ISOLATION_SUBSCRIPTION, "selection": "1-1"},
        follow_redirects=False,
    )
    assert response.status_code == 200
    assert db.subscription(ISOLATION["subject_id"], ISOLATION_SUBSCRIPTION) == before


def test_signed_out_sees_nothing(fresh_state) -> None:
    for route in ("/account", "/account/profile", "/account/billing"):
        response = fresh_state.get(route, follow_redirects=False)
        assert response.status_code == 303, route
        assert response.headers["location"] == "/login"


def test_detects_a_cross_account_read(fresh_state) -> None:
    """Negative control: an unscoped read must be caught.

    `db.subscription` is owner-scoped.  The same query without the owner clause
    returns the other actor's row, and the probe below must notice.
    """

    scoped = db.subscription(PRIMARY["subject_id"], ISOLATION_SUBSCRIPTION)
    assert scoped is None, "an owner-scoped read returned a foreign row"

    with db.backend().lifecycle.connection() as connection:
        unscoped = connection.execute(
            "SELECT * FROM deleteme_subscriptions WHERE subscription_id=?",
            (ISOLATION_SUBSCRIPTION,),
        ).fetchone()
    assert unscoped is not None, "the fixture row is missing; the control is vacuous"

    with pytest.raises(AssertionError):
        assert dict(unscoped).get("subject_id") == PRIMARY["subject_id"]

    # And the page-level probe fires on planted foreign content.
    sign_in(fresh_state, PRIMARY)
    body = fresh_state.get("/account").text
    damaged = body.replace("</main>", f"<p>{ISOLATION['email']}</p></main>", 1)
    with pytest.raises(AssertionError):
        for fingerprint in ISOLATION_FINGERPRINTS:
            assert fingerprint not in damaged, fingerprint
