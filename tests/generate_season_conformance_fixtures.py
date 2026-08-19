"""Generates tests/season_conformance_fixtures.json — the shared ground
truth both services/pricing/seasons.py (Python, the real pricing engine)
and admin/lib/seasonCalendar.ts (TypeScript, the seasons calendar preview's
independent mirror of it) must agree on, bit for bit.

admin/lib/seasonCalendar.conformance.test.ts reads this exact file and
fails the build the moment the two diverge — a change to season_contains
or resolve_season_id without regenerating this file, or a change to
seasonCalendar.ts that no longer matches it, both break CI. See
db/migrations/0002_seasons.sql and services/pricing/seasons.py's module
docstring for the resolution rules being verified here.

Every scenario below reuses season definitions and dates already verified
against the installed hijridate package directly in
tests/unit/test_pricing_seasons.py and
tests/integration/test_pricing_seasons_resolve.py — this file doesn't
invent new ground truth, it re-expresses those already-trusted cases as a
cross-language fixture, plus resolves each date's `winner` through the
real resolve_season_id (not a hand-duplicated selection rule), so the only
thing under test on the Python side is season_contains's boundary math.

Requires a real Postgres instance — resolve_season_id needs the DB. Run
manually and commit the result whenever a scenario changes:

    TEST_DATABASE_URL=postgresql://postgres:postgres@localhost:5432/hotel_sales_test \
        uv run python -m tests.generate_season_conformance_fixtures
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import psycopg

from lib.hijri import to_hijri
from services.pricing.seasons import Season, resolve_season_id, season_contains
from tests.conftest import _AUTH_SCHEMA_SQL, _ROLES_SQL, MIGRATIONS_DIR
from tests.integration._seed import seed_season

OUTPUT_PATH = Path(__file__).resolve().parent / "season_conformance_fixtures.json"


@dataclass(frozen=True)
class SeasonSpec:
    name: str
    calendar_type: str
    start_month: int
    start_day: int
    end_month: int
    end_day: int
    priority: int = 0
    is_default: bool = False


@dataclass(frozen=True)
class Scenario:
    name: str
    seasons: list[SeasonSpec]
    dates: list[date]


_DEFAULT = SeasonSpec("افتراضي", "hijri", 1, 1, 1, 1, is_default=True)
_DEFAULT_GREGORIAN = SeasonSpec("افتراضي", "gregorian", 1, 1, 1, 1, is_default=True)

SCENARIOS = [
    Scenario(
        name="gregorian_start_inclusive_end_exclusive",
        seasons=[
            _DEFAULT_GREGORIAN,
            SeasonSpec("صيف", "gregorian", 6, 1, 9, 1, priority=1),
        ],
        dates=[
            date(2026, 5, 31),
            date(2026, 6, 1),
            date(2026, 8, 31),
            date(2026, 9, 1),
        ],
    ),
    Scenario(
        name="gregorian_wraps_year_boundary",
        seasons=[
            _DEFAULT_GREGORIAN,
            SeasonSpec("رأس السنة", "gregorian", 12, 20, 1, 10, priority=1),
        ],
        dates=[
            date(2026, 12, 19),
            date(2026, 12, 20),
            date(2026, 12, 31),
            date(2027, 1, 9),
            date(2027, 1, 10),
        ],
    ),
    Scenario(
        name="hijri_wraps_hijri_new_year",
        seasons=[
            _DEFAULT,
            SeasonSpec("رأس السنة الهجرية", "hijri", 12, 1, 1, 1, priority=1),
        ],
        # 1447-12-01 -> 2026-05-18 (29-day Dhu al-Hijjah that year);
        # 1448-01-01 -> 2026-06-16 (verified against hijridate).
        dates=[date(2026, 5, 18), date(2026, 6, 15), date(2026, 6, 16)],
    ),
    Scenario(
        name="gregorian_end_day_beyond_month_rolls_over",
        seasons=[
            _DEFAULT_GREGORIAN,
            SeasonSpec("فبراير", "gregorian", 2, 1, 2, 30, priority=1),
        ],
        # February 2026 has 28 days (not a leap year); end_day=30 rolls
        # over to March 1, so February 28 — the real last day — is
        # included.
        dates=[date(2026, 2, 27), date(2026, 2, 28), date(2026, 3, 1)],
    ),
    Scenario(
        name="gregorian_end_day_beyond_month_rolls_over_leap_year",
        seasons=[
            _DEFAULT_GREGORIAN,
            SeasonSpec("فبراير", "gregorian", 2, 1, 2, 30, priority=1),
        ],
        # 2028 is a leap year: February has 29 days. The same sentinel
        # (end_day=30, the Gregorian reference-year max) must roll over to
        # March 1 either way, including the real last day whether it's 28
        # or 29.
        dates=[date(2028, 2, 28), date(2028, 2, 29), date(2028, 3, 1)],
    ),
    Scenario(
        name="hijri_variable_month_29_day_year_explicit_next_month",
        seasons=[_DEFAULT, SeasonSpec("شهر متغير", "hijri", 3, 1, 4, 1, priority=1)],
        # Hijri month 3, 1440 AH: 29 days, 2018-11-09 -> 2018-12-08.
        dates=[date(2018, 11, 9), date(2018, 12, 7), date(2018, 12, 8)],
    ),
    Scenario(
        name="hijri_variable_month_sentinel_29_day_year",
        seasons=[
            _DEFAULT,
            SeasonSpec("شهر متغير بسنتينل", "hijri", 3, 1, 3, 30, priority=1),
        ],
        dates=[date(2018, 11, 9), date(2018, 12, 7), date(2018, 12, 8)],
    ),
    Scenario(
        name="hijri_variable_month_sentinel_30_day_year",
        seasons=[
            _DEFAULT,
            SeasonSpec("شهر متغير بسنتينل", "hijri", 3, 1, 3, 30, priority=1),
        ],
        # Hijri month 3, 1441 AH: 30 days, 2019-10-29 -> 2019-11-28.
        dates=[date(2019, 10, 29), date(2019, 11, 27), date(2019, 11, 28)],
    ),
    Scenario(
        name="hijri_sentinel_wraps_into_next_hijri_year_29_day_month",
        seasons=[
            _DEFAULT,
            SeasonSpec("نهاية السنة بسنتينل", "hijri", 12, 5, 12, 30, priority=1),
        ],
        # 1447 AH: month 12 has 29 days, day 5 -> 2026-05-22; the sentinel
        # end rolls into Muharram 1 of 1448 AH -> 2026-06-16.
        dates=[date(2026, 5, 22), date(2026, 6, 15), date(2026, 6, 16)],
    ),
    Scenario(
        name="hijri_sentinel_wraps_into_next_hijri_year_30_day_month",
        seasons=[
            _DEFAULT,
            SeasonSpec("نهاية السنة بسنتينل", "hijri", 12, 5, 12, 30, priority=1),
        ],
        # 1443 AH: month 12 has 30 days, day 5 -> 2022-07-04; the sentinel
        # end rolls into Muharram 1 of 1444 AH -> 2022-07-30.
        dates=[date(2022, 7, 4), date(2022, 7, 29), date(2022, 7, 30)],
    ),
    Scenario(
        name="overlap_highest_priority_wins",
        seasons=[
            _DEFAULT_GREGORIAN,
            SeasonSpec("منخفض", "gregorian", 6, 1, 9, 1, priority=1),
            SeasonSpec("مرتفع", "gregorian", 7, 1, 8, 1, priority=2),
        ],
        dates=[date(2026, 7, 15), date(2026, 6, 15)],
    ),
    Scenario(
        name="overlap_tie_breaks_toward_lower_id",
        seasons=[
            _DEFAULT_GREGORIAN,
            SeasonSpec("الأول", "gregorian", 6, 1, 9, 1, priority=1),
            SeasonSpec("الثاني", "gregorian", 6, 1, 9, 1, priority=1),
        ],
        dates=[date(2026, 7, 15)],
    ),
    Scenario(
        name="falls_back_to_default_when_nothing_matches",
        seasons=[
            _DEFAULT_GREGORIAN,
            SeasonSpec("صيف", "gregorian", 6, 1, 9, 1, priority=1),
        ],
        dates=[date(2026, 1, 15)],
    ),
]


def _reset_schema(conn: psycopg.Connection[Any]) -> None:
    conn.execute(_ROLES_SQL)
    conn.execute(_AUTH_SCHEMA_SQL)
    conn.execute("DROP SCHEMA public CASCADE")
    conn.execute("CREATE SCHEMA public")
    for migration in sorted(MIGRATIONS_DIR.glob("*.sql")):
        conn.execute(migration.read_text(encoding="utf-8"))


def _seed_scenario(
    conn: psycopg.Connection[Any], scenario: Scenario
) -> tuple[dict[str, Season], int]:
    """Truncates and re-seeds the seasons table for one scenario.

    Returns the seeded Season objects keyed by name (for season_contains,
    which needs no DB) and the default season's id (to translate
    resolve_season_id's return value back into "falls back to default").
    """
    conn.execute("TRUNCATE seasons RESTART IDENTITY CASCADE")
    seasons_by_name: dict[str, Season] = {}
    default_id: int | None = None
    for spec in scenario.seasons:
        season_id = seed_season(
            conn,
            season_name=spec.name,
            calendar_type=spec.calendar_type,
            start_month=spec.start_month,
            start_day=spec.start_day,
            end_month=spec.end_month,
            end_day=spec.end_day,
            priority=spec.priority,
            is_default=spec.is_default,
        )
        seasons_by_name[spec.name] = Season(
            id=season_id,
            calendar_type=spec.calendar_type,
            start_month=spec.start_month,
            start_day=spec.start_day,
            end_month=spec.end_month,
            end_day=spec.end_day,
            priority=spec.priority,
            is_default=spec.is_default,
        )
        if spec.is_default:
            default_id = season_id
    assert default_id is not None, f"scenario {scenario.name!r} has no default season"
    return seasons_by_name, default_id


def _day_fixture(
    conn: psycopg.Connection[Any],
    seasons_by_name: dict[str, Season],
    default_id: int,
    day: date,
) -> dict[str, Any]:
    matching = sorted(
        name
        for name, season in seasons_by_name.items()
        if not season.is_default and season_contains(season, day)
    )
    winning_id = resolve_season_id(conn, day)
    winner = (
        None
        if winning_id == default_id
        else next(
            name for name, season in seasons_by_name.items() if season.id == winning_id
        )
    )
    return {
        "date": day.isoformat(),
        "hijriYear": to_hijri(day).year,
        "matching": matching,
        "winner": winner,
    }


def build_fixtures(conn: psycopg.Connection[Any]) -> dict[str, Any]:
    scenarios_out = []
    for scenario in SCENARIOS:
        seasons_by_name, default_id = _seed_scenario(conn, scenario)
        scenarios_out.append(
            {
                "name": scenario.name,
                "seasons": [
                    {
                        "id": season.id,
                        "season_name": name,
                        "calendar_type": season.calendar_type,
                        "start_month": season.start_month,
                        "start_day": season.start_day,
                        "end_month": season.end_month,
                        "end_day": season.end_day,
                        "priority": season.priority,
                        "is_default": season.is_default,
                    }
                    for name, season in seasons_by_name.items()
                ],
                "days": [
                    _day_fixture(conn, seasons_by_name, default_id, day)
                    for day in scenario.dates
                ],
            }
        )
    return {"scenarios": scenarios_out}


if __name__ == "__main__":
    dsn = os.environ["TEST_DATABASE_URL"]
    with psycopg.connect(dsn, autocommit=True) as connection:
        _reset_schema(connection)
        fixtures = build_fixtures(connection)
    OUTPUT_PATH.write_text(
        json.dumps(fixtures, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
