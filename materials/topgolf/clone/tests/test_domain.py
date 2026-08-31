from __future__ import annotations

import sqlite3

import pytest

from backend import domain


@pytest.fixture()
def connection():
    value = sqlite3.connect(":memory:")
    value.row_factory = sqlite3.Row
    value.execute("PRAGMA foreign_keys=ON")
    domain.migrate(value)
    domain.seed(value)
    yield value
    value.close()


def make_reservation(connection):
    return domain.create_reservation(
        connection,
        owner="account:test-player",
        slot_id="cle-20260905-1400-120",
        party_size=4,
        first_name="Test",
        last_name="Player",
        phone="+14165550188",
        email="player@example.test",
        accessibility_request="",
        special_request="",
        payment_flow_id="payflow_domain_test_123",
        idempotency_key="domain-test",
    )


def test_quote_is_per_bay_not_per_player(connection):
    one = domain.quote(connection, "cle-20260905-1400-120", 1)
    four = domain.quote(connection, "cle-20260905-1400-120", 4)
    assert one["total_cents"] == four["total_cents"] == 8800
    assert four["bay_count"] == 1


def test_unavailable_duration_and_player_limit(connection):
    with pytest.raises(ValueError, match="unavailable"):
        domain.quote(connection, "cle-20260905-1400-60", 4)
    with pytest.raises(ValueError, match="between 1 and 6"):
        domain.quote(connection, "cle-20260905-1400-120", 7)


def test_capacity_conflict_reschedule_and_cancel(connection):
    reservation = make_reservation(connection)
    changed = domain.update_reservation(
        connection,
        reservation["reservation_id"],
        "account:test-player",
        "reschedule",
        "cle-20260912-1400-120",
    )
    assert changed["status"] == "rescheduled"
    cancelled = domain.update_reservation(
        connection, reservation["reservation_id"], "account:test-player", "cancel"
    )
    assert cancelled["status"] == "cancelled"
    assert cancelled["refund_status"] == "refunded"
    with pytest.raises(ValueError, match="Cancelled"):
        domain.update_reservation(
            connection, reservation["reservation_id"], "account:test-player", "cancel"
        )


def test_slot_capacity_and_foreign_owner(connection):
    connection.execute(
        "UPDATE tg_slots SET reserved_bays=capacity_bays WHERE slot_id='cle-20260905-1400-120'"
    )
    with pytest.raises(ValueError, match="unavailable"):
        domain.quote(connection, "cle-20260905-1400-120", 4)
    assert domain.reservation_detail(connection, "missing", "foreign") is None
