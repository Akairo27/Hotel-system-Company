"""services/worker/hold_expiry.py — releasing expired holds exactly once,
per PLAN.md's mandatory phase 1 test list.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any

import psycopg
import pytest

from services.inventory.operations import confirm_hold, create_hold
from services.worker.hold_expiry import release_expired_holds
from tests.integration._seed import seed_allotment_nights, seed_hotel_and_room_type

pytestmark = pytest.mark.usefixtures("db_conn")

_NOW = datetime(2026, 6, 1, tzinfo=UTC)
_CHECK_IN = date(2026, 6, 5)  # 4 days out: standard 12h hold window
_CHECK_OUT = date(2026, 6, 6)


def _backdate_expiry(
    conn: psycopg.Connection[Any], hold_id: int, expires_at: datetime
) -> None:
    conn.execute(
        "UPDATE holds SET expires_at = %s WHERE id = %s", (expires_at, hold_id)
    )


def _room_night_state(
    conn: psycopg.Connection[Any], hotel_id: int, room_type_id: int
) -> tuple[int, int]:
    row = conn.execute(
        "SELECT held, reserved FROM room_night_inventory rni "
        "JOIN allotments a ON a.id = rni.allotment_id "
        "WHERE a.hotel_id = %s AND a.room_type_id = %s",
        (hotel_id, room_type_id),
    ).fetchone()
    assert row is not None
    return int(row[0]), int(row[1])


def test_release_expired_holds_releases_expired_unresolved_holds(
    db_conn: psycopg.Connection[Any],
) -> None:
    hotel_id, room_type_id = seed_hotel_and_room_type(db_conn)
    seed_allotment_nights(
        db_conn, hotel_id, room_type_id, _CHECK_IN, nights=1, total_rooms=2
    )
    hold_id = create_hold(
        db_conn, hotel_id, room_type_id, _CHECK_IN, _CHECK_OUT, 2, _NOW
    )
    _backdate_expiry(db_conn, hold_id, _NOW - timedelta(minutes=1))

    released = release_expired_holds(db_conn, _NOW)

    assert released == [hold_id]
    held, reserved = _room_night_state(db_conn, hotel_id, room_type_id)
    assert (held, reserved) == (0, 0)


def test_release_expired_holds_ignores_holds_not_yet_expired(
    db_conn: psycopg.Connection[Any],
) -> None:
    hotel_id, room_type_id = seed_hotel_and_room_type(db_conn)
    seed_allotment_nights(
        db_conn, hotel_id, room_type_id, _CHECK_IN, nights=1, total_rooms=2
    )
    create_hold(db_conn, hotel_id, room_type_id, _CHECK_IN, _CHECK_OUT, 2, _NOW)

    released = release_expired_holds(db_conn, _NOW)

    assert released == []
    held, reserved = _room_night_state(db_conn, hotel_id, room_type_id)
    assert (held, reserved) == (2, 0)


def test_release_expired_holds_skips_already_confirmed_holds(
    db_conn: psycopg.Connection[Any],
) -> None:
    hotel_id, room_type_id = seed_hotel_and_room_type(db_conn)
    seed_allotment_nights(
        db_conn, hotel_id, room_type_id, _CHECK_IN, nights=1, total_rooms=2
    )
    hold_id = create_hold(
        db_conn, hotel_id, room_type_id, _CHECK_IN, _CHECK_OUT, 2, _NOW
    )
    confirm_hold(db_conn, hold_id, _NOW)
    _backdate_expiry(db_conn, hold_id, _NOW - timedelta(minutes=1))

    released = release_expired_holds(db_conn, _NOW)

    assert released == []
    held, reserved = _room_night_state(db_conn, hotel_id, room_type_id)
    assert (held, reserved) == (0, 2)  # confirmed rooms stay reserved, untouched


def test_release_expired_holds_returns_empty_list_when_nothing_expired(
    db_conn: psycopg.Connection[Any],
) -> None:
    assert release_expired_holds(db_conn, _NOW) == []


def test_release_expired_holds_skips_a_hold_resolved_by_a_race(
    db_conn: psycopg.Connection[Any],
) -> None:
    """Simulates confirm_hold winning a race against the worker's scan: the
    hold is confirmed after the worker already decided it was expired and
    unresolved, but before the worker's own release_hold call runs.
    """
    hotel_id, room_type_id = seed_hotel_and_room_type(db_conn)
    seed_allotment_nights(
        db_conn, hotel_id, room_type_id, _CHECK_IN, nights=1, total_rooms=2
    )
    hold_id = create_hold(
        db_conn, hotel_id, room_type_id, _CHECK_IN, _CHECK_OUT, 2, _NOW
    )
    _backdate_expiry(db_conn, hold_id, _NOW - timedelta(minutes=1))
    # Confirm before the hold is technically expired, simulating a payment
    # that landed moments before the worker's release would have run.
    confirm_hold(db_conn, hold_id, _NOW - timedelta(minutes=2))

    released = release_expired_holds(db_conn, _NOW)

    assert released == []
    held, reserved = _room_night_state(db_conn, hotel_id, room_type_id)
    assert (held, reserved) == (0, 2)


def test_release_expired_holds_one_already_resolved_does_not_block_the_rest(
    db_conn: psycopg.Connection[Any],
) -> None:
    hotel_a, room_type_a = seed_hotel_and_room_type(db_conn)
    seed_allotment_nights(
        db_conn, hotel_a, room_type_a, _CHECK_IN, nights=1, total_rooms=1
    )
    resolved_hold = create_hold(
        db_conn, hotel_a, room_type_a, _CHECK_IN, _CHECK_OUT, 1, _NOW
    )
    confirm_hold(db_conn, resolved_hold, _NOW)
    _backdate_expiry(db_conn, resolved_hold, _NOW - timedelta(minutes=1))

    hotel_b, room_type_b = seed_hotel_and_room_type(db_conn)
    seed_allotment_nights(
        db_conn, hotel_b, room_type_b, _CHECK_IN, nights=1, total_rooms=1
    )
    open_hold = create_hold(
        db_conn, hotel_b, room_type_b, _CHECK_IN, _CHECK_OUT, 1, _NOW
    )
    _backdate_expiry(db_conn, open_hold, _NOW - timedelta(minutes=1))

    released = release_expired_holds(db_conn, _NOW)

    assert released == [open_hold]
    held, reserved = _room_night_state(db_conn, hotel_b, room_type_b)
    assert (held, reserved) == (0, 0)
