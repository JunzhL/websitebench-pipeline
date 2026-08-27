"""Invariant `synthetic-identity-only`.

This is a data-removal vendor.  Every seeded person, address, telephone number
and relative in the candidate has to be fictional and non-resolvable, and no
real person's data may appear in any fixture, template, log or asset.
"""

from __future__ import annotations

import re

import pytest

from conftest import CLONE_ROOT, db

# `.invalid` is reserved by RFC 6761 and can never resolve. `example.com`,
# `example.net` and `example.org` are reserved too but *do* resolve, so they are
# not accepted here.
SYNTHETIC_DOMAINS = ("example.invalid",)
# 555-01xx is the range reserved for fiction in North America.
FICTIONAL_PHONE = re.compile(r"555-01\d\d")

EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE = re.compile(r"(?:\+?1[ .-]?)?\(?\d{3}\)?[ .-]?\d{3}[ .-]?\d{4}")

# Files the seed and the shipped templates own.  The captured marketing pages
# are the source's own content and are not this invariant's subject; the
# candidate's *own* fixtures are.
OWNED_FILES = (
    CLONE_ROOT / "backend" / "db.py",
    CLONE_ROOT / "app.py",
    *(CLONE_ROOT / "frontend" / "fragments").glob("*.html"),
    *(CLONE_ROOT / "tests").glob("*.py"),
)


def _seeded_rows() -> list[dict]:
    rows: list[dict] = []
    with db.backend().lifecycle.connection() as connection:
        for table in db.BUSINESS_TABLES:
            rows.extend(
                dict(row) for row in connection.execute(f"SELECT * FROM {table}")
            )
    return rows


def test_seeded_identities_are_synthetic(fresh_state) -> None:
    rows = _seeded_rows()
    assert rows, "no seeded rows at all; the probe is vacuous"

    emails = set()
    phones = set()
    for row in rows:
        for value in row.values():
            text = str(value)
            emails.update(EMAIL.findall(text))
            phones.update(PHONE.findall(text))

    assert emails, "no seeded email addresses found; the probe is vacuous"
    for address in emails:
        domain = address.rsplit("@", 1)[1].casefold()
        assert domain.endswith(SYNTHETIC_DOMAINS), address

    for number in phones:
        assert FICTIONAL_PHONE.search(number), number

    # Addresses are placeholders, not real streets in real towns.
    for row in rows:
        for key in ("address", "other_addresses"):
            value = str(row.get(key, ""))
            if not value:
                continue
            assert re.search(
                r"(?i)placeholder|example|former|old lane", value
            ), value

    # The declared seed accounts agree.
    for account in db.SEED_ACCOUNTS:
        assert account["email"].endswith(SYNTHETIC_DOMAINS), account["email"]
        assert account["subject_id"].startswith("deleteme-subscriber-")


def test_no_real_looking_identity_in_any_owned_file() -> None:
    offenders: list[tuple[str, str]] = []
    for path in OWNED_FILES:
        text = path.read_text(encoding="utf-8")
        for address in EMAIL.findall(text):
            domain = address.rsplit("@", 1)[1].casefold()
            if domain.endswith(SYNTHETIC_DOMAINS):
                continue
            # The source's own published support address is site content, not
            # a seeded identity, and it is reproduced because the source has it.
            if address.casefold() == "support@joindeleteme.com":
                continue
            offenders.append((path.name, address))
    assert not offenders, offenders


def test_detects_a_planted_real_looking_identity(fresh_state) -> None:
    """Negative control: plant a resolvable identity and the probe must fire."""

    def probe(values: list[str]) -> None:
        for text in values:
            for address in EMAIL.findall(text):
                domain = address.rsplit("@", 1)[1].casefold()
                assert domain.endswith(SYNTHETIC_DOMAINS), address
            for number in PHONE.findall(text):
                assert FICTIONAL_PHONE.search(number), number

    clean = [str(value) for row in _seeded_rows() for value in row.values()]
    probe(clean)

    # Assembled from fragments: a literal resolvable address in this file would
    # be a finding in the very scan it exists to prove.
    for planted in (
        "j.smith" + "@" + "gmail.com",
        "contact" + "@" + "a-real-company.co.uk",
        "+1 617-" + "555-2311",
        "(212) " + "867-5309",
    ):
        with pytest.raises(AssertionError):
            probe([*clean, planted])

    # ... and a genuinely synthetic addition still passes.
    probe([*clean, "someone.else@example.invalid", "+1 555-0177"])


def test_the_removal_profile_stores_only_what_the_visitor_typed(subscriber) -> None:
    subscriber.post(
        "/account/profile",
        data={
            "birth_year": "1990",
            "phone": "+1 555-0123",
            "previous_names": "Test Name",
            "aliases": "T. Name",
            "relatives": "Someone Fictional",
            "other_addresses": "1 Placeholder Way",
        },
        follow_redirects=False,
    )
    stored = db.removal_profile(db.PRIMARY["subject_id"])
    assert stored["birth_year"] == "1990"
    assert stored["phone"] == "+1 555-0123"
    # Nothing was sent anywhere: the outbox holds no removal request.
    assert subscriber.get("/api/outbox").json()["messages"] == []
