from __future__ import annotations

import sqlite3

import pytest

from backend import domain


@pytest.fixture()
def connection():
    value = sqlite3.connect(":memory:")
    value.row_factory = sqlite3.Row
    domain.migrate(value)
    domain.seed(value)
    yield value
    value.close()


def make_booking(connection):
    return domain.create_booking(
        connection, owner="subject_test", session_id="pasta-pa-20260926-1300",
        party_size=1, attendee_name="Test Guest", attendee_email="test@example.test",
        payment_flow_id="payflow_test_booking_123", idempotency_key="domain-test",
    )


def test_reschedule_and_cancel(connection):
    booking = make_booking(connection)
    changed = domain.update_booking(
        connection, booking_id=booking["booking_id"], owner="subject_test",
        action="reschedule", session_id="pasta-pa-20260927-1500",
    )
    assert changed["status"] == "rescheduled"
    assert changed["session_id"] == "pasta-pa-20260927-1500"
    cancelled = domain.update_booking(
        connection, booking_id=booking["booking_id"], owner="subject_test", action="cancel"
    )
    assert cancelled["status"] == "cancelled"


def test_cancelled_booking_cannot_change(connection):
    booking = make_booking(connection)
    domain.update_booking(connection, booking_id=booking["booking_id"], owner="subject_test", action="cancel")
    with pytest.raises(ValueError, match="Cancelled"):
        domain.update_booking(
            connection, booking_id=booking["booking_id"], owner="subject_test",
            action="reschedule", session_id="pasta-pa-20260927-1500",
        )
