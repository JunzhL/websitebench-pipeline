"""Clone-local business state, opened only through the vendored seam.

Auth, sessions, mail and payments belong to ``websitebench``; this module owns
the site's own tables in the same site-isolated SQLite database and binds them
to auth accounts by ``subject_id``.

Everything under ``ipvanish_subscriptions`` / ``ipvanish_orders`` /
``ipvanish_billing_contacts`` is **clone-local inference**: IPVanish gates
account creation behind a purchase, so no rendered subscriber state was ever
observed on the source (``scope/routes.json`` records the route
``unavailable``).  The behaviour here is real local business behaviour, but it
is not a reproduction of anything captured.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import threading
from typing import Any

from websitebench.local_clone_auth import AuthConflict  # noqa: F401  (re-export)
from websitebench.site_backend import PaymentError

from .catalogue import BY_ID, CURRENCY, Plan
from .site_backend_integration import open_site_services


# --------------------------------------------------------------------------
# payment-input boundary
# --------------------------------------------------------------------------

# The candidate must not offer, accept, store or log anything card-shaped. This
# rejects a credential-shaped *key* as well as a credential-shaped *value*, so a
# renamed field cannot smuggle a PAN through.
PAYMENT_FIELD_RE = re.compile(
    r"(?i)^(card|cc)[-_ ]?(number|no|num)?$|^(pan|cvv|cvc|cvv2|csc)$"
    r"|^exp(iry|iration)?([-_ ]?(month|year|date))?$"
    r"|^(account|routing|iban|swift)[-_ ]?(number|no)?$"
    r"|card|cvv|cvc|iban|creditcard|securitycode|holdername"
)
CARD_VALUE_RE = re.compile(r"^[\d](?:[\d \-]{10,21})[\d]$")


class PaymentFieldRejected(ValueError):
    """A credential-shaped payment field reached the clone-local checkout."""


def reject_payment_fields(payload: dict[str, Any]) -> None:
    for key, value in payload.items():
        normalized = str(key).strip()
        if PAYMENT_FIELD_RE.search(normalized.replace("_", "").replace("-", "")):
            raise PaymentFieldRejected(f"field {normalized!r} is not accepted")
        if PAYMENT_FIELD_RE.search(normalized):
            raise PaymentFieldRejected(f"field {normalized!r} is not accepted")
        text = str(value).strip()
        if CARD_VALUE_RE.fullmatch(text) and len(re.sub(r"\D", "", text)) >= 12:
            raise PaymentFieldRejected(
                f"value submitted in {normalized!r} looks like a card number"
            )


# --------------------------------------------------------------------------
# deterministic seed
# --------------------------------------------------------------------------

SEED_ACCOUNTS = (
    {
        "subject_id": "ipvanish-subscriber-primary",
        "email": "avery.sandoval@example.invalid",
        "display_name": "Avery Sandoval",
        "password": "Vanish-Demo-2026!",
    },
    {
        "subject_id": "ipvanish-subscriber-isolation",
        "email": "morgan.reyes@example.invalid",
        "display_name": "Morgan Reyes",
        "password": "Isolate-Demo-2026!",
    },
)
PRIMARY_SUBJECT = SEED_ACCOUNTS[0]["subject_id"]
ISOLATION_SUBJECT = SEED_ACCOUNTS[1]["subject_id"]


def _seed_epoch() -> int:
    """A deterministic clock base so a reset is byte-stable for a given SEED."""

    raw = os.environ.get("SEED", "1").strip() or "1"
    try:
        offset = int(raw)
    except ValueError:
        offset = int(hashlib.sha256(raw.encode()).hexdigest()[:8], 16)
    # 2026-06-01T00:00:00Z, shifted one day per seed step.
    return 1780272000 + (offset % 366) * 86400


def _day(epoch: int, days: int) -> str:
    import datetime

    moment = datetime.datetime.fromtimestamp(
        epoch + days * 86400, tz=datetime.timezone.utc
    )
    return moment.strftime("%Y-%m-%d")


SCHEMA = """
CREATE TABLE IF NOT EXISTS ipvanish_accounts (
    subject_id TEXT PRIMARY KEY,
    email TEXT NOT NULL,
    display_name TEXT NOT NULL,
    created_on TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS ipvanish_subscriptions (
    subscription_id TEXT PRIMARY KEY,
    subject_id TEXT NOT NULL,
    plan_id TEXT NOT NULL,
    status TEXT NOT NULL,
    started_on TEXT NOT NULL,
    renews_on TEXT NOT NULL,
    renewal_price_minor INTEGER NOT NULL,
    paused_on TEXT,
    canceled_on TEXT,
    position INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS ipvanish_orders (
    order_id TEXT PRIMARY KEY,
    subject_id TEXT NOT NULL,
    subscription_id TEXT,
    plan_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    amount_minor INTEGER NOT NULL,
    tax_minor INTEGER NOT NULL,
    total_minor INTEGER NOT NULL,
    currency TEXT NOT NULL,
    status TEXT NOT NULL,
    scenario_id TEXT,
    idempotency_key TEXT,
    charged_on TEXT NOT NULL,
    position INTEGER NOT NULL DEFAULT 0,
    UNIQUE (subject_id, idempotency_key)
);
CREATE TABLE IF NOT EXISTS ipvanish_billing_contacts (
    subject_id TEXT PRIMARY KEY,
    full_name TEXT NOT NULL,
    email TEXT NOT NULL,
    country TEXT NOT NULL,
    postal_code TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS ipvanish_checkout_receipts (
    session_digest TEXT PRIMARY KEY,
    order_id TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS ipvanish_support_articles (
    slug TEXT PRIMARY KEY,
    section TEXT NOT NULL,
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    position INTEGER NOT NULL
);
"""

BUSINESS_TABLES = (
    "ipvanish_checkout_receipts",
    "ipvanish_orders",
    "ipvanish_subscriptions",
    "ipvanish_billing_contacts",
    "ipvanish_accounts",
    "ipvanish_support_articles",
)

# Support centre content transcribed verbatim from the captured Zendesk home
# (support-home/desktop): five categories and six promoted articles.
SUPPORT_CATEGORIES = (
    (
        "faq-frequently-asked-questions",
        "FAQ - Frequently Asked Questions",
        "Answers to the most Frequently Asked Questions can be found here",
    ),
    (
        "setup-guides",
        "Setup Guides",
        "Looking for a guide to help you set up your IPVanish VPN on your "
        "devices? Let our SETUP guides get you started",
    ),
    (
        "billing-questions",
        "Billing Questions",
        "Do you have billing questions? Find answers to billing issues",
    ),
    (
        "troubleshooting",
        "Troubleshooting",
        "Have a problem with your IPVanish VPN? Look at our Troubleshooting "
        "Guides for solutions to common problems",
    ),
    (
        "about-ipvanish",
        "About IPVanish",
        "Have a question about IPVanish, our service, or VPN? Find answers here",
    ),
)
SUPPORT_ARTICLES = (
    (
        "38941412055707-System-extension-blocked-error-in-macOS-Ventura",
        "troubleshooting",
        "System extension blocked error in macOS Ventura",
    ),
    (
        "36842546417307-How-to-Claim-and-Activate-Your-Free-eSIM-with-IPVanish",
        "faq-frequently-asked-questions",
        "How to Claim and Activate Your Free eSIM with IPVanish",
    ),
    (
        "29403068072475-Nothing-happens-when-I-click-the-IPVanish-icon-IPVanish-"
        "won-t-open-in-macOS-Sequoia",
        "troubleshooting",
        "Nothing happens when I click the IPVanish icon - IPVanish won’t "
        "open in macOS Sequoia",
    ),
    (
        "29399044908827-System-extension-blocked-error-in-macOS-Sequoia",
        "troubleshooting",
        "System extension blocked error in macOS Sequoia",
    ),
    (
        "4603207666203-Why-can-t-I-connect-to-any-location-on-the-Windows-app",
        "troubleshooting",
        "Why can’t I connect to any location on the Windows app?",
    ),
    (
        "4534840473499-How-do-I-set-up-IPVanish-for-Windows",
        "setup-guides",
        "How do I set up IPVanish for Windows?",
    ),
)


def _seed_business(connection: sqlite3.Connection) -> None:
    """Delete and rewrite only this site's own tables, deterministically."""

    for table in BUSINESS_TABLES:
        connection.execute(f"DELETE FROM {table}")
    epoch = _seed_epoch()
    for index, account in enumerate(SEED_ACCOUNTS):
        connection.execute(
            "INSERT INTO ipvanish_accounts"
            "(subject_id,email,display_name,created_on) VALUES (?,?,?,?)",
            (
                account["subject_id"],
                account["email"],
                account["display_name"],
                _day(epoch, -420 - index),
            ),
        )
    connection.execute(
        "INSERT INTO ipvanish_billing_contacts"
        "(subject_id,full_name,email,country,postal_code) VALUES (?,?,?,?,?)",
        (
            PRIMARY_SUBJECT,
            "Avery Sandoval",
            SEED_ACCOUNTS[0]["email"],
            "US",
            "78701",
        ),
    )
    connection.execute(
        "INSERT INTO ipvanish_billing_contacts"
        "(subject_id,full_name,email,country,postal_code) VALUES (?,?,?,?,?)",
        (
            ISOLATION_SUBJECT,
            "Morgan Reyes",
            SEED_ACCOUNTS[1]["email"],
            "CA",
            "M5V 2T6",
        ),
    )
    fixtures = (
        # the active annual subscription
        (
            "sub_primary_annual",
            PRIMARY_SUBJECT,
            "essential-annual",
            "active",
            _day(epoch, -300),
            _day(epoch, 65),
            BY_ID["essential-annual"].renewal_minor,
            None,
            None,
            0,
        ),
        # a canceled subscription, present so reactivation has something real
        (
            "sub_primary_monthly",
            PRIMARY_SUBJECT,
            "essential-monthly",
            "canceled",
            _day(epoch, -400),
            _day(epoch, -370),
            BY_ID["essential-monthly"].renewal_minor,
            None,
            _day(epoch, -372),
            1,
        ),
        # the isolation actor's own subscription
        (
            "sub_isolation_biennial",
            ISOLATION_SUBJECT,
            "advanced-biennial",
            "active",
            _day(epoch, -120),
            _day(epoch, 245),
            BY_ID["advanced-biennial"].renewal_minor,
            None,
            None,
            0,
        ),
    )
    connection.executemany(
        "INSERT INTO ipvanish_subscriptions(subscription_id,subject_id,plan_id,"
        "status,started_on,renews_on,renewal_price_minor,paused_on,canceled_on,"
        "position) VALUES (?,?,?,?,?,?,?,?,?,?)",
        fixtures,
    )
    orders = (
        (
            "ord_primary_initial",
            PRIMARY_SUBJECT,
            "sub_primary_annual",
            "essential-annual",
            "initial",
            4668,
            607,
            5275,
            _day(epoch, -300),
            0,
        ),
        (
            "ord_primary_renewal",
            PRIMARY_SUBJECT,
            "sub_primary_annual",
            "essential-annual",
            "renewal",
            9999,
            1300,
            11299,
            _day(epoch, -65),
            1,
        ),
        (
            "ord_primary_monthly",
            PRIMARY_SUBJECT,
            "sub_primary_monthly",
            "essential-monthly",
            "initial",
            1499,
            195,
            1694,
            _day(epoch, -400),
            2,
        ),
        (
            "ord_isolation_initial",
            ISOLATION_SUBJECT,
            "sub_isolation_biennial",
            "advanced-biennial",
            "initial",
            8616,
            1120,
            9736,
            _day(epoch, -120),
            0,
        ),
    )
    connection.executemany(
        "INSERT INTO ipvanish_orders(order_id,subject_id,subscription_id,plan_id,"
        "kind,amount_minor,tax_minor,total_minor,currency,status,scenario_id,"
        "idempotency_key,charged_on,position)"
        " VALUES (?,?,?,?,?,?,?,?,'USD','paid','seed',NULL,?,?)",
        orders,
    )
    for position, (slug, section, title) in enumerate(SUPPORT_ARTICLES):
        connection.execute(
            "INSERT INTO ipvanish_support_articles"
            "(slug,section,title,body,position) VALUES (?,?,?,?,?)",
            (
                slug,
                section,
                title,
                "This clone serves the captured support index. Article bodies "
                "were not part of the frozen capture, so none is reproduced "
                "here.",
                position,
            ),
        )


# --------------------------------------------------------------------------
# lazy, thread-safe opening
# --------------------------------------------------------------------------

_lock = threading.Lock()
_services: tuple[Any, Any] | None = None


def services() -> tuple[Any, Any]:
    global _services
    with _lock:
        if _services is None:
            backend, auth = open_site_services()
            with backend.lifecycle.connection(transaction=True) as connection:
                connection.executescript(SCHEMA)
            for account in SEED_ACCOUNTS:
                auth.seed_account(**account)
            with backend.lifecycle.connection(transaction=True) as connection:
                empty = (
                    int(
                        connection.execute(
                            "SELECT COUNT(*) FROM ipvanish_accounts"
                        ).fetchone()[0]
                    )
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
    """Deterministic full reset through the seam, in one transaction."""

    _, auth_store = services()
    auth_store.reset_site_state(
        site_reset=_seed_business,
        seed_accounts=[dict(account) for account in SEED_ACCOUNTS],
    )


def business_state_dump() -> str:
    """A canonical dump of every business table, for reset-stability tests."""

    site_backend, _ = services()
    rows: dict[str, list[list[Any]]] = {}
    with site_backend.lifecycle.connection() as connection:
        for table in sorted(BUSINESS_TABLES):
            cursor = connection.execute(f"SELECT * FROM {table} ORDER BY 1")
            rows[table] = [list(row) for row in cursor.fetchall()]
    return json.dumps(rows, sort_keys=True, separators=(",", ":"), default=str)


# --------------------------------------------------------------------------
# reads
# --------------------------------------------------------------------------


def account_by_subject(subject_id: str) -> dict[str, Any] | None:
    site_backend, _ = services()
    with site_backend.lifecycle.connection() as connection:
        row = connection.execute(
            "SELECT * FROM ipvanish_accounts WHERE subject_id=?", (subject_id,)
        ).fetchone()
        return dict(row) if row is not None else None


def subscriptions_for(subject_id: str) -> list[dict[str, Any]]:
    site_backend, _ = services()
    with site_backend.lifecycle.connection() as connection:
        cursor = connection.execute(
            "SELECT * FROM ipvanish_subscriptions WHERE subject_id=? "
            "ORDER BY position, subscription_id",
            (subject_id,),
        )
        return [dict(row) for row in cursor.fetchall()]


def subscription(subject_id: str, subscription_id: str) -> dict[str, Any] | None:
    """Scoped by owner: another actor's id resolves to nothing, not to a row."""

    site_backend, _ = services()
    with site_backend.lifecycle.connection() as connection:
        row = connection.execute(
            "SELECT * FROM ipvanish_subscriptions "
            "WHERE subject_id=? AND subscription_id=?",
            (subject_id, subscription_id),
        ).fetchone()
        return dict(row) if row is not None else None


def orders_for(subject_id: str) -> list[dict[str, Any]]:
    site_backend, _ = services()
    with site_backend.lifecycle.connection() as connection:
        cursor = connection.execute(
            "SELECT * FROM ipvanish_orders WHERE subject_id=? "
            "ORDER BY charged_on DESC, position DESC, order_id DESC",
            (subject_id,),
        )
        return [dict(row) for row in cursor.fetchall()]


def billing_contact(subject_id: str) -> dict[str, Any] | None:
    site_backend, _ = services()
    with site_backend.lifecycle.connection() as connection:
        row = connection.execute(
            "SELECT * FROM ipvanish_billing_contacts WHERE subject_id=?",
            (subject_id,),
        ).fetchone()
        return dict(row) if row is not None else None


def support_articles(query: str | None = None) -> list[dict[str, Any]]:
    site_backend, _ = services()
    with site_backend.lifecycle.connection() as connection:
        if query:
            cursor = connection.execute(
                "SELECT * FROM ipvanish_support_articles "
                "WHERE lower(title) LIKE ? ORDER BY position",
                (f"%{query.casefold()}%",),
            )
        else:
            cursor = connection.execute(
                "SELECT * FROM ipvanish_support_articles ORDER BY position"
            )
        return [dict(row) for row in cursor.fetchall()]


# --------------------------------------------------------------------------
# writes
# --------------------------------------------------------------------------

IDEMPOTENCY_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")


def _fingerprint(*parts: str) -> str:
    return hashlib.sha256(("ipvanish|" + "|".join(parts)).encode()).hexdigest()


def ensure_checkout_account(
    subject_id: str, *, email: str, display_name: str
) -> None:
    """Create the funnel-scoped account row if the checkout has not seen it.

    The source creates credentials inside the checkout bundle and mails them;
    this clone records the account and its subscription without ever setting a
    password here, and the confirmation page says so.
    """

    site_backend, _ = services()
    epoch = _seed_epoch()
    with site_backend.lifecycle.connection(transaction=True) as connection:
        connection.execute(
            "INSERT INTO ipvanish_accounts(subject_id,email,display_name,"
            "created_on) VALUES (?,?,?,?) ON CONFLICT(subject_id) DO NOTHING",
            (subject_id, email, display_name or email, _day(epoch, 0)),
        )


def record_receipt(session_digest: str, order_id: str) -> None:
    """Bind one completed order to the session that placed it."""

    site_backend, _ = services()
    with site_backend.lifecycle.connection(transaction=True) as connection:
        connection.execute(
            "INSERT INTO ipvanish_checkout_receipts(session_digest,order_id)"
            " VALUES (?,?) ON CONFLICT(session_digest) DO UPDATE SET"
            " order_id=excluded.order_id",
            (session_digest, order_id),
        )


def receipt_for(session_digest: str) -> dict[str, Any] | None:
    site_backend, _ = services()
    with site_backend.lifecycle.connection() as connection:
        row = connection.execute(
            "SELECT o.* FROM ipvanish_checkout_receipts r "
            "JOIN ipvanish_orders o ON o.order_id = r.order_id "
            "WHERE r.session_digest=?",
            (session_digest,),
        ).fetchone()
        return dict(row) if row is not None else None


def update_billing_contact(
    subject_id: str,
    *,
    full_name: str,
    email: str,
    country: str,
    postal_code: str,
) -> None:
    site_backend, _ = services()
    with site_backend.lifecycle.connection(transaction=True) as connection:
        connection.execute(
            "INSERT INTO ipvanish_billing_contacts"
            "(subject_id,full_name,email,country,postal_code) VALUES (?,?,?,?,?)"
            " ON CONFLICT(subject_id) DO UPDATE SET full_name=excluded.full_name,"
            " email=excluded.email, country=excluded.country,"
            " postal_code=excluded.postal_code",
            (subject_id, full_name, email, country, postal_code),
        )


def set_subscription_state(
    subject_id: str,
    subscription_id: str,
    *,
    status: str,
) -> dict[str, Any] | None:
    """Pause, resume, cancel or reactivate one subscription the actor owns."""

    if status not in {"active", "paused", "canceled"}:
        raise ValueError("unknown subscription status")
    site_backend, _ = services()
    epoch = _seed_epoch()
    with site_backend.lifecycle.connection(transaction=True) as connection:
        row = connection.execute(
            "SELECT * FROM ipvanish_subscriptions "
            "WHERE subject_id=? AND subscription_id=?",
            (subject_id, subscription_id),
        ).fetchone()
        if row is None:
            return None
        paused_on = _day(epoch, 0) if status == "paused" else None
        canceled_on = _day(epoch, 0) if status == "canceled" else None
        renews_on = row["renews_on"]
        if status == "active" and row["status"] == "canceled":
            plan = BY_ID.get(str(row["plan_id"]))
            renews_on = _day(epoch, 30 * (plan.term_months if plan else 1))
        connection.execute(
            "UPDATE ipvanish_subscriptions SET status=?, paused_on=?, "
            "canceled_on=?, renews_on=? WHERE subscription_id=?",
            (status, paused_on, canceled_on, renews_on, subscription_id),
        )
        updated = connection.execute(
            "SELECT * FROM ipvanish_subscriptions WHERE subscription_id=?",
            (subscription_id,),
        ).fetchone()
        return dict(updated)


def purchase(
    *,
    subject_id: str,
    plan: Plan,
    scenario_id: str,
    idempotency_key: str,
    kind: str = "initial",
    subscription_id: str | None = None,
) -> dict[str, Any]:
    """Consume one sandbox approval and write subscription + order together.

    A declined scenario writes neither.  A retryable scenario writes neither and
    stays retryable.  A duplicate submission returns the first result: the order
    table carries ``UNIQUE (subject_id, idempotency_key)`` and the seam's own
    attempt ledger is keyed the same way.
    """

    if not IDEMPOTENCY_RE.fullmatch(idempotency_key or ""):
        raise PaymentError("idempotency key is invalid")
    site_backend, _ = services()
    epoch = _seed_epoch()
    fingerprint = _fingerprint(subject_id, plan.plan_id, kind)
    amount_minor = plan.total_minor
    with site_backend.lifecycle.connection(transaction=True) as connection:
        existing = connection.execute(
            "SELECT * FROM ipvanish_orders WHERE subject_id=? AND idempotency_key=?",
            (subject_id, idempotency_key),
        ).fetchone()
        if existing is not None:
            return {
                "outcome": "approved",
                "duplicate": True,
                "order": dict(existing),
                "subscription_id": existing["subscription_id"],
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
        target = subscription_id or f"sub_{idempotency_key[:24]}"
        renews_on = _day(epoch, 30 * plan.term_months)
        connection.execute(
            "INSERT INTO ipvanish_subscriptions(subscription_id,subject_id,"
            "plan_id,status,started_on,renews_on,renewal_price_minor,paused_on,"
            "canceled_on,position) VALUES (?,?,?,'active',?,?,?,NULL,NULL,?)"
            " ON CONFLICT(subscription_id) DO UPDATE SET plan_id=excluded.plan_id,"
            " status='active', renews_on=excluded.renews_on,"
            " renewal_price_minor=excluded.renewal_price_minor,"
            " paused_on=NULL, canceled_on=NULL",
            (
                target,
                subject_id,
                plan.plan_id,
                _day(epoch, 0),
                renews_on,
                plan.renewal_minor,
                2,
            ),
        )
        connection.execute(
            "INSERT INTO ipvanish_orders(order_id,subject_id,subscription_id,"
            "plan_id,kind,amount_minor,tax_minor,total_minor,currency,status,"
            "scenario_id,idempotency_key,charged_on,position)"
            " VALUES (?,?,?,?,?,?,?,?,?,'paid',?,?,?,?)",
            (
                f"ord_{idempotency_key[:24]}",
                subject_id,
                target,
                plan.plan_id,
                kind,
                plan.charge_minor,
                plan.tax_minor,
                plan.total_minor,
                CURRENCY,
                scenario_id,
                idempotency_key,
                _day(epoch, 0),
                3,
            ),
        )
        order = connection.execute(
            "SELECT * FROM ipvanish_orders WHERE subject_id=? AND idempotency_key=?",
            (subject_id, idempotency_key),
        ).fetchone()
        return {
            "outcome": "approved",
            "duplicate": False,
            "order": dict(order),
            "subscription_id": target,
        }
