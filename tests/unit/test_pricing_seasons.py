"""services/pricing/seasons.py — pure boundary-matching logic (season_contains
and its helpers). No database: Season rows are constructed directly, with
synthetic boundaries chosen only to exercise the engine's mechanics — not
any real hotel's season configuration, which is business data the client
enters and edits from the (future) seasons screen, not something that
belongs in a test file.

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

_HIJRI_NEW_YEAR = Season(
    id=3,
    calendar_type="hijri",
    start_month=12,
    start_day=1,
    end_month=1,
    end_day=1,
    priority=3,
    is_default=False,
)

_FEBRUARY = Season(
    id=4,
    calendar_type="gregorian",
    start_month=2,
    start_day=1,
    end_month=2,
    end_day=30,  # doesn't exist — rolls over to March 1
    priority=4,
    is_default=False,
)

# A synthetic variable-length Hijri month, expressed two equivalent ways:
# explicitly as "start of next month", and via the day=30 sentinel an
# admin might type instead. Month 3 chosen arbitrarily — the mechanic
# being tested (Hijri months are 29 or 30 days, never fixed) applies to
# every Hijri month identically.
_HIJRI_VARIABLE_MONTH = Season(
    id=5,
    calendar_type="hijri",
    start_month=3,
    start_day=1,
    end_month=4,
    end_day=1,
    priority=5,
    is_default=False,
)

_HIJRI_VARIABLE_MONTH_SENTINEL = Season(
    id=6,
    calendar_type="hijri",
    start_month=3,
    start_day=1,
    end_month=3,
    end_day=30,
    priority=6,
    is_default=False,
)

# A day=30 sentinel end landing in month 12 — the rollover must cross into
# Muharram of the *next* Hijri year, not just the next month.
_HIJRI_YEAR_WRAP_SENTINEL = Season(
    id=7,
    calendar_type="hijri",
    start_month=12,
    start_day=5,
    end_month=12,
    end_day=30,
    priority=7,
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


def test_hijri_explicit_next_month_covers_a_29_day_month() -> None:
    # Hijri month 3, 1440 AH: 29 days, 2018-11-09 -> 2018-12-08 (verified).
    assert season_contains(_HIJRI_VARIABLE_MONTH, date(2018, 11, 9))  # start
    assert season_contains(_HIJRI_VARIABLE_MONTH, date(2018, 12, 7))  # real last day
    assert not season_contains(_HIJRI_VARIABLE_MONTH, date(2018, 12, 8))  # next month


def test_hijri_end_day_30_covers_a_29_day_month() -> None:
    # Same range as above, expressed via the end_day=30 sentinel instead
    # of an explicit next-month boundary — must resolve identically.
    assert season_contains(_HIJRI_VARIABLE_MONTH_SENTINEL, date(2018, 11, 9))
    assert season_contains(_HIJRI_VARIABLE_MONTH_SENTINEL, date(2018, 12, 7))
    assert not season_contains(_HIJRI_VARIABLE_MONTH_SENTINEL, date(2018, 12, 8))


def test_hijri_end_day_30_covers_a_30_day_month() -> None:
    # Hijri month 3, 1441 AH: 30 days, 2019-10-29 -> 2019-11-28 (verified).
    assert season_contains(_HIJRI_VARIABLE_MONTH_SENTINEL, date(2019, 10, 29))
    assert season_contains(_HIJRI_VARIABLE_MONTH_SENTINEL, date(2019, 11, 27))
    assert not season_contains(_HIJRI_VARIABLE_MONTH_SENTINEL, date(2019, 11, 28))


def test_hijri_end_day_30_wraps_into_next_hijri_year_in_a_29_day_month() -> None:
    # 1447 AH: month 12 has 29 days, day 5 -> 2026-05-22; the sentinel end
    # rolls into Muharram 1 of 1448 AH -> 2026-06-16 (verified).
    assert season_contains(_HIJRI_YEAR_WRAP_SENTINEL, date(2026, 5, 22))  # start
    assert season_contains(_HIJRI_YEAR_WRAP_SENTINEL, date(2026, 6, 15))  # last day
    assert not season_contains(_HIJRI_YEAR_WRAP_SENTINEL, date(2026, 6, 16))


def test_hijri_end_day_30_wraps_into_next_hijri_year_in_a_30_day_month() -> None:
    # 1443 AH: month 12 has 30 days, day 5 -> 2022-07-04; the sentinel end
    # rolls into Muharram 1 of 1444 AH -> 2022-07-30 (verified).
    assert season_contains(_HIJRI_YEAR_WRAP_SENTINEL, date(2022, 7, 4))  # start
    assert season_contains(_HIJRI_YEAR_WRAP_SENTINEL, date(2022, 7, 29))  # last day
    assert not season_contains(_HIJRI_YEAR_WRAP_SENTINEL, date(2022, 7, 30))
