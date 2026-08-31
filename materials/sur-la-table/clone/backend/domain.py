"""Site-owned cooking class data and booking transitions."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from typing import Any


SCHEMA = """
CREATE TABLE IF NOT EXISTS slt_schema_migrations (
    version TEXT PRIMARY KEY,
    applied_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS slt_stores (
    store_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    city TEXT NOT NULL,
    address TEXT NOT NULL,
    distance_miles REAL NOT NULL,
    has_classes INTEGER NOT NULL CHECK(has_classes IN (0,1))
);
CREATE TABLE IF NOT EXISTS slt_classes (
    class_id TEXT PRIMARY KEY,
    slug TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    cuisine TEXT NOT NULL,
    class_type TEXT NOT NULL,
    description TEXT NOT NULL,
    price_cents INTEGER NOT NULL,
    review_count INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS slt_sessions (
    session_id TEXT PRIMARY KEY,
    class_id TEXT NOT NULL REFERENCES slt_classes(class_id),
    store_id TEXT NOT NULL REFERENCES slt_stores(store_id),
    starts_at TEXT NOT NULL,
    capacity INTEGER NOT NULL,
    booked INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL CHECK(status IN ('available','limited','sold-out'))
);
CREATE TABLE IF NOT EXISTS slt_bookings (
    booking_id TEXT PRIMARY KEY,
    owner_subject TEXT NOT NULL,
    session_id TEXT NOT NULL REFERENCES slt_sessions(session_id),
    party_size INTEGER NOT NULL CHECK(party_size > 0),
    attendee_name TEXT NOT NULL,
    attendee_email TEXT NOT NULL,
    subtotal_cents INTEGER NOT NULL,
    total_cents INTEGER NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('confirmed','rescheduled','cancelled')),
    payment_flow_id TEXT NOT NULL UNIQUE,
    idempotency_key TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(owner_subject,idempotency_key)
);
CREATE INDEX IF NOT EXISTS slt_bookings_owner_idx
    ON slt_bookings(owner_subject,created_at DESC);
"""


STORES = [
    ("berkeley", "Berkeley", "Berkeley", "1806 Fourth Street, Berkeley, CA 94710", 9.2, 1),
    ("palo-alto", "Palo Alto", "Palo Alto", "855 El Camino Real, Palo Alto, CA 94301", 27.3, 1),
    ("san-jose", "Santana Row", "San Jose", "377 Santana Row, San Jose, CA 95128", 47.1, 1),
]

CLASSES = [
    (
        "fresh-pasta-two-ways",
        "fresh-pasta-workshop-kitchenaid",
        "Fresh Pasta Two Ways",
        "Italian",
        "In-Store Cooking Class",
        "Make fresh pasta dough, shape two pasta styles, and pair them with seasonal sauces. This is a hands-on class taught in our kitchen.",
        9900,
        2,
    ),
    (
        "autumn-ravioli",
        "autumn-ravioli-workshop",
        "Autumn Ravioli Workshop",
        "Italian",
        "In-Store Cooking Class",
        "Practice filled dough techniques and make an autumn ravioli with a simple sauce.",
        10900,
        0,
    ),
    (
        "croissant-basics",
        "croissant-basics",
        "Croissant Basics",
        "French",
        "In-Store Cooking Class",
        "Learn lamination, shaping, proofing, and baking in a hands-on class.",
        8900,
        5,
    ),
]

SESSIONS = [
    ("pasta-pa-20260926-1300", "fresh-pasta-two-ways", "palo-alto", "2026-09-26T13:00:00-07:00", 16, 10, "available"),
    ("pasta-pa-20260927-1500", "fresh-pasta-two-ways", "palo-alto", "2026-09-27T15:00:00-07:00", 16, 14, "limited"),
    ("pasta-pa-20261003-1300", "fresh-pasta-two-ways", "palo-alto", "2026-10-03T13:00:00-07:00", 16, 16, "sold-out"),
    ("ravioli-berk-20260927-1400", "autumn-ravioli", "berkeley", "2026-09-27T14:00:00-07:00", 14, 5, "available"),
    ("croissant-berk-20260926-1000", "croissant-basics", "berkeley", "2026-09-26T10:00:00-07:00", 14, 7, "available"),
]


def migrate(connection: sqlite3.Connection) -> None:
    # Lifecycle owns the surrounding transaction, so hooks must not use
    # executescript(), which commits implicitly in sqlite3.
    for statement in SCHEMA.split(";"):
        sql = statement.strip()
        if sql:
            connection.execute(sql)
    connection.execute(
        "INSERT OR IGNORE INTO slt_schema_migrations(version,applied_at) VALUES (?,?)",
        ("001-class-booking", "2026-08-30T00:00:00Z"),
    )


def seed(connection: sqlite3.Connection) -> None:
    connection.executemany(
        "INSERT OR IGNORE INTO slt_stores VALUES (?,?,?,?,?,?)", STORES
    )
    connection.executemany(
        "INSERT OR IGNORE INTO slt_classes VALUES (?,?,?,?,?,?,?,?)", CLASSES
    )
    connection.executemany(
        "INSERT OR IGNORE INTO slt_sessions VALUES (?,?,?,?,?,?,?)", SESSIONS
    )


def _dicts(cursor: sqlite3.Cursor) -> list[dict[str, Any]]:
    return [dict(row) for row in cursor.fetchall()]


def list_stores(connection: sqlite3.Connection) -> list[dict[str, Any]]:
    return _dicts(
        connection.execute(
            """
            SELECT st.*,
                   EXISTS(
                       SELECT 1
                       FROM slt_sessions s
                       JOIN slt_classes c USING(class_id)
                       WHERE s.store_id=st.store_id
                         AND c.class_id='fresh-pasta-two-ways'
                         AND s.status!='sold-out'
                         AND s.booked<s.capacity
                   ) AS qualifying_pasta_session
            FROM slt_stores st
            ORDER BY st.distance_miles
            """
        )
    )


def list_sessions(
    connection: sqlite3.Connection,
    *,
    query: str = "",
    store: str = "",
    cuisine: str = "",
    availability: str = "",
    sort: str = "date",
) -> list[dict[str, Any]]:
    sql = """
        SELECT s.*,c.slug,c.title,c.cuisine,c.class_type,c.description,
               c.price_cents,c.review_count,st.name AS store_name,st.city,
               st.address,st.distance_miles,(s.capacity-s.booked) AS seats_left
        FROM slt_sessions s JOIN slt_classes c USING(class_id)
        JOIN slt_stores st USING(store_id) WHERE 1=1
    """
    args: list[Any] = []
    if query:
        sql += " AND (lower(c.title) LIKE ? OR lower(c.description) LIKE ?)"
        token = f"%{query.casefold()}%"
        args.extend([token, token])
    if store:
        sql += " AND s.store_id=?"
        args.append(store)
    if cuisine:
        sql += " AND lower(c.cuisine)=?"
        args.append(cuisine.casefold())
    if availability == "available":
        sql += " AND s.status!='sold-out' AND s.booked<s.capacity"
    orders = {
        "date": "s.starts_at ASC",
        "price-low": "c.price_cents ASC,s.starts_at ASC",
        "distance": "st.distance_miles ASC,s.starts_at ASC",
        "availability": "seats_left DESC,s.starts_at ASC",
    }
    sql += " ORDER BY " + orders.get(sort, orders["date"])
    return _dicts(connection.execute(sql, args))


def session_detail(connection: sqlite3.Connection, session_id: str) -> dict[str, Any] | None:
    rows = list_sessions(connection)
    return next((row for row in rows if row["session_id"] == session_id), None)


def booking_fingerprint(session_id: str, party_size: int, owner: str) -> str:
    return hashlib.sha256(
        json.dumps([session_id, party_size, owner], separators=(",", ":")).encode()
    ).hexdigest()


def create_booking(
    connection: sqlite3.Connection,
    *,
    owner: str,
    session_id: str,
    party_size: int,
    attendee_name: str,
    attendee_email: str,
    payment_flow_id: str,
    idempotency_key: str,
) -> dict[str, Any]:
    existing = connection.execute(
        "SELECT * FROM slt_bookings WHERE owner_subject=? AND idempotency_key=?",
        (owner, idempotency_key),
    ).fetchone()
    if existing:
        return dict(existing)
    detail = session_detail(connection, session_id)
    if detail is None:
        raise ValueError("Selected class session is unavailable.")
    if detail["status"] == "sold-out" or detail["seats_left"] < party_size:
        raise ValueError("Not enough seats remain for this class.")
    total = int(detail["price_cents"]) * party_size
    now = datetime.now(timezone.utc).isoformat()
    booking_id = "SLT-" + hashlib.sha256(
        f"{owner}:{idempotency_key}".encode()
    ).hexdigest()[:10].upper()
    connection.execute(
        """INSERT INTO slt_bookings(
           booking_id,owner_subject,session_id,party_size,attendee_name,
           attendee_email,subtotal_cents,total_cents,status,payment_flow_id,
           idempotency_key,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (booking_id,owner,session_id,party_size,attendee_name,attendee_email,
         total,total,"confirmed",payment_flow_id,idempotency_key,now,now),
    )
    connection.execute(
        "UPDATE slt_sessions SET booked=booked+? WHERE session_id=?",
        (party_size, session_id),
    )
    return dict(connection.execute(
        "SELECT * FROM slt_bookings WHERE booking_id=?", (booking_id,)
    ).fetchone())


def booking_detail(connection: sqlite3.Connection, booking_id: str, owner: str) -> dict[str, Any] | None:
    row = connection.execute(
        """SELECT b.*,s.starts_at,c.title,c.price_cents,st.name AS store_name,
           st.address FROM slt_bookings b JOIN slt_sessions s USING(session_id)
           JOIN slt_classes c USING(class_id) JOIN slt_stores st USING(store_id)
           WHERE b.booking_id=? AND b.owner_subject=?""",
        (booking_id, owner),
    ).fetchone()
    return dict(row) if row else None


def booking_history(connection: sqlite3.Connection, owner: str) -> list[dict[str, Any]]:
    return _dicts(connection.execute(
        """SELECT b.*,s.starts_at,c.title,st.name AS store_name,st.address
           FROM slt_bookings b JOIN slt_sessions s USING(session_id)
           JOIN slt_classes c USING(class_id) JOIN slt_stores st USING(store_id)
           WHERE b.owner_subject=? ORDER BY b.created_at DESC""", (owner,)
    ))


def update_booking(
    connection: sqlite3.Connection,
    *,
    booking_id: str,
    owner: str,
    action: str,
    session_id: str | None = None,
) -> dict[str, Any]:
    current = booking_detail(connection, booking_id, owner)
    if current is None:
        raise PermissionError("Booking is unavailable or belongs to another account.")
    if current["status"] == "cancelled":
        raise ValueError("Cancelled bookings cannot be changed.")
    starts = datetime.fromisoformat(current["starts_at"])
    if (starts - datetime.now(starts.tzinfo)).total_seconds() < 48 * 3600:
        raise ValueError("Changes close 48 hours before class start.")
    now = datetime.now(timezone.utc).isoformat()
    if action == "cancel":
        connection.execute(
            "UPDATE slt_bookings SET status='cancelled',updated_at=? WHERE booking_id=?",
            (now, booking_id),
        )
        connection.execute(
            "UPDATE slt_sessions SET booked=booked-? WHERE session_id=?",
            (current["party_size"], current["session_id"]),
        )
    elif action == "reschedule" and session_id:
        target = session_detail(connection, session_id)
        if target is None or target["seats_left"] < current["party_size"] or target["status"] == "sold-out":
            raise ValueError("Selected replacement session is unavailable.")
        connection.execute(
            "UPDATE slt_sessions SET booked=booked-? WHERE session_id=?",
            (current["party_size"], current["session_id"]),
        )
        connection.execute(
            "UPDATE slt_sessions SET booked=booked+? WHERE session_id=?",
            (current["party_size"], session_id),
        )
        connection.execute(
            "UPDATE slt_bookings SET session_id=?,status='rescheduled',updated_at=? WHERE booking_id=?",
            (session_id, now, booking_id),
        )
    else:
        raise ValueError("Booking action is invalid.")
    return booking_detail(connection, booking_id, owner) or {}
