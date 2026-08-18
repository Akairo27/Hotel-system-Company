"""The client's actual 10 season definitions (all Hijri, equal priority,
none is_default), verified against every night of a full Hijri year.

The client's own boundaries (start-inclusive, end-exclusive) leave three
deliberate gaps — this is real production data, not a bug to paper over.
Each gap must fall through to the default season, not silently attach to
whichever neighbouring season happens to be nearby. `_expected_key` is a
hand-derived reference, independent of services/pricing/seasons.py, so
this test cannot pass just by agreeing with its own implementation.
"""

from __future__ import annotations

from typing import Any

import psycopg
import pytest

from lib.hijri import from_hijri, hijri_month_length
from services.pricing.seasons import resolve_season_id
from tests.integration._seed import seed_season

pytestmark = pytest.mark.usefixtures("db_conn")

# Each row: key, name, start month, start day, end month, end day.
_CLIENT_SEASONS = [
    ("long_low", "الموسم الراكد الطويل", 1, 15, 8, 29),
    ("ramadan_first", "رمضان الأول", 9, 1, 9, 10),
    ("ramadan_mid", "رمضان الأوسط", 9, 10, 9, 19),
    ("ramadan_last", "رمضان الأخير", 9, 20, 9, 30),
    ("shawwal", "شوال", 10, 1, 10, 30),
    ("dhu_qidah_first", "ذو القعدة الأول", 11, 1, 11, 25),
    ("pre_hajj", "ما قبل الحج", 11, 25, 12, 4),
    ("hajj", "الحج", 12, 4, 12, 14),
    ("post_hajj", "ما بعد الحج", 12, 14, 12, 20),
    ("dhu_hijjah_tail", "ذو الحجة الأخير", 12, 20, 12, 30),
]


def _expected_key(month: int, day: int) -> str | None:
    """The season key a given Hijri (month, day) should resolve to, or
    None for one of the three known gaps in the client's own definitions:

    - Muharram 1-14: before "the long low season" starts.
    - Sha'ban 29 (and 30, in a 30-day Sha'ban year): the long low season
      ends there exclusively, and Ramadan doesn't start until month 9.
    - Ramadan 19: "ramadan_mid" (10-19) ends exclusively at 19; "ramadan_
      last" (20-30) starts at 20. Day 19 belongs to neither.
    """
    if (1, 1) <= (month, day) < (1, 15):
        return None  # gap: before long_low starts
    if (1, 15) <= (month, day) < (8, 29):
        return "long_low"
    if (8, 29) <= (month, day) < (9, 1):
        return None  # gap: long_low's exclusive end vs. Ramadan's start
    if (9, 1) <= (month, day) < (9, 10):
        return "ramadan_first"
    if (9, 10) <= (month, day) < (9, 19):
        return "ramadan_mid"
    if (month, day) == (9, 19):
        return None  # gap: the single day between ramadan_mid and ramadan_last
    if (9, 20) <= (month, day) <= (9, 30):
        return "ramadan_last"
    if (10, 1) <= (month, day) <= (10, 30):
        return "shawwal"
    if (11, 1) <= (month, day) < (11, 25):
        return "dhu_qidah_first"
    if (11, 25) <= (month, day) < (12, 4):
        return "pre_hajj"
    if (12, 4) <= (month, day) < (12, 14):
        return "hajj"
    if (12, 14) <= (month, day) < (12, 20):
        return "post_hajj"
    if (12, 20) <= (month, day) <= (12, 30):
        return "dhu_hijjah_tail"
    raise AssertionError(f"unmapped hijri day: {month:02d}-{day:02d}")


def _seed_client_calendar(conn: psycopg.Connection[Any]) -> dict[str, int]:
    default_id = seed_season(
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
    ids = {"default": default_id}
    for key, name, start_month, start_day, end_month, end_day in _CLIENT_SEASONS:
        ids[key] = seed_season(
            conn,
            season_name=name,
            calendar_type="hijri",
            start_month=start_month,
            start_day=start_day,
            end_month=end_month,
            end_day=end_day,
            priority=1,
        )
    return ids


@pytest.mark.parametrize(
    "hijri_year",
    [
        1447,  # Shawwal and Dhu al-Hijjah both 29 days
        1444,  # Shawwal and Dhu al-Hijjah both 30 days
    ],
)
def test_every_night_of_the_year_resolves_to_the_expected_season(
    db_conn: psycopg.Connection[Any], hijri_year: int
) -> None:
    ids = _seed_client_calendar(db_conn)

    for month in range(1, 13):
        for day in range(1, hijri_month_length(hijri_year, month) + 1):
            expected_key = _expected_key(month, day)
            expected_id = ids["default"] if expected_key is None else ids[expected_key]
            stay_date = from_hijri(hijri_year, month, day)

            resolved_id = resolve_season_id(db_conn, stay_date)

            assert resolved_id == expected_id, (
                f"{hijri_year}-{month:02d}-{day:02d} ({stay_date}): "
                f"expected {expected_key or 'default'}, got season id {resolved_id}"
            )
