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

# Same intent, expressed the naive way an admin might type it: end_day=30
# for a month that isn't always 30 days. Demonstrates the clamp + exclusive-
# end interaction: this silently drops the true last day in a short year.
_RAMADAN_NAIVE_END = Season(
    id=4,
    calendar_type="hijri",
    start_month=9,
    start_day=1,
    end_month=9,
    end_day=30,
    priority=4,
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
    end_day=30,  # doesn't exist — clamps to the real last day
    priority=6,
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


def test_hijri_end_day_clamps_and_can_exclude_the_true_last_day() -> None:
    """Ramadan 1440 AH has only 29 days. A season configured with
    end_day=30 (a plausible admin mistake) clamps to day 29 — but since
    the end is exclusive, day 29 itself (the actual last day of Ramadan
    that year) ends up excluded. This is why a season meant to cover a
    whole variable-length month should be defined as start-of-next-month,
    like _RAMADAN above, not day 29/30 of the same month.
    """
    assert season_contains(_RAMADAN_NAIVE_END, date(2019, 6, 2))  # day 28
    assert not season_contains(_RAMADAN_NAIVE_END, date(2019, 6, 3))  # day 29


def test_gregorian_end_day_clamps_to_the_real_month_length() -> None:
    # February 2026 has 28 days (not a leap year); end_day=30 clamps to 28.
    assert season_contains(_FEBRUARY, date(2026, 2, 27))
    assert not season_contains(_FEBRUARY, date(2026, 2, 28))
