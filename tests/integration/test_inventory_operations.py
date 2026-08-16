"""Sequential (single-connection) tests for services/inventory/operations.py.

See test_inventory_concurrency.py for the mandatory real-concurrent-
transaction tests — those require two separate connections and are kept
apart from this file's simpler single-connection cases.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any

import psycopg
import pytest

from services.inventory.errors import (
    AllotmentNotFoundError,
    HoldAlreadyResolvedError,
    HoldExpiredError,
    HoldNotFoundError,
    InsufficientInventoryError,
)
from services.inventory.operations import (
    check_availability,
    confirm_hold,
    create_hold,
    release_hold,
)
from tests.integration._seed import seed_allotment_nights, seed_hotel_and_room_type

pytestmark = pytest.mark.usefixtures("db_conn")

_NOW = datetime(2026, 6, 1, tzinfo=UTC)
_CHECK_IN = date(2026, 7, 1)
_CHECK_OUT = date(2026, 7, 3)  # two nights


def _seed_two_night_stay(
    conn: psycopg.Connection[Any], total_rooms: int
) -> tuple[int, int]:
    hotel_id, room_type_id = seed_hotel_and_room_type(conn)
    seed_allotment_nights(
        conn, hotel_id, room_type_id, _CHECK_IN, nights=2, total_rooms=total_rooms
    )
    return hotel_id, room_type_id


def test_check_availability_true_when_capacity_exists(
    db_conn: psycopg.Connection[Any],
) -> None:
    hotel_id, room_type_id = _seed_two_night_stay(db_conn, total_rooms=3)
    assert check_availability(db_conn, hotel_id, room_type_id, _CHECK_IN, _CHECK_OUT, 3)


def test_check_availability_false_when_insufficient_capacity(
    db_conn: psycopg.Connection[Any],
) -> None:
    hotel_id, room_type_id = _seed_two_night_stay(db_conn, total_rooms=2)
    assert not check_availability(
        db_conn, hotel_id, room_type_id, _CHECK_IN, _CHECK_OUT, 3
    )


def test_check_availability_raises_when_check_out_not_after_check_in(
    db_conn: psycopg.Connection[Any],
) -> None:
    hotel_id, room_type_id = _seed_two_night_stay(db_conn, total_rooms=1)
    with pytest.raises(ValueError, match="check_out must be after check_in"):
        check_availability(db_conn, hotel_id, room_type_id, _CHECK_OUT, _CHECK_IN, 1)


def test_check_availability_raises_when_rooms_not_positive(
    db_conn: psycopg.Connection[Any],
) -> None:
    hotel_id, room_type_id = _seed_two_night_stay(db_conn, total_rooms=1)
    with pytest.raises(ValueError, match="rooms must be positive"):
        check_availability(db_conn, hotel_id, room_type_id, _CHECK_IN, _CHECK_OUT, 0)


def test_create_hold_raises_when_rooms_not_positive(
    db_conn: psycopg.Connection[Any],
) -> None:
    hotel_id, room_type_id = _seed_two_night_stay(db_conn, total_rooms=1)
    with pytest.raises(ValueError, match="rooms must be positive"):
        create_hold(db_conn, hotel_id, room_type_id, _CHECK_IN, _CHECK_OUT, 0, _NOW)


def test_check_availability_false_when_night_missing_allotment(
    db_conn: psycopg.Connection[Any],
) -> None:
    hotel_id, room_type_id = seed_hotel_and_room_type(db_conn)
    seed_allotment_nights(
        db_conn, hotel_id, room_type_id, _CHECK_IN, nights=1, total_rooms=5
    )
    # Only one of the two required nights has an allotment.
    assert not check_availability(
        db_conn, hotel_id, room_type_id, _CHECK_IN, _CHECK_OUT, 1
    )


def test_create_hold_increments_held_and_returns_id(
    db_conn: psycopg.Connection[Any],
) -> None:
    hotel_id, room_type_id = _seed_two_night_stay(db_conn, total_rooms=3)

    hold_id = create_hold(
        db_conn, hotel_id, room_type_id, _CHECK_IN, _CHECK_OUT, 2, _NOW
    )

    assert isinstance(hold_id, int)
    rows = db_conn.execute(
        "SELECT held, reserved FROM room_night_inventory rni "
        "JOIN allotments a ON a.id = rni.allotment_id "
        "WHERE a.hotel_id = %s AND a.room_type_id = %s",
        (hotel_id, room_type_id),
    ).fetchall()
    assert rows == [(2, 0), (2, 0)]


def test_create_hold_raises_when_night_missing_allotment(
    db_conn: psycopg.Connection[Any],
) -> None:
    hotel_id, room_type_id = seed_hotel_and_room_type(db_conn)
    seed_allotment_nights(
        db_conn, hotel_id, room_type_id, _CHECK_IN, nights=1, total_rooms=5
    )

    with pytest.raises(AllotmentNotFoundError):
        create_hold(db_conn, hotel_id, room_type_id, _CHECK_IN, _CHECK_OUT, 1, _NOW)


def test_create_hold_impossible_to_exceed_total(
    db_conn: psycopg.Connection[Any],
) -> None:
    hotel_id, room_type_id = _seed_two_night_stay(db_conn, total_rooms=2)
    create_hold(db_conn, hotel_id, room_type_id, _CHECK_IN, _CHECK_OUT, 2, _NOW)

    with pytest.raises(InsufficientInventoryError):
        create_hold(db_conn, hotel_id, room_type_id, _CHECK_IN, _CHECK_OUT, 1, _NOW)

    rows = db_conn.execute(
        "SELECT held, reserved, total FROM room_night_inventory rni "
        "JOIN allotments a ON a.id = rni.allotment_id "
        "WHERE a.hotel_id = %s AND a.room_type_id = %s",
        (hotel_id, room_type_id),
    ).fetchall()
    assert all(held + reserved <= total for held, reserved, total in rows)
    assert all(held == 2 for held, _reserved, _total in rows)


def test_create_hold_expiry_follows_the_hold_window_ladder(
    db_conn: psycopg.Connection[Any],
) -> None:
    hotel_id, room_type_id = _seed_two_night_stay(db_conn, total_rooms=3)
    far_check_in = date(2026, 12, 1)  # far beyond 15 days from _NOW
    seed_allotment_nights(
        db_conn, hotel_id, room_type_id, far_check_in, nights=1, total_rooms=3
    )

    hold_id = create_hold(
        db_conn, hotel_id, room_type_id, far_check_in, date(2026, 12, 2), 1, _NOW
    )

    row = db_conn.execute(
        "SELECT expires_at FROM holds WHERE id = %s", (hold_id,)
    ).fetchone()
    assert row is not None
    assert row[0] - _NOW == timedelta(hours=48)


def test_confirm_hold_moves_held_to_reserved(db_conn: psycopg.Connection[Any]) -> None:
    hotel_id, room_type_id = _seed_two_night_stay(db_conn, total_rooms=3)
    hold_id = create_hold(
        db_conn, hotel_id, room_type_id, _CHECK_IN, _CHECK_OUT, 2, _NOW
    )

    confirm_hold(db_conn, hold_id, _NOW)

    rows = db_conn.execute(
        "SELECT held, reserved FROM room_night_inventory rni "
        "JOIN allotments a ON a.id = rni.allotment_id "
        "WHERE a.hotel_id = %s AND a.room_type_id = %s",
        (hotel_id, room_type_id),
    ).fetchall()
    assert rows == [(0, 2), (0, 2)]


def test_confirm_hold_raises_hold_not_found(db_conn: psycopg.Connection[Any]) -> None:
    with pytest.raises(HoldNotFoundError):
        confirm_hold(db_conn, 999_999, _NOW)


def test_confirm_hold_raises_when_already_confirmed(
    db_conn: psycopg.Connection[Any],
) -> None:
    hotel_id, room_type_id = _seed_two_night_stay(db_conn, total_rooms=3)
    hold_id = create_hold(
        db_conn, hotel_id, room_type_id, _CHECK_IN, _CHECK_OUT, 1, _NOW
    )
    confirm_hold(db_conn, hold_id, _NOW)

    with pytest.raises(HoldAlreadyResolvedError):
        confirm_hold(db_conn, hold_id, _NOW)


def test_confirm_hold_raises_when_expired(db_conn: psycopg.Connection[Any]) -> None:
    hotel_id, room_type_id = _seed_two_night_stay(db_conn, total_rooms=3)
    hold_id = create_hold(
        db_conn, hotel_id, room_type_id, _CHECK_IN, _CHECK_OUT, 1, _NOW
    )

    row = db_conn.execute(
        "SELECT expires_at FROM holds WHERE id = %s", (hold_id,)
    ).fetchone()
    assert row is not None
    past_expiry = row[0]

    with pytest.raises(HoldExpiredError):
        confirm_hold(db_conn, hold_id, past_expiry)


def test_release_hold_decrements_held(db_conn: psycopg.Connection[Any]) -> None:
    hotel_id, room_type_id = _seed_two_night_stay(db_conn, total_rooms=3)
    hold_id = create_hold(
        db_conn, hotel_id, room_type_id, _CHECK_IN, _CHECK_OUT, 2, _NOW
    )

    release_hold(db_conn, hold_id, _NOW)

    rows = db_conn.execute(
        "SELECT held, reserved FROM room_night_inventory rni "
        "JOIN allotments a ON a.id = rni.allotment_id "
        "WHERE a.hotel_id = %s AND a.room_type_id = %s",
        (hotel_id, room_type_id),
    ).fetchall()
    assert rows == [(0, 0), (0, 0)]


def test_release_hold_raises_hold_not_found(db_conn: psycopg.Connection[Any]) -> None:
    with pytest.raises(HoldNotFoundError):
        release_hold(db_conn, 999_999, _NOW)


def test_release_hold_raises_when_already_released(
    db_conn: psycopg.Connection[Any],
) -> None:
    hotel_id, room_type_id = _seed_two_night_stay(db_conn, total_rooms=3)
    hold_id = create_hold(
        db_conn, hotel_id, room_type_id, _CHECK_IN, _CHECK_OUT, 1, _NOW
    )
    release_hold(db_conn, hold_id, _NOW)

    with pytest.raises(HoldAlreadyResolvedError):
        release_hold(db_conn, hold_id, _NOW)


def test_release_hold_raises_when_already_confirmed(
    db_conn: psycopg.Connection[Any],
) -> None:
    hotel_id, room_type_id = _seed_two_night_stay(db_conn, total_rooms=3)
    hold_id = create_hold(
        db_conn, hotel_id, room_type_id, _CHECK_IN, _CHECK_OUT, 1, _NOW
    )
    confirm_hold(db_conn, hold_id, _NOW)

    with pytest.raises(HoldAlreadyResolvedError):
        release_hold(db_conn, hold_id, _NOW)
