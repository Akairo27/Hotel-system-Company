"""lib/hijri.py — the one Hijri <-> Gregorian conversion module.

Pure, no database — verified conversions come from hijridate's real
Umm al-Qura table, confirmed against the installed package directly
before writing these expectations (CLAUDE.md: verify, don't guess).
"""

from __future__ import annotations

from datetime import date

import pytest

from lib.hijri import HijriDate, from_hijri, hijri_month_length, to_hijri


def test_to_hijri_converts_a_known_date() -> None:
    assert to_hijri(date(2026, 3, 20)) == HijriDate(1447, 10, 1)


def test_from_hijri_converts_a_known_date() -> None:
    assert from_hijri(1447, 9, 1) == date(2026, 2, 18)


def test_hijri_round_trip_is_consistent() -> None:
    gregorian = from_hijri(1447, 9, 15)
    assert to_hijri(gregorian) == HijriDate(1447, 9, 15)


def test_hijri_month_length_is_29_or_30_and_varies_by_year() -> None:
    # Ramadan (month 9): 29 days in 1440 AH, 30 days in 1441 AH — the
    # month's length is not fixed, unlike a generic tabular calendar.
    assert hijri_month_length(1440, 9) == 29
    assert hijri_month_length(1441, 9) == 30


def test_from_hijri_raises_for_a_day_past_the_months_end() -> None:
    # Ramadan 1440 AH has only 29 days.
    with pytest.raises(ValueError, match="1-29"):
        from_hijri(1440, 9, 30)
