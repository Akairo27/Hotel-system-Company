"""Price rule inheritance — ARCHITECTURE.md §5.

Each of target_margin_bps, min_profit_by_lead_time, and demand_curve
resolves independently through the chain global -> season -> hotel ->
room_type: the most specific scope that has set a non-NULL value for
that particular field wins; a NULL field falls through to the next less
specific matching row. See the phase-2 design decision recorded in
ARCHITECTURE.md — this is deliberately field-by-field, not whole-row
replacement.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import psycopg

from services.pricing.errors import IncompletePriceRuleChainError

# Most specific first — the order fields are resolved in.
_SCOPE_PRECEDENCE = ("room_type", "hotel", "season", "global")


@dataclass(frozen=True)
class ResolvedPriceRule:
    """The fully-resolved rule for one (hotel, room_type, season) —
    every field guaranteed non-None."""

    target_margin_bps: int
    min_profit_by_lead_time: dict[str, Any]
    demand_curve: dict[str, Any]


def resolve_price_rule(
    conn: psycopg.Connection[Any],
    hotel_id: int,
    room_type_id: int,
    season_id: int,
) -> ResolvedPriceRule:
    """Resolves the price rule that applies to a given hotel/room_type on
    a night in the given season.

    Raises:
        IncompletePriceRuleChainError: at least one field is NULL at
            every scope that could supply it — most commonly, no global
            price_rules row exists at all.
    """
    rows = conn.execute(
        "SELECT scope, target_margin_bps, min_profit_by_lead_time, demand_curve "
        "FROM price_rules "
        "WHERE scope = 'global' "
        "OR (scope = 'season' AND scope_id = %(season_id)s) "
        "OR (scope = 'hotel' AND scope_id = %(hotel_id)s) "
        "OR (scope = 'room_type' AND scope_id = %(room_type_id)s)",
        {"season_id": season_id, "hotel_id": hotel_id, "room_type_id": room_type_id},
    ).fetchall()

    by_scope = {row[0]: row for row in rows}

    def _resolve(column_index: int) -> Any:
        for scope in _SCOPE_PRECEDENCE:
            row = by_scope.get(scope)
            if row is not None and row[column_index] is not None:
                return row[column_index]
        return None

    target_margin_bps = _resolve(1)
    min_profit_by_lead_time = _resolve(2)
    demand_curve = _resolve(3)

    incomplete = (
        target_margin_bps is None
        or min_profit_by_lead_time is None
        or demand_curve is None
    )
    if incomplete:
        raise IncompletePriceRuleChainError(
            f"no complete price rule for hotel {hotel_id}/room type {room_type_id}/"
            f"season {season_id} — target_margin_bps={target_margin_bps is not None}, "
            f"min_profit_by_lead_time={min_profit_by_lead_time is not None}, "
            f"demand_curve={demand_curve is not None}"
        )

    return ResolvedPriceRule(
        target_margin_bps=target_margin_bps,
        min_profit_by_lead_time=min_profit_by_lead_time,
        demand_curve=demand_curve,
    )
