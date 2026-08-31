"""Topgolf venue, identity, favorite, and reservation domain model."""

from __future__ import annotations

import hashlib
import json
import re
import secrets
import sqlite3
from datetime import datetime, timezone
from typing import Any


SCHEMA = """
CREATE TABLE IF NOT EXISTS tg_schema_migrations (
    version TEXT PRIMARY KEY,
    applied_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS tg_venues (
    venue_id TEXT PRIMARY KEY,
    source_record_id TEXT NOT NULL UNIQUE,
    source_site_id TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    city TEXT NOT NULL,
    region TEXT NOT NULL,
    country TEXT NOT NULL,
    address TEXT NOT NULL,
    distance_km REAL NOT NULL,
    description TEXT NOT NULL,
    pricing_note TEXT NOT NULL,
    hours_note TEXT NOT NULL,
    policy_note TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS tg_slots (
    slot_id TEXT PRIMARY KEY,
    venue_id TEXT NOT NULL REFERENCES tg_venues(venue_id),
    starts_at TEXT NOT NULL,
    duration_minutes INTEGER NOT NULL,
    party_limit INTEGER NOT NULL,
    price_cents INTEGER NOT NULL,
    capacity_bays INTEGER NOT NULL,
    reserved_bays INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL CHECK(status IN ('available','unavailable')),
    recommended INTEGER NOT NULL CHECK(recommended IN (0,1)),
    UNIQUE(venue_id,starts_at,duration_minutes)
);
CREATE TABLE IF NOT EXISTS tg_players (
    subject_id TEXT PRIMARY KEY,
    phone_normalized TEXT NOT NULL UNIQUE,
    phone_last4 TEXT NOT NULL,
    display_name TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS tg_phone_challenges (
    challenge_id TEXT PRIMARY KEY,
    session_digest TEXT NOT NULL UNIQUE,
    phone_normalized TEXT NOT NULL,
    code_salt BLOB NOT NULL,
    code_hash BLOB NOT NULL,
    expires_at INTEGER NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0 CHECK(attempts BETWEEN 0 AND 5),
    verified_at INTEGER,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS tg_phone_challenge_phone_idx
    ON tg_phone_challenges(phone_normalized,created_at DESC);
CREATE TABLE IF NOT EXISTS tg_favorites (
    owner_key TEXT NOT NULL,
    venue_id TEXT NOT NULL REFERENCES tg_venues(venue_id),
    created_at TEXT NOT NULL,
    PRIMARY KEY(owner_key,venue_id)
);
CREATE TABLE IF NOT EXISTS tg_reservations (
    reservation_id TEXT PRIMARY KEY,
    owner_key TEXT NOT NULL,
    slot_id TEXT NOT NULL REFERENCES tg_slots(slot_id),
    party_size INTEGER NOT NULL CHECK(party_size BETWEEN 1 AND 6),
    bay_count INTEGER NOT NULL CHECK(bay_count=1),
    first_name TEXT NOT NULL,
    last_name TEXT NOT NULL,
    phone TEXT NOT NULL,
    email TEXT NOT NULL,
    accessibility_request TEXT NOT NULL,
    special_request TEXT NOT NULL,
    subtotal_cents INTEGER NOT NULL,
    total_cents INTEGER NOT NULL,
    currency TEXT NOT NULL CHECK(currency='USD'),
    status TEXT NOT NULL CHECK(status IN ('confirmed','rescheduled','cancelled')),
    refund_status TEXT NOT NULL CHECK(refund_status IN ('none','not-required','refunded')),
    payment_flow_id TEXT NOT NULL UNIQUE,
    idempotency_key TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(owner_key,idempotency_key)
);
CREATE INDEX IF NOT EXISTS tg_reservations_owner_idx
    ON tg_reservations(owner_key,created_at DESC);
CREATE TABLE IF NOT EXISTS tg_reservation_events (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    reservation_id TEXT NOT NULL REFERENCES tg_reservations(reservation_id),
    event_type TEXT NOT NULL,
    snapshot_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


VENUES = [
    (
        "cleveland", "65651", "63", "Topgolf Cleveland", "Independence",
        "Ohio", "United States", "5820 Rockside Woods Blvd N, Independence, OH 44131",
        311.3,
        "A sports and entertainment venue with climate-controlled hitting bays, games, food, and drinks.",
        "$44 per hour per bay on Saturday from noon to 4 PM. Prices exclude sales tax.",
        "Hours vary by day and holiday. Review the selected date before visiting.",
        "Up to six players may share one bay. A one-time new-player membership fee may apply.",
    ),
    (
        "avon", "avon-observed", "avon", "Topgolf Avon", "Avon", "Ohio",
        "United States", "Near Detroit Road, Avon, OH", 324.5,
        "An observed Topgolf venue west of Cleveland.",
        "Check venue pricing for the selected date.", "Hours vary.",
        "Availability and policies vary by venue.",
    ),
    (
        "detroit-auburn-hills", "detroit-observed", "auburn-hills",
        "Topgolf Detroit - Auburn Hills", "Auburn Hills", "Michigan",
        "United States", "500 Great Lakes Crossing Dr, Auburn Hills, MI 48326",
        333.9, "An observed Topgolf venue in Auburn Hills.",
        "Check venue pricing for the selected date.", "Hours vary.",
        "Availability and policies vary by venue.",
    ),
]


SLOTS = [
    ("cle-20260905-1400-120", "cleveland", "2026-09-05T14:00:00-04:00", 120, 6, 8800, 3, 0, "available", 1),
    ("cle-20260905-1400-90", "cleveland", "2026-09-05T14:00:00-04:00", 90, 6, 6600, 3, 0, "available", 0),
    ("cle-20260905-1400-60", "cleveland", "2026-09-05T14:00:00-04:00", 60, 6, 4400, 3, 0, "unavailable", 0),
    ("cle-20260905-1500-120", "cleveland", "2026-09-05T15:00:00-04:00", 120, 6, 8800, 2, 0, "available", 1),
    ("cle-20260912-1400-120", "cleveland", "2026-09-12T14:00:00-04:00", 120, 6, 8800, 3, 0, "available", 1),
]


def migrate(connection: sqlite3.Connection) -> None:
    for statement in SCHEMA.split(";"):
        sql = statement.strip()
        if sql:
            connection.execute(sql)
    connection.execute(
        "INSERT OR IGNORE INTO tg_schema_migrations(version,applied_at) VALUES (?,?)",
        ("001-topgolf-reservations", "2026-08-30T00:00:00Z"),
    )


def seed(connection: sqlite3.Connection) -> None:
    connection.executemany(
        "INSERT OR IGNORE INTO tg_venues VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", VENUES
    )
    connection.executemany(
        "INSERT OR IGNORE INTO tg_slots VALUES (?,?,?,?,?,?,?,?,?,?)", SLOTS
    )


def reset(connection: sqlite3.Connection) -> None:
    for table in (
        "tg_reservation_events", "tg_reservations", "tg_favorites",
        "tg_phone_challenges", "tg_players", "tg_slots", "tg_venues",
    ):
        connection.execute(f"DELETE FROM {table}")
    seed(connection)


def rows(cursor: sqlite3.Cursor) -> list[dict[str, Any]]:
    return [dict(row) for row in cursor.fetchall()]


def list_venues(connection: sqlite3.Connection, query: str = "") -> list[dict[str, Any]]:
    sql = "SELECT * FROM tg_venues"
    args: list[str] = []
    if query.strip() and query.strip().casefold() not in {"toronto", "downtown toronto", "toronto, on"}:
        token = f"%{query.strip().casefold()}%"
        sql += " WHERE lower(name) LIKE ? OR lower(city) LIKE ? OR lower(region) LIKE ?"
        args = [token, token, token]
    sql += " ORDER BY distance_km,name"
    return rows(connection.execute(sql, args))


def venue_detail(connection: sqlite3.Connection, venue_id: str) -> dict[str, Any] | None:
    row = connection.execute("SELECT * FROM tg_venues WHERE venue_id=?", (venue_id,)).fetchone()
    return dict(row) if row else None


def list_slots(connection: sqlite3.Connection, venue_id: str, date: str) -> list[dict[str, Any]]:
    return rows(connection.execute(
        "SELECT *,CASE WHEN status='available' AND reserved_bays<capacity_bays THEN 1 ELSE 0 END AS available "
        "FROM tg_slots WHERE venue_id=? AND substr(starts_at,1,10)=? ORDER BY starts_at,duration_minutes DESC",
        (venue_id, date),
    ))


def slot_detail(connection: sqlite3.Connection, slot_id: str) -> dict[str, Any] | None:
    row = connection.execute(
        "SELECT s.*,v.name AS venue_name,v.address,v.city,v.region,v.distance_km,v.policy_note "
        "FROM tg_slots s JOIN tg_venues v USING(venue_id) WHERE s.slot_id=?",
        (slot_id,),
    ).fetchone()
    return dict(row) if row else None


def normalize_phone(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError("Mobile number is required.")
    digits = re.sub(r"\D", "", value)
    if len(digits) == 10:
        digits = "1" + digits
    if not 11 <= len(digits) <= 15:
        raise ValueError("Enter a valid mobile number with country code.")
    return "+" + digits


def hash_code(code: str, salt: bytes | None = None) -> tuple[bytes, bytes]:
    actual_salt = salt or secrets.token_bytes(16)
    digest = hashlib.scrypt(code.encode(), salt=actual_salt, n=2**14, r=8, p=1, dklen=64)
    return actual_salt, digest


def player_subject(phone: str) -> str:
    return "topgolf-player-" + hashlib.sha256(phone.encode()).hexdigest()[:24]


def owner_key(session: dict[str, Any] | None, session_digest: str) -> str:
    if session and session.get("authenticated"):
        return "account:" + str(session["account"]["subject_id"])
    return "session:" + session_digest


def booking_fingerprint(slot_id: str, party_size: int, owner: str) -> str:
    value = json.dumps([slot_id, party_size, 1, owner], separators=(",", ":"))
    return hashlib.sha256(value.encode()).hexdigest()


def quote(connection: sqlite3.Connection, slot_id: str, party_size: int) -> dict[str, Any]:
    detail = slot_detail(connection, slot_id)
    if detail is None:
        raise ValueError("Selected session is unavailable.")
    if party_size < 1 or party_size > 6:
        raise ValueError("Players must be between 1 and 6 for one bay.")
    if detail["status"] != "available" or detail["reserved_bays"] >= detail["capacity_bays"]:
        raise ValueError("Selected session is unavailable.")
    amount = int(detail["price_cents"])
    return {
        **detail,
        "party_size": party_size,
        "bay_count": 1,
        "subtotal_cents": amount,
        "total_cents": amount,
        "currency": "USD",
        "tax_source_status": "unavailable-not-included",
        "membership_fee_source_status": "may-apply-unavailable-not-included",
    }


def create_reservation(
    connection: sqlite3.Connection,
    *,
    owner: str,
    slot_id: str,
    party_size: int,
    first_name: str,
    last_name: str,
    phone: str,
    email: str,
    accessibility_request: str,
    special_request: str,
    payment_flow_id: str,
    idempotency_key: str,
) -> dict[str, Any]:
    existing = connection.execute(
        "SELECT reservation_id FROM tg_reservations WHERE owner_key=? AND idempotency_key=?",
        (owner, idempotency_key),
    ).fetchone()
    if existing:
        return reservation_detail(connection, str(existing["reservation_id"]), owner) or {}
    current = quote(connection, slot_id, party_size)
    now = datetime.now(timezone.utc).isoformat()
    reservation_id = "TG-" + hashlib.sha256(f"{owner}:{idempotency_key}".encode()).hexdigest()[:10].upper()
    connection.execute(
        "INSERT INTO tg_reservations(reservation_id,owner_key,slot_id,party_size,bay_count,first_name,last_name,phone,email,accessibility_request,special_request,subtotal_cents,total_cents,currency,status,refund_status,payment_flow_id,idempotency_key,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (reservation_id, owner, slot_id, party_size, 1, first_name, last_name, phone, email,
         accessibility_request, special_request, current["subtotal_cents"], current["total_cents"],
         "USD", "confirmed", "none", payment_flow_id, idempotency_key, now, now),
    )
    connection.execute(
        "UPDATE tg_slots SET reserved_bays=reserved_bays+1 WHERE slot_id=?",
        (slot_id,),
    )
    _event(connection, reservation_id, "confirmed")
    return reservation_detail(connection, reservation_id, owner) or {}


def reservation_detail(connection: sqlite3.Connection, reservation_id: str, owner: str) -> dict[str, Any] | None:
    row = connection.execute(
        "SELECT r.*,s.starts_at,s.duration_minutes,s.price_cents,v.name AS venue_name,v.address,v.city,v.region "
        "FROM tg_reservations r JOIN tg_slots s USING(slot_id) JOIN tg_venues v USING(venue_id) "
        "WHERE r.reservation_id=? AND r.owner_key=?",
        (reservation_id, owner),
    ).fetchone()
    return dict(row) if row else None


def reservation_history(connection: sqlite3.Connection, owner: str) -> list[dict[str, Any]]:
    return rows(connection.execute(
        "SELECT r.*,s.starts_at,s.duration_minutes,v.name AS venue_name,v.address "
        "FROM tg_reservations r JOIN tg_slots s USING(slot_id) JOIN tg_venues v USING(venue_id) "
        "WHERE r.owner_key=? ORDER BY r.created_at DESC", (owner,),
    ))


def update_reservation(connection: sqlite3.Connection, reservation_id: str, owner: str, action: str, slot_id: str | None = None) -> dict[str, Any]:
    current = reservation_detail(connection, reservation_id, owner)
    if current is None:
        raise PermissionError("Reservation is unavailable or belongs to another account.")
    if current["status"] == "cancelled":
        raise ValueError("Cancelled reservations cannot be changed.")
    starts = datetime.fromisoformat(current["starts_at"])
    if (starts - datetime.now(starts.tzinfo)).total_seconds() < 2 * 3600:
        raise ValueError("Changes close two hours before the reservation.")
    now = datetime.now(timezone.utc).isoformat()
    if action == "cancel":
        connection.execute(
            "UPDATE tg_reservations SET status='cancelled',refund_status='refunded',updated_at=? WHERE reservation_id=?",
            (now, reservation_id),
        )
        connection.execute("UPDATE tg_slots SET reserved_bays=reserved_bays-1 WHERE slot_id=?", (current["slot_id"],))
        _event(connection, reservation_id, "cancelled-and-refunded")
    elif action == "reschedule" and slot_id:
        target = quote(connection, slot_id, int(current["party_size"]))
        if int(target["total_cents"]) != int(current["total_cents"]):
            raise ValueError("Replacement session must have the same local total.")
        connection.execute("UPDATE tg_slots SET reserved_bays=reserved_bays-1 WHERE slot_id=?", (current["slot_id"],))
        connection.execute("UPDATE tg_slots SET reserved_bays=reserved_bays+1 WHERE slot_id=?", (slot_id,))
        connection.execute(
            "UPDATE tg_reservations SET slot_id=?,status='rescheduled',updated_at=? WHERE reservation_id=?",
            (slot_id, now, reservation_id),
        )
        _event(connection, reservation_id, "rescheduled")
    else:
        raise ValueError("Reservation action is invalid.")
    return reservation_detail(connection, reservation_id, owner) or {}


def _event(connection: sqlite3.Connection, reservation_id: str, event_type: str) -> None:
    connection.execute(
        "INSERT INTO tg_reservation_events(reservation_id,event_type,snapshot_json,created_at) VALUES (?,?,?,?)",
        (reservation_id, event_type, json.dumps({"event": event_type}, separators=(",", ":")), datetime.now(timezone.utc).isoformat()),
    )
