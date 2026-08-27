"""Reset determinism.

Two resets of the same `SEED` must produce byte-identical state, and the reset
must actually reach every table the site owns.  The schema is enumerated from
SQLite rather than from a hand-written list, so a table added later cannot slip
past this gate; columns that are legitimately non-deterministic are declared,
and the declaration is asserted in *both* directions.
"""

from __future__ import annotations

import hashlib
import json

import pytest

from conftest import BUYER, PRIMARY, db, purchase, sign_in

# A fresh random salt per account is correct behaviour, not drift. The vendored
# auth runtime timestamps reset at whole-second precision, so they may remain
# equal or advance depending on whether two resets straddle a clock boundary.
NONDETERMINISTIC_COLUMNS = {
    ("local_auth_accounts", "password_salt"): "a fresh random salt per account",
    ("local_auth_accounts", "password_hash"): "derived from the random salt",
}
OPTIONALLY_NONDETERMINISTIC_COLUMNS = {
    ("local_auth_accounts", "created_at"): "the vendored auth runtime records reset time",
    ("local_auth_accounts", "password_updated_at"): "the vendored auth runtime records reset time",
}


def _tables() -> list[str]:
    with db.backend().lifecycle.connection() as connection:
        rows = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
    return [str(row["name"]) for row in rows]


def _column_digests() -> dict[tuple[str, str], str]:
    digests: dict[tuple[str, str], str] = {}
    with db.backend().lifecycle.connection() as connection:
        for table in _tables():
            columns = [
                str(row["name"])
                for row in connection.execute(f"PRAGMA table_info({table})")
            ]
            rows = [
                dict(row) for row in connection.execute(f"SELECT * FROM {table}")
            ]
            rows.sort(key=lambda row: json.dumps(row, sort_keys=True, default=str))
            for column in columns:
                blob = json.dumps(
                    [row.get(column) for row in rows], sort_keys=True, default=str
                )
                digests[(table, column)] = hashlib.sha256(blob.encode()).hexdigest()
    return digests


def test_the_schema_is_large_enough_to_be_worth_comparing() -> None:
    tables = _tables()
    assert len(tables) >= 12, f"only {len(tables)} tables; the reset looks inert"
    for table in db.BUSINESS_TABLES:
        assert table in tables, table


def test_two_resets_of_the_same_seed_agree() -> None:
    db.reset()
    first = _column_digests()
    db.reset()
    second = _column_digests()

    drift = {
        key
        for key in set(first) | set(second)
        if first.get(key) != second.get(key)
    }
    undeclared = drift - set(NONDETERMINISTIC_COLUMNS) - set(
        OPTIONALLY_NONDETERMINISTIC_COLUMNS
    )
    assert not undeclared, sorted(undeclared)

    stable = set(NONDETERMINISTIC_COLUMNS) - drift
    assert not stable, (
        "these are declared non-deterministic but no longer drift; "
        f"remove them from NONDETERMINISTIC_COLUMNS: {sorted(stable)}"
    )


def test_reset_erases_state_a_journey_created(fresh_state) -> None:
    baseline = db.business_state_dump()

    purchase(fresh_state, attempt="reset-check")
    subject = db.ensure_checkout_subject(BUYER["email"])
    assert db.orders(subject), "the journey wrote nothing; the control is vacuous"
    sign_in(fresh_state, PRIMARY)
    fresh_state.post(
        f"/account/subscription/{db.PRIMARY_SUBSCRIPTION}/cancel",
        follow_redirects=False,
    )
    assert db.business_state_dump() != baseline

    db.reset()
    assert db.business_state_dump() == baseline
    assert db.orders(subject) == []
    assert (
        db.subscription(PRIMARY["subject_id"], db.PRIMARY_SUBSCRIPTION)["status"]
        == "active"
    )


def test_reset_detects_divergent_state() -> None:
    """Negative control: the comparison must notice a single changed row."""

    db.reset()
    baseline = db.business_state_dump()
    with db.backend().lifecycle.connection(transaction=True) as connection:
        connection.execute(
            "UPDATE deleteme_reports SET listings_found = listings_found + 1"
        )
    assert db.business_state_dump() != baseline
    with pytest.raises(AssertionError):
        assert db.business_state_dump() == baseline
    db.reset()
    assert db.business_state_dump() == baseline


def test_seeded_credentials_still_work_after_a_reset(fresh_state) -> None:
    db.reset()
    sign_in(fresh_state, PRIMARY)
    assert fresh_state.get("/account").status_code == 200

    wrong = fresh_state.post(
        "/login",
        data={"email": PRIMARY["email"], "password": "not-the-password"},
        follow_redirects=False,
    )
    assert wrong.status_code == 401
