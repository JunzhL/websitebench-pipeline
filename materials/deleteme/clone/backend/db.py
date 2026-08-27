"""Clone-local business state for the `deleteme` candidate.

Four boundaries live here rather than in the route handlers, so no handler can
forget one:

* **No card data, ever.**  The source collects card details inside a
  Stripe-hosted iframe.  The clone reproduces no card field at all and offers
  only a named local sandbox scenario.  Any request carrying a card-shaped
  *field name* is refused, and so is a card-shaped *value* smuggled into a field
  with an innocent name.  Nothing resembling a payment key is ever written.
* **No removal PII at checkout.**  DeleteMe exists to remove personal data and
  its checkout deliberately asks for very little: a first name, a last name, an
  email address and one postal address.  Age, phone, previous names, aliases and
  relatives belong to the *removal profile*, which the source only exposes after
  a purchase.  Adding any of them to checkout would misrepresent a privacy
  vendor's own data collection, so checkout refuses them.
* **Synthetic identities only.**  Every seeded person, address and phone number
  is fictional and non-resolvable: `example.invalid` mail domains, placeholder
  streets, `555` telephone prefixes reserved for fiction.
* **One subscriber cannot read another.**  Every read is scoped by
  `subject_id`; another actor's row resolves to `None`, not to a refusal that
  would confirm the row exists.

Money is integer minor units end to end.  Time is derived from `SEED` so two
resets of the same seed produce byte-identical state.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
import re
import sqlite3
import threading
from typing import Any

from backend.catalogue import CURRENCY, Plan
from backend.site_backend_integration import open_site_services

# ---------------------------------------------------------------------------
# payment-input boundary
# ---------------------------------------------------------------------------

PAYMENT_FIELD_RE = re.compile(
    r"(?i)^(?:card|cc)[-_ ]?(?:number|no|num)?$"
    r"|^(?:pan|cvv|cvc|cvv2|csc|securitycode)$"
    r"|^exp(?:iry|iration)?(?:[-_ ]?(?:month|year|date))?$"
    r"|^(?:account|routing|iban|swift)[-_ ]?(?:number|no)?$"
    r"|card|cvv|cvc|iban|creditcard|securitycode|holdername|cardholder"
)
# 12-19 digits, optionally grouped by spaces or dashes: a card number wearing
# somebody else's field name.
CARD_VALUE_RE = re.compile(r"^\d(?:[\d \-]{10,21})\d$")

# ---------------------------------------------------------------------------
# removal-PII boundary (checkout only)
# ---------------------------------------------------------------------------

REMOVAL_PII_FIELD_RE = re.compile(
    r"(?i)age|birth|dob|phone|mobile|telephone"
    r"|previous[-_ ]?name|maiden|alias|nickname"
    r"|relative|family[-_ ]?member|household|associate"
    r"|ssn|social[-_ ]?security"
)

CHECKOUT_FIELDS = ("firstName", "lastName", "email", "address")
CHECKOUT_OPTIONAL_FIELDS = ("selfReportedSource", "coupon", "scenario", "agree_billing",
                            "agree_terms", "term", "qty", "plan")


class PaymentFieldRejected(ValueError):
    """A request tried to hand the clone card data."""


class RemovalPiiRejected(ValueError):
    """A request tried to collect removal PII where the source collects none."""


def reject_payment_fields(payload: dict[str, Any]) -> None:
    for key, value in payload.items():
        name = str(key)
        if PAYMENT_FIELD_RE.search(name) or PAYMENT_FIELD_RE.search(
            name.replace("_", "").replace("-", "")
        ):
            raise PaymentFieldRejected(
                f"field {name!r} looks like card data; this clone takes none"
            )
        text = str(value).strip()
        digits = re.sub(r"\D", "", text)
        if CARD_VALUE_RE.match(text) and 12 <= len(digits) <= 19:
            raise PaymentFieldRejected(
                f"the value of {name!r} is card-shaped; this clone takes none"
            )


def reject_removal_pii(payload: dict[str, Any]) -> None:
    for key in payload:
        if REMOVAL_PII_FIELD_RE.search(str(key)):
            raise RemovalPiiRejected(
                f"checkout does not collect {str(key)!r}; the source collects only "
                "a first name, a last name, an email address and one address"
            )


# ---------------------------------------------------------------------------
# deterministic clock
# ---------------------------------------------------------------------------


def _seed_epoch() -> int:
    """A fixed instant derived from SEED, so a reset is reproducible."""

    raw = os.environ.get("SEED", "1")
    try:
        offset = int(raw) % 366
    except ValueError:
        offset = int(hashlib.sha256(raw.encode()).hexdigest()[:6], 16) % 366
    return 1_780_272_000 + offset * 86_400


def _day(epoch: int, days: int) -> str:
    moment = _dt.datetime.fromtimestamp(epoch, tz=_dt.timezone.utc) + _dt.timedelta(
        days=days
    )
    return moment.strftime("%Y-%m-%d")


def _stamp(epoch: int, days: int) -> str:
    moment = _dt.datetime.fromtimestamp(epoch, tz=_dt.timezone.utc) + _dt.timedelta(
        days=days
    )
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# schema
# ---------------------------------------------------------------------------

SCHEMA = """
CREATE TABLE IF NOT EXISTS deleteme_profiles (
    subject_id TEXT PRIMARY KEY,
    first_name TEXT NOT NULL,
    last_name TEXT NOT NULL,
    email TEXT NOT NULL,
    address TEXT NOT NULL,
    self_reported_source TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS deleteme_removal_profiles (
    subject_id TEXT PRIMARY KEY,
    birth_year TEXT NOT NULL DEFAULT '',
    phone TEXT NOT NULL DEFAULT '',
    previous_names TEXT NOT NULL DEFAULT '',
    aliases TEXT NOT NULL DEFAULT '',
    relatives TEXT NOT NULL DEFAULT '',
    other_addresses TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS deleteme_subscriptions (
    subscription_id TEXT PRIMARY KEY,
    subject_id TEXT NOT NULL,
    plan_key TEXT NOT NULL,
    term_years INTEGER NOT NULL,
    quantity INTEGER NOT NULL,
    status TEXT NOT NULL,
    started_on TEXT NOT NULL,
    renews_on TEXT NOT NULL,
    position INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS deleteme_orders (
    order_id TEXT PRIMARY KEY,
    subject_id TEXT NOT NULL,
    subscription_id TEXT,
    plan_key TEXT NOT NULL,
    amount_minor INTEGER NOT NULL,
    currency TEXT NOT NULL,
    scenario_id TEXT NOT NULL,
    outcome TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    created_at TEXT NOT NULL,
    position INTEGER NOT NULL DEFAULT 0,
    UNIQUE (subject_id, idempotency_key)
);
CREATE TABLE IF NOT EXISTS deleteme_removal_records (
    record_id TEXT PRIMARY KEY,
    subject_id TEXT NOT NULL,
    broker TEXT NOT NULL,
    status TEXT NOT NULL,
    requested_on TEXT NOT NULL,
    completed_on TEXT NOT NULL DEFAULT '',
    position INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS deleteme_reports (
    report_id TEXT PRIMARY KEY,
    subject_id TEXT NOT NULL,
    period TEXT NOT NULL,
    issued_on TEXT NOT NULL,
    listings_found INTEGER NOT NULL,
    listings_removed INTEGER NOT NULL,
    position INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS deleteme_billing_events (
    event_id TEXT PRIMARY KEY,
    subject_id TEXT NOT NULL,
    occurred_on TEXT NOT NULL,
    description TEXT NOT NULL,
    amount_minor INTEGER NOT NULL,
    position INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS deleteme_checkout_receipts (
    session_digest TEXT PRIMARY KEY,
    subject_id TEXT NOT NULL,
    order_id TEXT NOT NULL,
    plan_key TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""

BUSINESS_TABLES = (
    "deleteme_checkout_receipts",
    "deleteme_billing_events",
    "deleteme_reports",
    "deleteme_removal_records",
    "deleteme_orders",
    "deleteme_subscriptions",
    "deleteme_removal_profiles",
    "deleteme_profiles",
)

# ---------------------------------------------------------------------------
# synthetic seed identities
# ---------------------------------------------------------------------------
#
# Every value below is invented.  `example.invalid` can never resolve (RFC 6761
# reserves `.invalid`), the street names are placeholders, and the telephone
# numbers use the 555-01xx range reserved for fiction.  No real person's data
# appears anywhere in this candidate.

PRIMARY = {
    "subject_id": "deleteme-subscriber-primary",
    "email": "avery.quill@example.invalid",
    "display_name": "Avery Quill",
    "password": "OfflineClone!2026",
}
ISOLATION = {
    "subject_id": "deleteme-subscriber-second",
    "email": "morgan.pell@example.invalid",
    "display_name": "Morgan Pell",
    "password": "SecondActor!2026",
}
SEED_ACCOUNTS = (PRIMARY, ISOLATION)

PRIMARY_SUBSCRIPTION = "sub-primary-0001"
ISOLATION_SUBSCRIPTION = "sub-second-0001"

_SEED_PROFILES = (
    (
        PRIMARY["subject_id"],
        "Avery",
        "Quill",
        PRIMARY["email"],
        "418 Placeholder Avenue, Apt 6, Springfield, EX 00001",
        "Podcast",
    ),
    (
        ISOLATION["subject_id"],
        "Morgan",
        "Pell",
        ISOLATION["email"],
        "77 Example Row, Riverton, EX 00002",
        "Search engine",
    ),
)

_SEED_REMOVAL_PROFILES = (
    (
        PRIMARY["subject_id"],
        "1984",
        "+1 555-0142",
        "Avery Marsh",
        "A. Quill",
        "Rowan Quill; Devi Marsh",
        "12 Former Street, Springfield, EX 00001",
    ),
    (
        ISOLATION["subject_id"],
        "1979",
        "+1 555-0188",
        "Morgan Vale",
        "M. Pell",
        "Kit Pell",
        "5 Old Lane, Riverton, EX 00002",
    ),
)

_SEED_BROKERS = (
    "AtlasPeopleIndex",
    "CivicRecordFinder",
    "NeighbourLookupCo",
    "PublicDossierNet",
    "QuickTraceDirectory",
)


def _seed_business(connection: sqlite3.Connection) -> None:
    """Delete and rebuild every table this site owns, in one transaction."""

    epoch = _seed_epoch()
    for table in BUSINESS_TABLES:
        connection.execute(f"DELETE FROM {table}")

    connection.executemany(
        "INSERT INTO deleteme_profiles (subject_id, first_name, last_name, email, "
        "address, self_reported_source, created_at) VALUES (?,?,?,?,?,?,?)",
        [(*row, _stamp(epoch, -400)) for row in _SEED_PROFILES],
    )
    connection.executemany(
        "INSERT INTO deleteme_removal_profiles (subject_id, birth_year, phone, "
        "previous_names, aliases, relatives, other_addresses, updated_at) "
        "VALUES (?,?,?,?,?,?,?,?)",
        [(*row, _stamp(epoch, -30)) for row in _SEED_REMOVAL_PROFILES],
    )
    connection.executemany(
        "INSERT INTO deleteme_subscriptions (subscription_id, subject_id, plan_key, "
        "term_years, quantity, status, started_on, renews_on, position) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        [
            (
                PRIMARY_SUBSCRIPTION,
                PRIMARY["subject_id"],
                "price1Year1Person",
                1,
                1,
                "active",
                _day(epoch, -400),
                _day(epoch, -35),
                0,
            ),
            (
                ISOLATION_SUBSCRIPTION,
                ISOLATION["subject_id"],
                "price2Years2People",
                2,
                2,
                "active",
                _day(epoch, -200),
                _day(epoch, 530),
                0,
            ),
        ],
    )
    connection.executemany(
        "INSERT INTO deleteme_orders (order_id, subject_id, subscription_id, plan_key, "
        "amount_minor, currency, scenario_id, outcome, idempotency_key, created_at, "
        "position) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        [
            (
                "ord-primary-0001",
                PRIMARY["subject_id"],
                PRIMARY_SUBSCRIPTION,
                "price1Year1Person",
                12900,
                CURRENCY,
                "sandbox-approved",
                "approved",
                "seed-primary-initial",
                _stamp(epoch, -400),
                0,
            ),
            (
                "ord-second-0001",
                ISOLATION["subject_id"],
                ISOLATION_SUBSCRIPTION,
                "price2Years2People",
                34900,
                CURRENCY,
                "sandbox-approved",
                "approved",
                "seed-second-initial",
                _stamp(epoch, -200),
                0,
            ),
        ],
    )
    records = []
    for index, broker in enumerate(_SEED_BROKERS):
        records.append(
            (
                f"rec-primary-{index:04d}",
                PRIMARY["subject_id"],
                broker,
                "removed" if index % 2 == 0 else "in-progress",
                _day(epoch, -300 + index * 7),
                _day(epoch, -280 + index * 7) if index % 2 == 0 else "",
                index,
            )
        )
    records.append(
        (
            "rec-second-0000",
            ISOLATION["subject_id"],
            "AtlasPeopleIndex",
            "removed",
            _day(epoch, -190),
            _day(epoch, -170),
            0,
        )
    )
    connection.executemany(
        "INSERT INTO deleteme_removal_records (record_id, subject_id, broker, status, "
        "requested_on, completed_on, position) VALUES (?,?,?,?,?,?,?)",
        records,
    )
    connection.executemany(
        "INSERT INTO deleteme_reports (report_id, subject_id, period, issued_on, "
        "listings_found, listings_removed, position) VALUES (?,?,?,?,?,?,?)",
        [
            (
                "rep-primary-0001",
                PRIMARY["subject_id"],
                "Quarter 1",
                _day(epoch, -300),
                34,
                21,
                0,
            ),
            (
                "rep-primary-0002",
                PRIMARY["subject_id"],
                "Quarter 2",
                _day(epoch, -210),
                18,
                16,
                1,
            ),
            (
                "rep-second-0001",
                ISOLATION["subject_id"],
                "Quarter 1",
                _day(epoch, -110),
                52,
                40,
                0,
            ),
        ],
    )
    connection.executemany(
        "INSERT INTO deleteme_billing_events (event_id, subject_id, occurred_on, "
        "description, amount_minor, position) VALUES (?,?,?,?,?,?)",
        [
            (
                "bil-primary-0001",
                PRIMARY["subject_id"],
                _day(epoch, -400),
                "DeleteMe, one year, 1 person",
                12900,
                0,
            ),
            (
                "bil-second-0001",
                ISOLATION["subject_id"],
                _day(epoch, -200),
                "DeleteMe, two years, 2 people",
                34900,
                0,
            ),
        ],
    )


# ---------------------------------------------------------------------------
# lazy, thread-safe opening
# ---------------------------------------------------------------------------

_lock = threading.Lock()
_services: tuple[Any, Any] | None = None


def services() -> tuple[Any, Any]:
    global _services
    if _services is not None:
        return _services
    with _lock:
        if _services is None:
            backend, auth = open_site_services()
            with backend.lifecycle.connection(transaction=True) as connection:
                connection.executescript(SCHEMA)
            for account in SEED_ACCOUNTS:
                auth.seed_account(**account)
            with backend.lifecycle.connection(transaction=True) as connection:
                empty = (
                    connection.execute(
                        "SELECT COUNT(*) AS total FROM deleteme_profiles"
                    ).fetchone()["total"]
                    == 0
                )
                if empty:
                    _seed_business(connection)
            _services = (backend, auth)
    return _services


def backend() -> Any:
    return services()[0]


def auth() -> Any:
    return services()[1]


def reset() -> None:
    """Restore the seeded state in one vendored transaction."""

    _, auth_store = services()
    auth_store.reset_site_state(
        site_reset=_seed_business,
        seed_accounts=[dict(account) for account in SEED_ACCOUNTS],
    )


def business_state_dump() -> str:
    """Canonical JSON of every site table, for the reset-determinism test."""

    site_backend = backend()
    state: dict[str, list[dict[str, Any]]] = {}
    with site_backend.lifecycle.connection() as connection:
        for table in sorted(BUSINESS_TABLES):
            rows = connection.execute(f"SELECT * FROM {table}").fetchall()
            state[table] = sorted(
                (dict(row) for row in rows), key=lambda row: json.dumps(row, sort_keys=True)
            )
    return json.dumps(state, indent=1, sort_keys=True)


# ---------------------------------------------------------------------------
# reads - every one of them scoped by subject
# ---------------------------------------------------------------------------


def _rows(sql: str, params: tuple[Any, ...]) -> list[dict[str, Any]]:
    with backend().lifecycle.connection() as connection:
        return [dict(row) for row in connection.execute(sql, params).fetchall()]


def _row(sql: str, params: tuple[Any, ...]) -> dict[str, Any] | None:
    found = _rows(sql, params)
    return found[0] if found else None


def profile(subject_id: str) -> dict[str, Any] | None:
    return _row("SELECT * FROM deleteme_profiles WHERE subject_id=?", (subject_id,))


def removal_profile(subject_id: str) -> dict[str, Any] | None:
    return _row(
        "SELECT * FROM deleteme_removal_profiles WHERE subject_id=?", (subject_id,)
    )


def subscriptions(subject_id: str) -> list[dict[str, Any]]:
    return _rows(
        "SELECT * FROM deleteme_subscriptions WHERE subject_id=? "
        "ORDER BY position, subscription_id",
        (subject_id,),
    )


def subscription(subject_id: str, subscription_id: str) -> dict[str, Any] | None:
    # Owner-scoped on purpose: another actor's id resolves to nothing at all,
    # rather than to a refusal that would confirm the row exists.
    return _row(
        "SELECT * FROM deleteme_subscriptions WHERE subject_id=? AND subscription_id=?",
        (subject_id, subscription_id),
    )


def orders(subject_id: str) -> list[dict[str, Any]]:
    return _rows(
        "SELECT * FROM deleteme_orders WHERE subject_id=? ORDER BY created_at, order_id",
        (subject_id,),
    )


def removal_records(subject_id: str) -> list[dict[str, Any]]:
    return _rows(
        "SELECT * FROM deleteme_removal_records WHERE subject_id=? "
        "ORDER BY position, record_id",
        (subject_id,),
    )


def reports(subject_id: str) -> list[dict[str, Any]]:
    return _rows(
        "SELECT * FROM deleteme_reports WHERE subject_id=? ORDER BY position, report_id",
        (subject_id,),
    )


def billing_events(subject_id: str) -> list[dict[str, Any]]:
    return _rows(
        "SELECT * FROM deleteme_billing_events WHERE subject_id=? "
        "ORDER BY position, event_id",
        (subject_id,),
    )


def receipt_for(session_digest: str) -> dict[str, Any] | None:
    return _row(
        "SELECT * FROM deleteme_checkout_receipts WHERE session_digest=?",
        (session_digest,),
    )


# ---------------------------------------------------------------------------
# writes
# ---------------------------------------------------------------------------


def _fingerprint(subject_id: str, plan_key: str, kind: str) -> str:
    return hashlib.sha256(f"deleteme|{subject_id}|{plan_key}|{kind}".encode()).hexdigest()


IDEMPOTENCY_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")


def save_removal_profile(subject_id: str, values: dict[str, str]) -> None:
    epoch = _seed_epoch()
    with backend().lifecycle.connection(transaction=True) as connection:
        connection.execute(
            "INSERT INTO deleteme_removal_profiles (subject_id, birth_year, phone, "
            "previous_names, aliases, relatives, other_addresses, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(subject_id) DO UPDATE SET "
            "birth_year=excluded.birth_year, phone=excluded.phone, "
            "previous_names=excluded.previous_names, aliases=excluded.aliases, "
            "relatives=excluded.relatives, other_addresses=excluded.other_addresses, "
            "updated_at=excluded.updated_at",
            (
                subject_id,
                values.get("birth_year", ""),
                values.get("phone", ""),
                values.get("previous_names", ""),
                values.get("aliases", ""),
                values.get("relatives", ""),
                values.get("other_addresses", ""),
                _stamp(epoch, 0),
            ),
        )


def set_subscription_state(
    subject_id: str, subscription_id: str, *, status: str
) -> dict[str, Any] | None:
    with backend().lifecycle.connection(transaction=True) as connection:
        connection.execute(
            "UPDATE deleteme_subscriptions SET status=? "
            "WHERE subject_id=? AND subscription_id=?",
            (status, subject_id, subscription_id),
        )
    return subscription(subject_id, subscription_id)


def change_plan(
    subject_id: str, subscription_id: str, *, plan: Plan
) -> dict[str, Any] | None:
    with backend().lifecycle.connection(transaction=True) as connection:
        connection.execute(
            "UPDATE deleteme_subscriptions SET plan_key=?, term_years=?, quantity=? "
            "WHERE subject_id=? AND subscription_id=?",
            (plan.key, plan.term_years, plan.quantity, subject_id, subscription_id),
        )
    return subscription(subject_id, subscription_id)


def ensure_checkout_subject(email: str) -> str:
    """A stable, non-guessable subject for an anonymous buyer.

    The source creates the account *after* payment, from an emailed link, so the
    clone has no account at this point either - only a deterministic handle to
    attach the order to.
    """

    digest = hashlib.sha256(f"deleteme-buyer|{email.strip().casefold()}".encode())
    return f"deleteme-buyer-{digest.hexdigest()[:24]}"


def purchase(
    *,
    subject_id: str,
    plan: Plan,
    scenario_id: str,
    idempotency_key: str,
    contact: dict[str, str],
) -> dict[str, Any]:
    """Run the sandbox payment protocol and the business writes together.

    The three payment calls and every row they justify share one SQLite
    transaction, so a decline cannot leave a subscription behind and an
    approval cannot lose one.
    """

    if not IDEMPOTENCY_RE.match(idempotency_key):
        raise ValueError("idempotency key is malformed")
    site_backend = backend()
    epoch = _seed_epoch()
    amount_minor = plan.charge_minor
    fingerprint = _fingerprint(subject_id, plan.key, "initial")

    with site_backend.lifecycle.connection(transaction=True) as connection:
        existing = connection.execute(
            "SELECT * FROM deleteme_orders WHERE subject_id=? AND idempotency_key=?",
            (subject_id, idempotency_key),
        ).fetchone()
        if existing is not None:
            row = dict(existing)
            return {
                "outcome": row["outcome"],
                "duplicate": True,
                "order": row,
                "subscription_id": row["subscription_id"],
            }

        intent = site_backend.payments.create_intent(
            owner=subject_id,
            amount_minor=amount_minor,
            currency=CURRENCY,
            fingerprint=fingerprint,
            idempotency_key=idempotency_key,
            connection=connection,
        )
        attempt = site_backend.payments.attempt(
            flow_id=str(intent["flow_id"]),
            owner=subject_id,
            amount_minor=amount_minor,
            currency=CURRENCY,
            fingerprint=fingerprint,
            scenario_id=scenario_id,
            idempotency_key=idempotency_key,
            connection=connection,
        )
        status = str(attempt.get("status", "")).upper()
        if status != "APPROVED":
            return {
                "outcome": status.casefold() or "rejected",
                "duplicate": False,
                "order": None,
                "subscription_id": None,
            }
        site_backend.payments.consume_approval(
            connection,
            flow_id=str(intent["flow_id"]),
            owner=subject_id,
            amount_minor=amount_minor,
            currency=CURRENCY,
            fingerprint=fingerprint,
        )

        subscription_id = f"sub-{hashlib.sha256(idempotency_key.encode()).hexdigest()[:12]}"
        order_id = f"ord-{hashlib.sha256(idempotency_key.encode()).hexdigest()[12:24]}"
        created = _stamp(epoch, 0)
        connection.execute(
            "INSERT INTO deleteme_profiles (subject_id, first_name, last_name, email, "
            "address, self_reported_source, created_at) VALUES (?,?,?,?,?,?,?) "
            "ON CONFLICT(subject_id) DO UPDATE SET first_name=excluded.first_name, "
            "last_name=excluded.last_name, email=excluded.email, "
            "address=excluded.address, "
            "self_reported_source=excluded.self_reported_source",
            (
                subject_id,
                contact.get("firstName", ""),
                contact.get("lastName", ""),
                contact.get("email", ""),
                contact.get("address", ""),
                contact.get("selfReportedSource", ""),
                created,
            ),
        )
        connection.execute(
            "INSERT INTO deleteme_subscriptions (subscription_id, subject_id, plan_key, "
            "term_years, quantity, status, started_on, renews_on, position) "
            "VALUES (?,?,?,?,?,?,?,?,0) ON CONFLICT(subscription_id) DO NOTHING",
            (
                subscription_id,
                subject_id,
                plan.key,
                plan.term_years,
                plan.quantity,
                "active",
                _day(epoch, 0),
                _day(epoch, 365 * plan.term_years),
            ),
        )
        connection.execute(
            "INSERT INTO deleteme_orders (order_id, subject_id, subscription_id, "
            "plan_key, amount_minor, currency, scenario_id, outcome, idempotency_key, "
            "created_at, position) VALUES (?,?,?,?,?,?,?,?,?,?,0)",
            (
                order_id,
                subject_id,
                subscription_id,
                plan.key,
                amount_minor,
                CURRENCY,
                scenario_id,
                "approved",
                idempotency_key,
                created,
            ),
        )
        connection.execute(
            "INSERT INTO deleteme_billing_events (event_id, subject_id, occurred_on, "
            "description, amount_minor, position) VALUES (?,?,?,?,?,0) "
            "ON CONFLICT(event_id) DO NOTHING",
            (
                f"bil-{order_id}",
                subject_id,
                _day(epoch, 0),
                f"DeleteMe, {plan.years_label.casefold()}",
                amount_minor,
            ),
        )
        order = dict(
            connection.execute(
                "SELECT * FROM deleteme_orders WHERE order_id=?", (order_id,)
            ).fetchone()
        )
    return {
        "outcome": "approved",
        "duplicate": False,
        "order": order,
        "subscription_id": subscription_id,
    }


def record_receipt(
    *, session_digest: str, subject_id: str, order_id: str, plan_key: str
) -> None:
    with backend().lifecycle.connection(transaction=True) as connection:
        connection.execute(
            "INSERT INTO deleteme_checkout_receipts (session_digest, subject_id, "
            "order_id, plan_key, created_at) VALUES (?,?,?,?,?) "
            "ON CONFLICT(session_digest) DO UPDATE SET order_id=excluded.order_id, "
            "subject_id=excluded.subject_id, plan_key=excluded.plan_key",
            (session_digest, subject_id, order_id, plan_key, _stamp(_seed_epoch(), 0)),
        )
