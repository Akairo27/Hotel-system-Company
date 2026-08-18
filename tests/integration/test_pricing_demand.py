"""services/pricing/demand.py's compute_occupancy — the one part of the
demand module that touches the database.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import psycopg
import pytest

from services.pricing.demand import compute_occupancy
from services.pricing.errors import AllotmentNotFoundError
from tests.integration._seed import seed_allotment_night, seed_hotel_and_room_type

pytestmark = pytest.mark.usefixtures("db_conn")

_NIGHT = date(2026, 9, 1)


def test_compute_occupancy_reflects_reserved_and_held(
    db_conn: psycopg.Connection[Any],
) -> None:
    hotel_id, room_type_id = seed_hotel_and_room_type(db_conn)
    seed_allotment_night(
        db_conn, hotel_id, room_type_id, _NIGHT, total_rooms=10, reserved=3, held=2
    )

    assert compute_occupancy(db_conn, hotel_id, room_type_id, _NIGHT) == 0.5


def test_compute_occupancy_is_zero_when_nothing_reserved_or_held(
    db_conn: psycopg.Connection[Any],
) -> None:
    hotel_id, room_type_id = seed_hotel_and_room_type(db_conn)
    seed_allotment_night(db_conn, hotel_id, room_type_id, _NIGHT, total_rooms=10)

    assert compute_occupancy(db_conn, hotel_id, room_type_id, _NIGHT) == 0.0


def test_compute_occupancy_is_one_when_fully_booked(
    db_conn: psycopg.Connection[Any],
) -> None:
    hotel_id, room_type_id = seed_hotel_and_room_type(db_conn)
    seed_allotment_night(
        db_conn, hotel_id, room_type_id, _NIGHT, total_rooms=10, reserved=10
    )

    assert compute_occupancy(db_conn, hotel_id, room_type_id, _NIGHT) == 1.0


def test_compute_occupancy_is_one_when_total_is_zero(
    db_conn: psycopg.Connection[Any],
) -> None:
    hotel_id, room_type_id = seed_hotel_and_room_type(db_conn)
    seed_allotment_night(db_conn, hotel_id, room_type_id, _NIGHT, total_rooms=0)

    assert compute_occupancy(db_conn, hotel_id, room_type_id, _NIGHT) == 1.0


def test_compute_occupancy_raises_when_no_allotment(
    db_conn: psycopg.Connection[Any],
) -> None:
    hotel_id, room_type_id = seed_hotel_and_room_type(db_conn)

    with pytest.raises(AllotmentNotFoundError):
        compute_occupancy(db_conn, hotel_id, room_type_id, _NIGHT)
