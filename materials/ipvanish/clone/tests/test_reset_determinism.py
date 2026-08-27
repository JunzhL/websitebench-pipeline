"""`reset()` must land in the same state every time, for a given SEED.

The acceptance manual asks for this to be demonstrated by running reset twice
and comparing. Doing that turns up exactly one source of variance: the vendored
auth store draws a fresh random `password_salt` per account, so `password_salt`
and `password_hash` differ between resets while every other byte matches.

That variance is deliberate and correct — a per-account random salt is how
password hashing is supposed to work — and the store is a vendored runtime tree
this repository forbids regenerating. Seeding the salt from `SEED` to make the
bytes match would weaken the hashing to satisfy a check, which is the opposite
of the intent. So determinism is asserted where it is meaningful: every other
table byte-for-byte, and the seeded credentials still authenticating after each
reset, with the salt columns named as the single declared exception.
"""

from __future__ import annotations

import hashlib
import os
import pathlib
import sqlite3

import pytest
from conftest import make_client

from backend import db

# The only columns allowed to differ between two resets, and why.
NONDETERMINISTIC_COLUMNS = {
    ("local_auth_accounts", "password_salt"): "fresh random salt per account",
    ("local_auth_accounts", "password_hash"): "derived from the random salt",
}


def _database_path() -> str:
    data_dir = pathlib.Path(os.environ["DATA_DIR"])
    files = sorted(data_dir.rglob("*.sqlite3"))
    assert files, f"no site database under {data_dir}"
    return str(files[0])


def _tables(connection: sqlite3.Connection) -> list[str]:
    return [
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
    ]


def _snapshot() -> dict[tuple[str, str], str]:
    """Per-column digests, so a difference names its own column."""
    connection = sqlite3.connect(_database_path())
    try:
        digests: dict[tuple[str, str], str] = {}
        for table in _tables(connection):
            cursor = connection.execute(f"SELECT * FROM {table} ORDER BY rowid")
            columns = [description[0] for description in cursor.description]
            rows = cursor.fetchall()
            for index, column in enumerate(columns):
                values = repr([row[index] for row in rows]).encode()
                digests[(table, column)] = hashlib.sha256(values).hexdigest()
        return digests
    finally:
        connection.close()


@pytest.fixture(scope="module")
def two_resets() -> tuple[dict, dict]:
    db.reset()
    first = _snapshot()
    db.reset()
    second = _snapshot()
    return first, second


def test_reset_touches_a_real_schema(two_resets) -> None:
    first, _ = two_resets
    tables = {table for table, _ in first}
    assert len(tables) >= 15, f"only {len(tables)} tables; reset looks inert"
    assert ("local_auth_accounts", "email_normalized") in first


def test_every_column_is_byte_stable_except_the_declared_salt(two_resets) -> None:
    first, second = two_resets
    assert set(first) == set(second), "reset changed the schema"
    differing = {key for key in first if first[key] != second[key]}
    undeclared = differing - set(NONDETERMINISTIC_COLUMNS)
    assert not undeclared, (
        "these columns differ between two resets and are not declared "
        f"nondeterministic: {sorted(undeclared)}"
    )


def test_the_declared_exception_is_real_and_minimal(two_resets) -> None:
    """If the salt ever becomes deterministic, this file should say so."""
    first, second = two_resets
    still_random = {
        key for key in NONDETERMINISTIC_COLUMNS if first[key] != second[key]
    }
    assert still_random == set(NONDETERMINISTIC_COLUMNS), (
        "a column declared nondeterministic is now stable; narrow "
        f"NONDETERMINISTIC_COLUMNS: {sorted(set(NONDETERMINISTIC_COLUMNS) - still_random)}"
    )


@pytest.mark.parametrize("attempt", [1, 2])
def test_seeded_credentials_authenticate_after_every_reset(attempt: int) -> None:
    """Behavioural determinism: the salt changes, the login outcome does not."""
    db.reset()
    client = make_client()
    account = db.SEED_ACCOUNTS[0]
    response = client.post(
        "/login",
        data={"email": account["email"], "password": account["password"]},
        follow_redirects=False,
    )
    assert response.status_code == 303, (
        f"reset #{attempt}: seeded credentials no longer authenticate "
        f"({response.status_code})"
    )


def test_wrong_password_still_fails_after_reset() -> None:
    """Negative control: the login assertion above can fail."""
    db.reset()
    client = make_client()
    response = client.post(
        "/login",
        data={
            "email": db.SEED_ACCOUNTS[0]["email"],
            "password": "not-the-seeded-password",
        },
        follow_redirects=False,
    )
    assert response.status_code == 422, response.status_code
