"""Backend lifecycle: deterministic seeded reset (with a negative
divergence probe), cross-actor isolation, and restart persistence."""

from __future__ import annotations

import json
from pathlib import Path

from conftest import ISOLATION, PRIMARY, login, make_client

from backend import db
from websitebench.site_backend import SiteBackend


def test_reset_reproduces_byte_stable_business_state(fresh_state) -> None:
    baseline = db.business_state_dump()
    db.reset()
    assert db.business_state_dump() == baseline
    db.reset()
    assert db.business_state_dump() == baseline


def test_reset_detects_divergent_state(member) -> None:
    baseline_after_reset = None
    db.reset()
    baseline_after_reset = db.business_state_dump()
    login(member)
    plan_id = member.post("/api/plans").json()["id"]
    member.post(f"/api/plans/{plan_id}/name", json={"name": "Divergence"})
    diverged = db.business_state_dump()
    # the probe: mutated state must be DETECTED as different...
    assert diverged != baseline_after_reset
    assert "Divergence" in diverged
    # ...and a reset must fold it back to the deterministic seed
    db.reset()
    assert db.business_state_dump() == baseline_after_reset


def test_seeded_accounts_and_fixtures(fresh_state) -> None:
    login(fresh_state)
    workouts = fresh_state.get("/my-jefit/workouts").text
    assert "Strength Base 3-Day" in workouts
    assert "New Routine" in workouts
    history = fresh_state.get(
        "/my-jefit/progress/history?date=2026-08-18"
    ).text
    assert "Barbell Bench Press" in history
    stats = fresh_state.get("/my-jefit/progress/body-stats").text
    assert ">185<" in stats and ">175<" in stats
    other = make_client()
    login(other, ISOLATION)
    assert "Strength Base 3-Day" not in other.get("/my-jefit/workouts").text


def test_cross_actor_isolation_full_surface(fresh_state) -> None:
    login(fresh_state)
    primary_csv = fresh_state.get("/my-jefit/settings/export.csv").text
    assert "Strength Base 3-Day" in primary_csv
    other = make_client()
    login(other, ISOLATION)
    other_csv = other.get("/my-jefit/settings/export.csv").text
    assert "Strength Base 3-Day" not in other_csv
    # anonymous visitors reach no member data at all
    anonymous = make_client()
    response = anonymous.get("/my-jefit/settings/export.csv",
                             follow_redirects=False)
    assert response.status_code == 302


def test_restart_persistence(fresh_state) -> None:
    login(fresh_state)
    plan_id = fresh_state.post("/api/plans").json()["id"]
    fresh_state.post(f"/api/plans/{plan_id}/name",
                     json={"name": "Restart Survivor"})
    database_path = Path(db.backend().lifecycle.database_path)
    runtime_path = (
        Path(__file__).resolve().parents[2] / "backend" / "runtime.json"
    )
    # a second SiteBackend over the same file is the restart equivalent
    reopened = SiteBackend.open(
        json.loads(runtime_path.read_text()),
        data_root=database_path.parent,
    )
    reopened.lifecycle.initialize()
    with reopened.lifecycle.connection() as connection:
        row = connection.execute(
            "SELECT name FROM jefit_routines WHERE id=?", (plan_id,)
        ).fetchone()
    assert row is not None and row[0] == "Restart Survivor"


def test_seed_identities_are_synthetic(fresh_state) -> None:
    # the capture account's identity must never appear in the business state
    dump = db.business_state_dump().casefold()
    assert "jz0023" not in dump
    assert "uwaterloo" not in dump
    assert PRIMARY["username"] in dump
