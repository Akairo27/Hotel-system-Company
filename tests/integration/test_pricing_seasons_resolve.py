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


def test_resolve_season_id_variable_hijri_month_in_a_30_day_year(
    db_conn: psycopg.Connection[Any],
) -> None:
    """A synthetic season spanning one Hijri month (month 3, chosen
    arbitrarily) — Hijri months are 29 or 30 days depending on the year,
    and resolve_season_id must track the real boundary either way."""
    _seed_default(db_conn)
    variable_month = seed_season(
        db_conn,
        season_name="Variable Month",
        calendar_type="hijri",
        start_month=3,
        start_day=1,
        end_month=4,
        end_day=1,
        priority=1,
    )

    # 1441 AH: month 3 is 30 days, 2019-10-29 -> 2019-11-28 (verified).
    assert resolve_season_id(db_conn, date(2019, 10, 29)) == variable_month
    assert resolve_season_id(db_conn, date(2019, 11, 27)) == variable_month
    assert resolve_season_id(db_conn, date(2019, 11, 28)) != variable_month  # exclusive


def test_resolve_season_id_variable_hijri_month_in_a_29_day_year(
    db_conn: psycopg.Connection[Any],
) -> None:
    _seed_default(db_conn)
    variable_month = seed_season(
        db_conn,
        season_name="Variable Month",
        calendar_type="hijri",
        start_month=3,
        start_day=1,
        end_month=4,
        end_day=1,
        priority=1,
    )

    # 1440 AH: month 3 is 29 days, 2018-11-09 -> 2018-12-08 (verified).
    assert resolve_season_id(db_conn, date(2018, 11, 9)) == variable_month
    assert resolve_season_id(db_conn, date(2018, 12, 7)) == variable_month
    assert resolve_season_id(db_conn, date(2018, 12, 8)) != variable_month  # exclusive
