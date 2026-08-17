"""Season resolution — ARCHITECTURE.md §4.

Given a stay date, finds which season applies: the highest-priority
season whose [start, end) window (in its own calendar) contains the date,
falling back to the mandatory default season if none match. Boundaries
are start-inclusive, end-exclusive; the default season is used whenever
nothing else matches, regardless of the default row's own configured
range, so a gap or a data-entry error in the default's bounds can never
leave a date unpriced.

The boundary-matching logic (season_contains and its helpers) is pure —
no I/O, no clock reads — and is unit-tested directly. resolve_season_id
is the only function here that touches the database.
"""

from __future__ import annotations

from calendar import monthrange
from dataclasses import dataclass
from datetime import date
from typing import Any

import psycopg

from lib.hijri import from_hijri, hijri_month_length, to_hijri
from services.pricing.errors import NoApplicableSeasonError


@dataclass(frozen=True)
class Season:
    """A season row from the seasons table (migration 0002)."""

    id: int
    calendar_type: str  # 'hijri' or 'gregorian' — enforced by a DB CHECK
    start_month: int
    start_day: int
    end_month: int
    end_day: int
    priority: int
    is_default: bool


def _clamped_day(calendar_type: str, year: int, month: int, day: int) -> int:
    """Clamps a generic 1-31 day to the actual length of that month/year,
    so a boundary like "end of Ramadan" (day 30) resolves to the real
    last day even in a 29-day year, and "end of April" (day 31) resolves
    to April 30. See db/migrations/0002_seasons.sql's note that this
    validity check is a pricing-engine concern, not a migration-time one.
    """
    if calendar_type == "hijri":
        return min(day, hijri_month_length(year, month))
    return min(day, monthrange(year, month)[1])


def _instance_date(calendar_type: str, year: int, month: int, day: int) -> date:
    clamped = _clamped_day(calendar_type, year, month, day)
    if calendar_type == "hijri":
        return from_hijri(year, month, clamped)
    return date(year, month, clamped)


def _wraps_year(start_month: int, start_day: int, end_month: int, end_day: int) -> bool:
    """True if (end_month, end_day) does not fall chronologically after
    (start_month, start_day) within the same calendar year — the season
    crosses the year boundary (e.g. Dec 20 -> Jan 10)."""
    return (end_month, end_day) <= (start_month, start_day)


def _season_instance(season: Season, anchor_year: int) -> tuple[date, date]:
    """The concrete [start, end) window for the occurrence of `season`
    whose start falls in `anchor_year`, in the season's own calendar."""
    start = _instance_date(
        season.calendar_type, anchor_year, season.start_month, season.start_day
    )
    wraps = _wraps_year(
        season.start_month, season.start_day, season.end_month, season.end_day
    )
    end_year = anchor_year + 1 if wraps else anchor_year
    end = _instance_date(
        season.calendar_type, end_year, season.end_month, season.end_day
    )
    return start, end


def _anchor_years(calendar_type: str, stay_date: date) -> tuple[int, int]:
    """The two candidate anchor years — this one and the previous one, in
    the season's own calendar — whose instances could cover stay_date:
    one for a same-year season, one for a season that started the prior
    year and wraps into this one.
    """
    year = to_hijri(stay_date).year if calendar_type == "hijri" else stay_date.year
    return year - 1, year


def season_contains(season: Season, stay_date: date) -> bool:
    """Whether any occurrence of `season` covers stay_date."""
    for anchor_year in _anchor_years(season.calendar_type, stay_date):
        start, end = _season_instance(season, anchor_year)
        if start <= stay_date < end:
            return True
    return False


def _fetch_seasons(conn: psycopg.Connection[Any]) -> list[Season]:
    rows = conn.execute(
        "SELECT id, calendar_type, start_month, start_day, end_month, end_day, "
        "priority, is_default FROM seasons"
    ).fetchall()
    return [
        Season(
            id=row[0],
            calendar_type=row[1],
            start_month=row[2],
            start_day=row[3],
            end_month=row[4],
            end_day=row[5],
            priority=row[6],
            is_default=row[7],
        )
        for row in rows
    ]


def resolve_season_id(conn: psycopg.Connection[Any], stay_date: date) -> int:
    """Finds the id of the season that applies to stay_date.

    The highest-priority non-default season whose window contains
    stay_date wins; ties break toward the lower id (earliest created).
    Falls back to the default season if none match.

    Raises:
        NoApplicableSeasonError: no season matches and no default season
            is configured — violates ARCHITECTURE.md's "exactly one
            default season always exists" guarantee.
    """
    seasons = _fetch_seasons(conn)
    matching = [
        s for s in seasons if not s.is_default and season_contains(s, stay_date)
    ]
    if matching:
        best = max(matching, key=lambda s: (s.priority, -s.id))
        return best.id

    default = next((s for s in seasons if s.is_default), None)
    if default is None:
        raise NoApplicableSeasonError(
            f"no season matches {stay_date} and no default season is configured"
        )
    return default.id
