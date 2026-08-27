"""Deterministic reset, cross-actor isolation, restart persistence."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from backend import db
from conftest import (
    ISOLATION,
    ISOLATION_SUBSCRIPTION,
    PRIMARY_SUBSCRIPTION,
    make_client,
    sign_in,
)
from websitebench.site_backend import SiteBackend


def test_reset_is_byte_stable(fresh_state: TestClient) -> None:
    first = db.business_state_dump()
    db.reset()
    second = db.business_state_dump()
    assert first == second


def test_reset_detects_divergent_state(fresh_state: TestClient) -> None:
    """Negative control: a mutation must be visible before a reset folds it back."""

    baseline = db.business_state_dump()
    db.update_billing_contact(
        db.PRIMARY_SUBJECT,
        full_name="Divergent Name",
        email="divergent@example.invalid",
        country="GB",
        postal_code="SW1A 1AA",
    )
    mutated = db.business_state_dump()
    assert mutated != baseline, "the dump cannot see its own business state"
    db.reset()
    assert db.business_state_dump() == baseline


def test_seed_holds_the_declared_fixtures(fresh_state: TestClient) -> None:
    primary = db.subscriptions_for(db.PRIMARY_SUBJECT)
    statuses = {row["subscription_id"]: row["status"] for row in primary}
    assert statuses[PRIMARY_SUBSCRIPTION] == "active"
    assert any(status == "canceled" for status in statuses.values())
    orders = db.orders_for(db.PRIMARY_SUBJECT)
    kinds = {row["kind"] for row in orders}
    assert {"initial", "renewal"} <= kinds
    assert db.billing_contact(db.PRIMARY_SUBJECT) is not None
    isolation = db.subscriptions_for(db.ISOLATION_SUBJECT)
    assert [row["subscription_id"] for row in isolation] == [ISOLATION_SUBSCRIPTION]


def test_seed_identities_are_synthetic(fresh_state: TestClient) -> None:
    dump = db.business_state_dump()
    assert "@example.invalid" in dump
    for real in ("@ipvanish.com", "@gmail.com", "@outlook.com"):
        assert real not in dump, real


def test_cross_actor_isolation(fresh_state: TestClient) -> None:
    """Negative control: one actor cannot see or mutate another's rows."""

    assert db.subscription(db.PRIMARY_SUBJECT, ISOLATION_SUBSCRIPTION) is None
    assert db.subscription(db.ISOLATION_SUBJECT, PRIMARY_SUBSCRIPTION) is None
    assert (
        db.set_subscription_state(
            db.PRIMARY_SUBJECT, ISOLATION_SUBSCRIPTION, status="canceled"
        )
        is None
    )
    still = db.subscription(db.ISOLATION_SUBJECT, ISOLATION_SUBSCRIPTION)
    assert still is not None and still["status"] == "active"

    sign_in(fresh_state)
    over_http = fresh_state.post(
        f"/account/subscription/{ISOLATION_SUBSCRIPTION}/cancel",
        follow_redirects=False,
    )
    assert over_http.status_code == 404
    mine = fresh_state.get("/account/").text
    assert ISOLATION_SUBSCRIPTION not in mine

    other = make_client()
    sign_in(other, ISOLATION)
    theirs = other.get("/account/billing").text
    assert "ord_primary_initial" not in theirs


def test_subscription_lifecycle_is_real_local_behaviour(
    subscriber: TestClient,
) -> None:
    for action, expected in (
        ("pause", "paused"),
        ("resume", "active"),
        ("cancel", "canceled"),
        ("reactivate", "active"),
    ):
        response = subscriber.post(
            f"/account/subscription/{PRIMARY_SUBSCRIPTION}/{action}",
            follow_redirects=False,
        )
        assert response.status_code == 303, action
        row = db.subscription(db.PRIMARY_SUBJECT, PRIMARY_SUBSCRIPTION)
        assert row is not None and row["status"] == expected, action


def test_unknown_subscription_action_is_not_found(subscriber: TestClient) -> None:
    response = subscriber.post(
        f"/account/subscription/{PRIMARY_SUBSCRIPTION}/detonate",
        follow_redirects=False,
    )
    assert response.status_code == 404


def test_restart_persistence(fresh_state: TestClient) -> None:
    """A second SiteBackend over the same file is the restart equivalent."""

    db.update_billing_contact(
        db.PRIMARY_SUBJECT,
        full_name="Persisted Name",
        email="persisted@example.invalid",
        country="AU",
        postal_code="2000",
    )
    database_path = Path(db.backend().lifecycle.database_path)
    runtime_path = Path(__file__).resolve().parents[2] / "backend" / "runtime.json"
    reopened = SiteBackend.open(
        json.loads(runtime_path.read_text(encoding="utf-8")),
        data_root=database_path.parent,
    )
    reopened.lifecycle.initialize()
    with reopened.lifecycle.connection() as connection:
        row = connection.execute(
            "SELECT full_name FROM ipvanish_billing_contacts WHERE subject_id=?",
            (db.PRIMARY_SUBJECT,),
        ).fetchone()
    assert row is not None and row[0] == "Persisted Name"
    db.reset()


def test_admin_reset_requires_the_token(client: TestClient) -> None:
    refused = client.post("/__admin/reset")
    assert refused.status_code == 403
    allowed = client.post(
        "/__admin/reset",
        headers={"X-WebsiteBench-Admin-Token": "ipvanish-test-admin"},
    )
    assert allowed.status_code == 200
    assert allowed.json() == {"reset": True, "site_id": "ipvanish"}
