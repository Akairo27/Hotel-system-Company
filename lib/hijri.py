"""The one and only Hijri <-> Gregorian conversion module — CLAUDE.md rule 6.

Wraps `hijridate`, which implements the real Umm al-Qura calendar (a
published table of month starts, not an arithmetic approximation) — see
the phase 2 dependency decision recorded in the PR that introduced this
file. Every module that needs a Hijri date goes through the three
functions below; nowhere else in this codebase hand-rolls Hijri
arithmetic or imports `hijridate` directly.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from hijridate import Gregorian
from hijridate import Hijri as _Hijri


@dataclass(frozen=True)
class HijriDate:
    """A Hijri calendar date, per the Umm al-Qura calendar."""

    year: int
    month: int
    day: int


def to_hijri(gregorian_date: date) -> HijriDate:
    """Converts a Gregorian date to its Umm al-Qura Hijri equivalent."""
    hijri = Gregorian.fromdate(gregorian_date).to_hijri()
    return HijriDate(hijri.year, hijri.month, hijri.day)


def from_hijri(year: int, month: int, day: int) -> date:
    """Converts an Umm al-Qura Hijri (year, month, day) to a Gregorian date.

    Raises:
        ValueError: day is out of range for the given Hijri month/year —
            Hijri months are 29 or 30 days depending on the year (see
            hijri_month_length), never a fixed 30.
    """
    gregorian = _Hijri(year, month, day).to_gregorian()
    return date(gregorian.year, gregorian.month, gregorian.day)


def hijri_month_length(year: int, month: int) -> int:
    """The number of days in a Hijri month for a specific Hijri year — 29
    or 30, read from the real Umm al-Qura table. A Hijri month's length is
    not fixed: the same month (e.g. Ramadan) can be 29 days in one year
    and 30 in the next.
    """
    return _Hijri(year, month, 1).month_length()
