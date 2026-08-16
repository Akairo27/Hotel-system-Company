"""Boundary tests for the hold-expiry ladder — see hold_windows.py for the
resolution of the ambiguous "3 days" row in ARCHITECTURE.md's table."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from services.inventory.hold_windows import hold_window_for

_NOW = datetime(2026, 1, 1, tzinfo=UTC)


def test_long_lead_time_gets_48_hour_hold() -> None:
    check_in = (_NOW + timedelta(days=16)).date()
    window = hold_window_for(check_in, _NOW)
    assert window.duration == timedelta(hours=48)
    assert window.requires_full_payment is False


def test_exactly_15_days_still_gets_standard_hold() -> None:
    check_in = (_NOW + timedelta(days=15)).date()
    window = hold_window_for(check_in, _NOW)
    assert window.duration == timedelta(hours=12)
    assert window.requires_full_payment is False


def test_exactly_48_hours_gets_standard_hold_not_last_minute() -> None:
    check_in = (_NOW + timedelta(hours=48)).date()
    window = hold_window_for(check_in, _NOW)
    assert window.duration == timedelta(hours=12)
    assert window.requires_full_payment is False


def test_just_under_48_hours_gets_last_minute_hold() -> None:
    now = datetime(2026, 1, 1, 0, 0, 1, tzinfo=UTC)
    check_in = date(2026, 1, 3)  # lead time is 47h59m59s
    window = hold_window_for(check_in, now)
    assert window.duration == timedelta(hours=2)
    assert window.requires_full_payment is True


def test_check_in_today_gets_last_minute_hold_with_full_payment() -> None:
    window = hold_window_for(_NOW.date(), _NOW)
    assert window.duration == timedelta(hours=2)
    assert window.requires_full_payment is True


def test_naive_datetime_is_rejected() -> None:
    naive_now = _NOW.replace(tzinfo=None)
    with pytest.raises(ValueError, match="timezone-aware"):
        hold_window_for(date(2026, 2, 1), naive_now)
