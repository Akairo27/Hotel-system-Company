"""Seeding helpers shared by services/inventory integration tests.

Not a test module itself (no test_ prefix), so pytest does not collect it.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import psycopg


def returning_id(
    conn: psycopg.Connection[Any], query: str, params: tuple[Any, ...] = ()
) -> int:
    """Runs an INSERT ... RETURNING id and returns that id."""
    row = conn.execute(query, params).fetchone()
    assert row is not None
    return int(row[0])


def seed_hotel_and_room_type(conn: psycopg.Connection[Any]) -> tuple[int, int]:
    hotel_id = returning_id(
        conn, "INSERT INTO hotels (hotel_name) VALUES ('Test Hotel') RETURNING id"
    )
    room_type_id = returning_id(
        conn,
        "INSERT INTO room_types (hotel_id, room_type_name) VALUES (%s, 'Standard') "
        "RETURNING id",
        (hotel_id,),
    )
    return hotel_id, room_type_id


def seed_allotment_nights(
    conn: psycopg.Connection[Any],
    hotel_id: int,
    room_type_id: int,
    check_in: date,
    nights: int,
    total_rooms: int,
    cost_per_night: int = 10_000,
) -> None:
    """Creates one allotment and one room_night_inventory row per night,
    each starting with `total_rooms` capacity and zero reserved/held."""
    for offset in range(nights):
        night = check_in + timedelta(days=offset)
        allotment_id = returning_id(
            conn,
            "INSERT INTO allotments (hotel_id, room_type_id, stay_date, total_rooms, "
            "cost_per_night) VALUES (%s, %s, %s, %s, %s) RETURNING id",
            (hotel_id, room_type_id, night, total_rooms, cost_per_night),
        )
        conn.execute(
            "INSERT INTO room_night_inventory (allotment_id, stay_date, total) "
            "VALUES (%s, %s, %s)",
            (allotment_id, night, total_rooms),
        )
