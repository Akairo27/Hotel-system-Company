"""Price rule inheritance — ARCHITECTURE.md §5.

Each of target_margin_bps, min_profit_by_lead_time, and demand_curve
resolves independently through the chain global -> season -> hotel ->
room_type: the most specific scope that has set a non-NULL value for
that particular field wins; a NULL field falls through to the next less
specific matching row. See the phase-2 design decision recorded in
ARCHITECTURE.md — this is deliberately field-by-field, not whole-row
replacement.

Only *active* rows participate (price_rules.is_active, migration 0020) —
a deactivated rule is treated as if it did not exist at all, falling
through to the next less specific scope exactly like a row that never
set that field. price_rules has no DELETE grant for the admin dashboard
(a row created at the wrong scope would otherwise shadow the chain
forever with no way out), so is_active is the only mechanism for
removing a rule from resolution.

Because of that, a single resolution can legitimately draw its three
fields from three *different* price_rules rows (e.g. margin from a
room_type-scoped rule, the profit floor from a season-scoped rule, the
demand curve from global). ResolvedPriceRule carries the id that
supplied each field specifically so a quote can record which rule
produced it — a single "the price rule" id would misrepresent this.
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
    every value guaranteed non-None, each paired with the price_rules.id
    of the row that actually supplied it."""

    target_margin_bps: int
    target_margin_rule_id: int
    min_profit_by_lead_time: dict[str, Any]
    min_profit_rule_id: int
    demand_curve: dict[str, Any]
    demand_curve_rule_id: int


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
        "SELECT id, scope, target_margin_bps, min_profit_by_lead_time, demand_curve "
        "FROM price_rules "
        "WHERE is_active "
        "AND (scope = 'global' "
        "OR (scope = 'season' AND scope_id = %(season_id)s) "
        "OR (scope = 'hotel' AND scope_id = %(hotel_id)s) "
        "OR (scope = 'room_type' AND scope_id = %(room_type_id)s))",
        {"season_id": season_id, "hotel_id": hotel_id, "room_type_id": room_type_id},
    ).fetchall()

    by_scope = {row[1]: row for row in rows}

    def _resolve(column_index: int) -> tuple[Any, int | None]:
        for scope in _SCOPE_PRECEDENCE:
            row = by_scope.get(scope)
            if row is not None and row[column_index] is not None:
                return row[column_index], int(row[0])
        return None, None

    target_margin_bps, target_margin_rule_id = _resolve(2)
    min_profit_by_lead_time, min_profit_rule_id = _resolve(3)
    demand_curve, demand_curve_rule_id = _resolve(4)

    if (
        target_margin_bps is None
        or target_margin_rule_id is None
        or min_profit_by_lead_time is None
        or min_profit_rule_id is None
        or demand_curve is None
        or demand_curve_rule_id is None
    ):
        raise IncompletePriceRuleChainError(
            f"no complete price rule for hotel {hotel_id}/room type {room_type_id}/"
            f"season {season_id} — target_margin_bps={target_margin_bps is not None}, "
            f"min_profit_by_lead_time={min_profit_by_lead_time is not None}, "
            f"demand_curve={demand_curve is not None}"
        )

    return ResolvedPriceRule(
        target_margin_bps=target_margin_bps,
        target_margin_rule_id=target_margin_rule_id,
        min_profit_by_lead_time=min_profit_by_lead_time,
        min_profit_rule_id=min_profit_rule_id,
        demand_curve=demand_curve,
        demand_curve_rule_id=demand_curve_rule_id,
    )
