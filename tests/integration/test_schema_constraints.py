"""Verifies the phase-1 schema's own guarantees hold against a real Postgres
instance — not that application code respects them, but that the database
itself refuses to be misused. See CLAUDE.md rule 3: application-level checks
are advisory only; the DB constraint is the source of truth.
"""

from __future__ import annotations

from typing import Any

import psycopg
import pytest

pytestmark = pytest.mark.usefixtures("db_conn")


def _returning_id(
    conn: psycopg.Connection[Any], query: str, params: tuple[Any, ...] = ()
) -> int:
    """Runs an INSERT ... RETURNING id and returns that id.

    Centralises the None-check psycopg's Optional fetchone() return type
    otherwise forces at every call site.
    """
    row = conn.execute(query, params).fetchone()
    assert row is not None
    return int(row[0])


def _seed_single_room_night(conn: psycopg.Connection[Any]) -> int:
    """Inserts one hotel/room-type/allotment with a single-room night and
    returns the allotment id."""
    hotel_id = _returning_id(
        conn, "INSERT INTO hotels (hotel_name) VALUES ('Test Hotel') RETURNING id"
    )
    room_type_id = _returning_id(
        conn,
        "INSERT INTO room_types (hotel_id, room_type_name) VALUES (%s, 'Standard') "
        "RETURNING id",
        (hotel_id,),
    )
    allotment_id = _returning_id(
        conn,
        "INSERT INTO allotments (hotel_id, room_type_id, stay_date, total_rooms, "
        "cost_per_night) VALUES (%s, %s, '2026-09-01', 1, 10000) RETURNING id",
        (hotel_id, room_type_id),
    )
    conn.execute(
        "INSERT INTO room_night_inventory (allotment_id, stay_date, total) "
        "VALUES (%s, '2026-09-01', 1)",
        (allotment_id,),
    )
    return allotment_id


def test_inventory_never_oversold_blocks_direct_oversell(
    db_conn: psycopg.Connection[Any],
) -> None:
    allotment_id = _seed_single_room_night(db_conn)

    with pytest.raises(psycopg.errors.CheckViolation, match="inventory_never_oversold"):
        db_conn.execute(
            "UPDATE room_night_inventory SET held = held + 999 WHERE allotment_id = %s",
            (allotment_id,),
        )


def test_inventory_never_oversold_blocks_negative_reserved(
    db_conn: psycopg.Connection[Any],
) -> None:
    allotment_id = _seed_single_room_night(db_conn)

    with pytest.raises(psycopg.errors.CheckViolation, match="inventory_never_oversold"):
        db_conn.execute(
            "UPDATE room_night_inventory SET reserved = -1 WHERE allotment_id = %s",
            (allotment_id,),
        )


def test_allotment_cost_cannot_be_negative(db_conn: psycopg.Connection[Any]) -> None:
    hotel_id = _returning_id(
        db_conn, "INSERT INTO hotels (hotel_name) VALUES ('Test Hotel') RETURNING id"
    )
    room_type_id = _returning_id(
        db_conn,
        "INSERT INTO room_types (hotel_id, room_type_name) VALUES (%s, 'Standard') "
        "RETURNING id",
        (hotel_id,),
    )

    with pytest.raises(
        psycopg.errors.CheckViolation, match="allotments_cost_non_negative"
    ):
        db_conn.execute(
            "INSERT INTO allotments (hotel_id, room_type_id, stay_date, total_rooms, "
            "cost_per_night) VALUES (%s, %s, '2026-09-01', 1, -5)",
            (hotel_id, room_type_id),
        )


def test_room_night_inventory_date_must_match_its_allotment(
    db_conn: psycopg.Connection[Any],
) -> None:
    """The composite foreign key on (allotment_id, stay_date) means a night
    can never be recorded against a date its allotment does not own."""
    allotment_id = _seed_single_room_night(db_conn)

    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        db_conn.execute(
            "INSERT INTO room_night_inventory (allotment_id, stay_date, total) "
            "VALUES (%s, '2026-09-02', 1)",
            (allotment_id,),
        )


def test_at_most_one_default_season(db_conn: psycopg.Connection[Any]) -> None:
    db_conn.execute(
        "INSERT INTO seasons (season_name, calendar_type, start_month, start_day, "
        "end_month, end_day, priority, is_default) "
        "VALUES ('Default', 'gregorian', 1, 1, 12, 31, 0, true)"
    )

    with pytest.raises(psycopg.errors.UniqueViolation, match="seasons_single_default"):
        db_conn.execute(
            "INSERT INTO seasons (season_name, calendar_type, start_month, start_day, "
            "end_month, end_day, priority, is_default) "
            "VALUES ('Another Default', 'hijri', 1, 1, 12, 30, 0, true)"
        )


def test_holds_cannot_be_released_and_confirmed_at_once(
    db_conn: psycopg.Connection[Any],
) -> None:
    hotel_id = _returning_id(
        db_conn, "INSERT INTO hotels (hotel_name) VALUES ('Test Hotel') RETURNING id"
    )
    room_type_id = _returning_id(
        db_conn,
        "INSERT INTO room_types (hotel_id, room_type_name) VALUES (%s, 'Standard') "
        "RETURNING id",
        (hotel_id,),
    )

    with pytest.raises(
        psycopg.errors.CheckViolation, match="holds_not_released_and_confirmed"
    ):
        db_conn.execute(
            "INSERT INTO holds (hotel_id, room_type_id, check_in, check_out, rooms, "
            "expires_at, released_at, confirmed_at) "
            "VALUES (%s, %s, '2026-09-01', '2026-09-02', 1, now(), now(), now())",
            (hotel_id, room_type_id),
        )


def test_hold_room_type_must_belong_to_its_hotel(
    db_conn: psycopg.Connection[Any],
) -> None:
    """The composite foreign key on (room_type_id, hotel_id) means a hold can
    never be recorded against a room type from a different hotel."""
    hotel_id = _returning_id(
        db_conn, "INSERT INTO hotels (hotel_name) VALUES ('Hotel A') RETURNING id"
    )
    other_hotel_id = _returning_id(
        db_conn, "INSERT INTO hotels (hotel_name) VALUES ('Hotel B') RETURNING id"
    )
    room_type_id = _returning_id(
        db_conn,
        "INSERT INTO room_types (hotel_id, room_type_name) VALUES (%s, 'Standard') "
        "RETURNING id",
        (hotel_id,),
    )

    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        db_conn.execute(
            "INSERT INTO holds (hotel_id, room_type_id, check_in, check_out, rooms, "
            "expires_at) VALUES (%s, %s, '2026-09-01', '2026-09-02', 1, now())",
            (other_hotel_id, room_type_id),
        )


def test_rls_denies_anon_even_when_granted_table_select(
    db_conn: psycopg.Connection[Any],
) -> None:
    """RLS is the last line of defence: even an explicit table-level GRANT
    must not expose rows to anon, because zero policies are defined."""
    _seed_single_room_night(db_conn)

    db_conn.execute("GRANT USAGE ON SCHEMA public TO anon")
    db_conn.execute("GRANT SELECT ON hotels TO anon")
    try:
        db_conn.execute("SET SESSION AUTHORIZATION anon")
        rows = db_conn.execute("SELECT * FROM hotels").fetchall()
        assert rows == []
    finally:
        db_conn.execute("RESET SESSION AUTHORIZATION")
        db_conn.execute("REVOKE SELECT ON hotels FROM anon")
        db_conn.execute("REVOKE USAGE ON SCHEMA public FROM anon")


def test_rls_denies_authenticated_even_when_granted_table_select(
    db_conn: psycopg.Connection[Any],
) -> None:
    _seed_single_room_night(db_conn)

    db_conn.execute("GRANT USAGE ON SCHEMA public TO authenticated")
    db_conn.execute("GRANT SELECT ON hotels TO authenticated")
    try:
        db_conn.execute("SET SESSION AUTHORIZATION authenticated")
        rows = db_conn.execute("SELECT * FROM hotels").fetchall()
        assert rows == []
    finally:
        db_conn.execute("RESET SESSION AUTHORIZATION")
        db_conn.execute("REVOKE SELECT ON hotels FROM authenticated")
        db_conn.execute("REVOKE USAGE ON SCHEMA public FROM authenticated")


def test_service_role_bypasses_rls(db_conn: psycopg.Connection[Any]) -> None:
    """service_role is the one role our own backend connects as — it must
    see rows RLS would otherwise hide, or every service query would break."""
    _seed_single_room_night(db_conn)

    db_conn.execute("SET SESSION AUTHORIZATION service_role")
    try:
        rows = db_conn.execute("SELECT * FROM hotels").fetchall()
        assert len(rows) == 1
    finally:
        db_conn.execute("RESET SESSION AUTHORIZATION")
