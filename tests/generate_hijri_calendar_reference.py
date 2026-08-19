"""Generates admin/lib/hijriCalendarReference.json — the one Hijri lookup
table the admin dashboard's seasons calendar preview reads directly, in the
browser, with zero live calls back into lib/hijri.py. This keeps CLAUDE.md
rule 6 intact ("Hijri conversion happens in exactly one module... nowhere
else"): the admin frontend never computes a Hijri date itself, it only
looks up facts this script already computed through lib/hijri.py.

Run manually and commit the result whenever the covered year range needs
to change — nothing imports this module at runtime:

    uv run python -m tests.generate_hijri_calendar_reference

Covers Hijri years 1439-1461 inclusive. 1439 and 1461 exist only as a
one-year lookback/lookahead buffer — a Hijri-calendar season's window can
start in the year *before* the one being displayed and still overlap it
(same reasoning resolve_season_id applies by checking two anchor years for
a single date; the calendar preview checks three, to resolve a whole
year's worth of days at once — see seasonCalendar.ts's
candidateInstancesOverlapping). Without both buffer years, viewing either
end of the admin UI's own selectable range (1440-1460, see
LAST_SELECTABLE_YEAR) would look up a year outside the table and crash —
caught by admin/lib/seasonCalendar.conformance.test.ts before it shipped.
"""

from __future__ import annotations

import json
from pathlib import Path

from lib.hijri import from_hijri, hijri_month_length

FIRST_YEAR = 1440
LAST_SELECTABLE_YEAR = 1460
_FIRST_GENERATED_YEAR = FIRST_YEAR - 1
_LAST_GENERATED_YEAR = LAST_SELECTABLE_YEAR + 1

_ADMIN_LIB_DIR = Path(__file__).resolve().parent.parent / "admin" / "lib"
OUTPUT_PATH = _ADMIN_LIB_DIR / "hijriCalendarReference.json"


def _year_months(year: int) -> list[dict[str, int | str]]:
    return [
        {
            "month": month,
            "length": hijri_month_length(year, month),
            "gregorianStart": from_hijri(year, month, 1).isoformat(),
        }
        for month in range(1, 13)
    ]


def build_reference() -> dict[str, object]:
    """The full generated table: which years it covers, and which of those
    are meant to be offered to the admin (see module docstring)."""
    return {
        "firstYear": FIRST_YEAR,
        "lastSelectableYear": LAST_SELECTABLE_YEAR,
        "years": {
            str(year): _year_months(year)
            for year in range(_FIRST_GENERATED_YEAR, _LAST_GENERATED_YEAR + 1)
        },
    }


if __name__ == "__main__":
    OUTPUT_PATH.write_text(
        json.dumps(build_reference(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
