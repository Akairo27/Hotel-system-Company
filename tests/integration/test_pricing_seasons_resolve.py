"""services/pricing/seasons.py's resolve_season_id — the DB-backed
orchestration on top of the pure boundary logic tested in
tests/unit/test_pricing_seasons.py.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import psycopg
import pytest

from services.pricing.errors import NoApplicableSeasonError
from services.pricing.seasons import resolve_season_id
from tests.integration._seed import seed_season

pytestmark = pytest.mark.usefixtures("db_conn")


def _seed_default(conn: psycopg.Connection[Any]) -> int:
    return seed_season(
        conn,
        season_name="Default",
        calendar_type="gregorian",
        start_month=1,
        start_day=1,
        end_month=1,
        end_day=1,
        priority=0,
        is_default=True,
    )


def test_resolve_season_id_picks_highest_priority_on_overlap(
    db_conn: psycopg.Connection[Any],
) -> None:
    _seed_default(db_conn)
    low = seed_season(
        db_conn,
        season_name="Low",
        calendar_type="gregorian",
        start_month=6,
        start_day=1,
        end_month=9,
        end_day=1,
        priority=1,
    )
    high = seed_season(
        db_conn,
        season_name="High",
        calendar_type="gregorian",
        start_month=7,
        start_day=1,
        end_month=8,
        end_day=1,
        priority=2,
    )

    assert resolve_season_id(db_conn, date(2026, 7, 15)) == high
    assert resolve_season_id(db_conn, date(2026, 6, 15)) == low


def test_resolve_season_id_ties_break_toward_lower_id(
    db_conn: psycopg.Connection[Any],
) -> None:
    _seed_default(db_conn)
    first = seed_season(
        db_conn,
        season_name="First",
        calendar_type="gregorian",
        start_month=6,
        start_day=1,
        end_month=9,
        end_day=1,
        priority=1,
    )
    seed_season(
        db_conn,
        season_name="Second",
        calendar_type="gregorian",
        start_month=6,
        start_day=1,
        end_month=9,
        end_day=1,
        priority=1,
    )

    assert resolve_season_id(db_conn, date(2026, 7, 15)) == first


def test_resolve_season_id_falls_back_to_default_when_nothing_matches(
    db_conn: psycopg.Connection[Any],
) -> None:
    default_id = _seed_default(db_conn)
    seed_season(
        db_conn,
        season_name="Summer",
        calendar_type="gregorian",
        start_month=6,
        start_day=1,
        end_month=9,
        end_day=1,
        priority=1,
    )

    assert resolve_season_id(db_conn, date(2026, 1, 15)) == default_id


def test_resolve_season_id_raises_when_no_season_configured(
    db_conn: psycopg.Connection[Any],
) -> None:
    with pytest.raises(NoApplicableSeasonError):
        resolve_season_id(db_conn, date(2026, 1, 15))


def test_resolve_season_id_ramadan_in_a_30_day_hijri_year(
    db_conn: psycopg.Connection[Any],
) -> None:
    _seed_default(db_conn)
    ramadan = seed_season(
        db_conn,
        season_name="Ramadan",
        calendar_type="hijri",
        start_month=9,
        start_day=1,
        end_month=10,
        end_day=1,
        priority=1,
    )

    # 1441 AH: Ramadan is 30 days, 2020-04-24 -> 2020-05-24 (verified).
    assert resolve_season_id(db_conn, date(2020, 4, 24)) == ramadan
    assert resolve_season_id(db_conn, date(2020, 5, 23)) == ramadan
    assert resolve_season_id(db_conn, date(2020, 5, 24)) != ramadan  # end exclusive


def test_resolve_season_id_ramadan_in_a_29_day_hijri_year(
    db_conn: psycopg.Connection[Any],
) -> None:
    _seed_default(db_conn)
    ramadan = seed_season(
        db_conn,
        season_name="Ramadan",
        calendar_type="hijri",
        start_month=9,
        start_day=1,
        end_month=10,
        end_day=1,
        priority=1,
    )

    # 1444 AH: Ramadan is 29 days, 2023-03-23 -> 2023-04-21 (verified).
    assert resolve_season_id(db_conn, date(2023, 3, 23)) == ramadan
    assert resolve_season_id(db_conn, date(2023, 4, 20)) == ramadan
    assert resolve_season_id(db_conn, date(2023, 4, 21)) != ramadan  # end exclusive
