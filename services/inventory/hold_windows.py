"""The hold-expiry ladder from ARCHITECTURE.md §6.

Pure and deterministic: `now` is always passed in, never read from the
clock inside the function, per CLAUDE.md §6 ("Pricing functions must be
pure... pass `now` in as a parameter" — the same rule applies here since a
hold window decision is as financially consequential as a price).

Boundary note: ARCHITECTURE.md's table reads ">15 days -> 48h",
"3-15 days -> 12h", "<48 hours -> 2h", which leaves an unstated gap between
48 hours and 3 days. Resolved with the user: the operative boundary is 48
hours (matching the two places it is stated in hours), and "3 days" in the
middle row is an approximate, rounded label — not a second, separate
threshold. So the ladder has exactly two boundaries: 48 hours and 15 days.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta

_LAST_MINUTE_THRESHOLD = timedelta(hours=48)
_LONG_LEAD_THRESHOLD = timedelta(days=15)

_LAST_MINUTE_HOLD_DURATION = timedelta(hours=2)
_STANDARD_HOLD_DURATION = timedelta(hours=12)
_LONG_LEAD_HOLD_DURATION = timedelta(hours=48)


@dataclass(frozen=True)
class HoldWindow:
    """How long a hold stays valid, and whether it requires full payment
    up front instead of the usual payment-on-confirmation flow."""

    duration: timedelta
    requires_full_payment: bool


def hold_window_for(check_in: date, now: datetime) -> HoldWindow:
    """Computes the hold window for a stay starting on check_in, as of now.

    Raises:
        ValueError: if now is not timezone-aware. CLAUDE.md rule 6: every
            timestamp in this system is UTC — a naive datetime here would
            make the lead-time comparison silently wrong.
    """
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware (UTC)")

    check_in_start = datetime.combine(check_in, time.min, tzinfo=UTC)
    lead_time = check_in_start - now

    if lead_time < _LAST_MINUTE_THRESHOLD:
        return HoldWindow(
            duration=_LAST_MINUTE_HOLD_DURATION, requires_full_payment=True
        )
    if lead_time <= _LONG_LEAD_THRESHOLD:
        return HoldWindow(duration=_STANDARD_HOLD_DURATION, requires_full_payment=False)
    return HoldWindow(duration=_LONG_LEAD_HOLD_DURATION, requires_full_payment=False)
