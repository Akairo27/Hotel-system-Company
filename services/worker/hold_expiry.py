"""Releases expired holds. Runs every minute per ARCHITECTURE.md §6.

Each expired hold is released in its own transaction (release_hold opens
one internally), so one hold already resolved by a race with confirm_hold
never blocks the rest of the batch. Errors this module does not recognise
are not caught here — CLAUDE.md forbids swallowing errors we don't
understand, and the worker's next run will simply retry anything still
expired and unresolved.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import psycopg

from services.inventory.errors import HoldAlreadyResolvedError, HoldNotFoundError
from services.inventory.operations import release_hold

# Resolved by a race with confirm_hold (or another worker run) since the
# scan below — not this worker's job to report.
_RESOLVED_BY_RACE = (HoldNotFoundError, HoldAlreadyResolvedError)


def release_expired_holds(conn: psycopg.Connection[Any], now: datetime) -> list[int]:
    """Releases every hold whose expiry has passed and is not yet resolved.

    Returns the ids actually released, in the order attempted.
    """
    expired_ids = [
        row[0]
        for row in conn.execute(
            "SELECT id FROM holds "
            "WHERE expires_at <= %s AND released_at IS NULL AND confirmed_at IS NULL "
            "ORDER BY id",
            (now,),
        ).fetchall()
    ]

    released: list[int] = []
    for hold_id in expired_ids:
        try:
            release_hold(conn, hold_id, now)
        except _RESOLVED_BY_RACE:
            continue
        released.append(hold_id)
    return released
