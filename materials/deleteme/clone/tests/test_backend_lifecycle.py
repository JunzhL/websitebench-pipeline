"""Persistence, recovery, and concurrent-write proofs for the site backend."""

from __future__ import annotations

import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path

from backend import catalogue, db
from conftest import BUYER
from websitebench.site_backend import SiteBackend


def test_business_state_survives_a_fresh_backend_instance(fresh_state) -> None:
    db.set_subscription_state(
        db.PRIMARY["subject_id"], db.PRIMARY_SUBSCRIPTION, status="paused"
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
            "SELECT status FROM deleteme_subscriptions WHERE subscription_id=?",
            (db.PRIMARY_SUBSCRIPTION,),
        ).fetchone()
    assert row is not None and row[0] == "paused"


def test_backup_is_complete_and_restore_recovers_business_state(
    fresh_state, tmp_path: Path
) -> None:
    lifecycle = db.backend().lifecycle
    destination = tmp_path / "deleteme-backup.sqlite3"
    report = lifecycle.backup(destination)
    assert report["schema_version"] == "websitebench.site-backend-backup.v1"
    assert report["site_id"] == "deleteme"
    with closing(sqlite3.connect(destination)) as backup:
        assert backup.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert backup.execute(
            "SELECT site_id FROM websitebench_site_binding WHERE singleton=1"
        ).fetchone()[0] == "deleteme"
        assert backup.execute(
            "SELECT status FROM deleteme_subscriptions WHERE subscription_id=?",
            (db.PRIMARY_SUBSCRIPTION,),
        ).fetchone()[0] == "active"

    db.set_subscription_state(
        db.PRIMARY["subject_id"], db.PRIMARY_SUBSCRIPTION, status="canceled"
    )
    lifecycle.restore(destination)
    restored = db.subscription(db.PRIMARY["subject_id"], db.PRIMARY_SUBSCRIPTION)
    assert restored is not None and restored["status"] == "active"


def test_concurrent_unique_checkouts_are_lossless(fresh_state) -> None:
    plan = catalogue.BY_KEY["price1Year1Person"]

    def buy(index: int) -> dict:
        email = f"parallel-{index}@example.invalid"
        return db.purchase(
            subject_id=db.ensure_checkout_subject(email),
            plan=plan,
            scenario_id="sandbox-approved",
            idempotency_key=f"parallel-{index:04d}",
            contact={**BUYER, "email": email},
        )

    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(buy, range(8)))

    assert all(result["outcome"] == "approved" for result in results)
    assert len({result["subscription_id"] for result in results}) == 8
    with db.backend().lifecycle.connection() as connection:
        count = connection.execute(
            "SELECT COUNT(*) FROM deleteme_orders WHERE idempotency_key LIKE 'parallel-%'"
        ).fetchone()[0]
    assert count == 8
