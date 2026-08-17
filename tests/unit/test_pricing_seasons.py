"""services/pricing/seasons.py — pure boundary-matching logic (season_contains
and its helpers). No database: Season rows are constructed directly.

Gregorian and Hijri dates used below were verified against the installed
hijridate package directly before being hardcoded here (see the PR
description) — not guessed.
"""

from __future__ import annotations

from datetime import date

from services.pricing.seasons import Season, season_contains

_SUMMER = Season(
    id=1,
    calendar_type="gregorian",
    start_month=6,
    start_day=1,
    end_month=9,
    end_day=1,
    priority=1,
    is_default=False,
)

_NEW_YEAR = Season(
    id=2,
    calendar_type="gregorian",
    start_month=12,
    start_day=20,
    end_month=1,
    end_day=10,
    priority=2,
    is_default=False,
)

# Spans exactly one Hijri month: Ramadan (9) -> Shawwal (10), i.e. "all of
# Ramadan" expressed correctly as start-of-next-month, not day 29/30.
_RAMADAN = Season(
    id=3,
    calendar_type="hijri",
    start_month=9,
    start_day=1,
    end_month=10,
    end_day=1,
    priority=3,
    is_default=False,
)

_HIJRI_NEW_YEAR = Season(
    id=5,
    calendar_type="hijri",
    start_month=12,
    start_day=1,
    end_month=1,
    end_day=1,
    priority=5,
    is_default=False,
)

_FEBRUARY = Season(
    id=6,
    calendar_type="gregorian",
    start_month=2,
    start_day=1,
    end_month=2,
    end_day=30,  # doesn't exist — rolls over to March 1
    priority=6,
    is_default=False,
)

# Two of the client's actual season definitions, exactly as configured:
# end_day=30 for Hijri months that are sometimes 29 days. This is real
# production data, not a hypothetical — season_contains must treat day 30
# as "through the end of the month" in every year, short or long.
_SHAWWAL = Season(
    id=7,
    calendar_type="hijri",
    start_month=10,
    start_day=1,
    end_month=10,
    end_day=30,
    priority=7,
    is_default=False,
)

_DHU_AL_HIJJAH_TAIL = Season(
    id=8,
    calendar_type="hijri",
    start_month=12,
    start_day=20,
    end_month=12,
    end_day=30,
    priority=8,
    is_default=False,
)


def test_gregorian_season_start_is_inclusive() -> None:
    assert season_contains(_SUMMER, date(2026, 6, 1))


def test_gregorian_season_day_before_start_does_not_match() -> None:
    assert not season_contains(_SUMMER, date(2026, 5, 31))


def test_gregorian_season_end_is_exclusive() -> None:
    assert not season_contains(_SUMMER, date(2026, 9, 1))


def test_gregorian_season_day_before_end_matches() -> None:
    assert season_contains(_SUMMER, date(2026, 8, 31))


def test_gregorian_season_unrelated_date_does_not_match() -> None:
    assert not season_contains(_SUMMER, date(2026, 1, 15))


def test_gregorian_season_wraps_year_boundary_in_december() -> None:
    assert season_contains(_NEW_YEAR, date(2026, 12, 20))
    assert season_contains(_NEW_YEAR, date(2026, 12, 31))


def test_gregorian_season_wraps_year_boundary_in_january() -> None:
    assert season_contains(_NEW_YEAR, date(2027, 1, 9))
    assert not season_contains(_NEW_YEAR, date(2027, 1, 10))  # end exclusive
    assert not season_contains(_NEW_YEAR, date(2026, 12, 19))  # before start


def test_hijri_season_start_is_inclusive() -> None:
    # Ramadan 1447 AH starts 2026-02-18 (verified against hijridate).
    assert season_contains(_RAMADAN, date(2026, 2, 18))


def test_hijri_season_end_is_exclusive() -> None:
    # Shawwal 1 1447 AH (end of Ramadan) is 2026-03-20.
    assert not season_contains(_RAMADAN, date(2026, 3, 20))
    assert season_contains(_RAMADAN, date(2026, 3, 19))


def test_hijri_season_wraps_hijri_new_year() -> None:
    # 1447-12-01 -> 2026-05-18 (29-day Dhu al-Hijjah that year);
    # 1448-01-01 -> 2026-06-16 (verified against hijridate).
    assert season_contains(_HIJRI_NEW_YEAR, date(2026, 5, 18))
    assert season_contains(_HIJRI_NEW_YEAR, date(2026, 6, 15))
    assert not season_contains(_HIJRI_NEW_YEAR, date(2026, 6, 16))  # end exclusive


def test_gregorian_end_day_beyond_month_rolls_to_next_month() -> None:
    # February 2026 has 28 days (not a leap year); end_day=30 rolls over
    # to March 1, so February 28 — the real last day — is included.
    assert season_contains(_FEBRUARY, date(2026, 2, 27))
    assert season_contains(_FEBRUARY, date(2026, 2, 28))
    assert not season_contains(_FEBRUARY, date(2026, 3, 1))  # end exclusive


def test_hijri_end_day_30_covers_the_whole_month_in_a_29_day_year() -> None:
    # Shawwal 1447 AH has 29 days: 2026-03-20 -> 2026-04-17 (verified).
    assert season_contains(_SHAWWAL, date(2026, 3, 20))  # start
    assert season_contains(_SHAWWAL, date(2026, 4, 17))  # real last day
    assert not season_contains(_SHAWWAL, date(2026, 4, 18))  # next month


def test_hijri_end_day_30_covers_the_whole_month_in_a_30_day_year() -> None:
    # Shawwal 1440 AH has 30 days: 2019-06-04 -> 2019-07-03 (verified).
    assert season_contains(_SHAWWAL, date(2019, 6, 4))  # start
    assert season_contains(_SHAWWAL, date(2019, 7, 3))  # real last day
    assert not season_contains(_SHAWWAL, date(2019, 7, 4))  # next month


def test_hijri_end_day_30_covers_a_month_ending_at_hijri_new_year() -> None:
    """Dhu al-Hijjah is the last Hijri month — "through its end" lands in
    Muharram of the *following* AH year. 1447 AH: Dhu al-Hijjah has 29
    days, 2026-06-06 -> 2026-06-15 (verified)."""
    assert season_contains(_DHU_AL_HIJJAH_TAIL, date(2026, 6, 6))  # start
    assert season_contains(_DHU_AL_HIJJAH_TAIL, date(2026, 6, 15))  # last day
    assert not season_contains(_DHU_AL_HIJJAH_TAIL, date(2026, 6, 16))


def test_hijri_end_day_30_covers_a_30_day_month_ending_at_hijri_new_year() -> None:
    # 1443 AH: Dhu al-Hijjah has 30 days, 2022-07-19 -> 2022-07-29 (verified).
    assert season_contains(_DHU_AL_HIJJAH_TAIL, date(2022, 7, 19))  # start
    assert season_contains(_DHU_AL_HIJJAH_TAIL, date(2022, 7, 29))  # last day
    assert not season_contains(_DHU_AL_HIJJAH_TAIL, date(2022, 7, 30))
