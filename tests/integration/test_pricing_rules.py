"""services/pricing/rules.py's resolve_price_rule — field-by-field
inheritance through global -> season -> hotel -> room_type. Each of the
three fields (target_margin_bps, min_profit_by_lead_time, demand_curve)
must resolve independently to whichever scope is the most specific one
that actually set it, per ARCHITECTURE.md's phase-2 design decision —
not "the most specific matching row wins as a whole".
"""

from __future__ import annotations

from typing import Any

import psycopg
import pytest

from services.pricing.errors import IncompletePriceRuleChainError
from services.pricing.rules import resolve_price_rule
from tests.integration._seed import (
    flat_demand_curve,
    flat_min_profit,
    seed_hotel_and_room_type,
    seed_price_rule,
    seed_season,
)

pytestmark = pytest.mark.usefixtures("db_conn")


def _seed_season(conn: psycopg.Connection[Any]) -> int:
    return seed_season(
        conn,
        season_name="Test Season",
        calendar_type="gregorian",
        start_month=1,
        start_day=1,
        end_month=1,
        end_day=1,
    )


def test_resolve_price_rule_uses_global_when_nothing_more_specific(
    db_conn: psycopg.Connection[Any],
) -> None:
    hotel_id, room_type_id = seed_hotel_and_room_type(db_conn)
    season_id = _seed_season(db_conn)
    seed_price_rule(
        db_conn,
        scope="global",
        target_margin_bps=1000,
        min_profit_by_lead_time=flat_min_profit(500),
        demand_curve=flat_demand_curve(11_000),
    )

    rule = resolve_price_rule(db_conn, hotel_id, room_type_id, season_id)

    assert rule.target_margin_bps == 1000
    assert rule.min_profit_by_lead_time == flat_min_profit(500)
    assert rule.demand_curve == flat_demand_curve(11_000)


def test_resolve_price_rule_season_overrides_global(
    db_conn: psycopg.Connection[Any],
) -> None:
    hotel_id, room_type_id = seed_hotel_and_room_type(db_conn)
    season_id = _seed_season(db_conn)
    seed_price_rule(
        db_conn,
        scope="global",
        target_margin_bps=1000,
        min_profit_by_lead_time=flat_min_profit(500),
        demand_curve=flat_demand_curve(),
    )
    seed_price_rule(db_conn, scope="season", scope_id=season_id, target_margin_bps=2000)

    rule = resolve_price_rule(db_conn, hotel_id, room_type_id, season_id)

    assert rule.target_margin_bps == 2000  # from season
    assert rule.min_profit_by_lead_time == flat_min_profit(
        500
    )  # falls through to global
    assert rule.demand_curve == flat_demand_curve()  # falls through to global


def test_resolve_price_rule_hotel_overrides_season(
    db_conn: psycopg.Connection[Any],
) -> None:
    hotel_id, room_type_id = seed_hotel_and_room_type(db_conn)
    season_id = _seed_season(db_conn)
    seed_price_rule(
        db_conn,
        scope="global",
        target_margin_bps=1000,
        min_profit_by_lead_time=flat_min_profit(500),
        demand_curve=flat_demand_curve(),
    )
    seed_price_rule(db_conn, scope="season", scope_id=season_id, target_margin_bps=2000)
    seed_price_rule(db_conn, scope="hotel", scope_id=hotel_id, target_margin_bps=3000)

    rule = resolve_price_rule(db_conn, hotel_id, room_type_id, season_id)

    assert rule.target_margin_bps == 3000  # from hotel


def test_resolve_price_rule_room_type_overrides_hotel(
    db_conn: psycopg.Connection[Any],
) -> None:
    hotel_id, room_type_id = seed_hotel_and_room_type(db_conn)
    season_id = _seed_season(db_conn)
    seed_price_rule(
        db_conn,
        scope="global",
        target_margin_bps=1000,
        min_profit_by_lead_time=flat_min_profit(500),
        demand_curve=flat_demand_curve(),
    )
    seed_price_rule(db_conn, scope="season", scope_id=season_id, target_margin_bps=2000)
    seed_price_rule(db_conn, scope="hotel", scope_id=hotel_id, target_margin_bps=3000)
    seed_price_rule(
        db_conn, scope="room_type", scope_id=room_type_id, target_margin_bps=4000
    )

    rule = resolve_price_rule(db_conn, hotel_id, room_type_id, season_id)

    assert rule.target_margin_bps == 4000  # from room_type


def test_resolve_price_rule_room_type_overrides_global_directly(
    db_conn: psycopg.Connection[Any],
) -> None:
    """No season- or hotel-scoped rule exists at all — room_type must
    still win over global without a middle scope to fall through first."""
    hotel_id, room_type_id = seed_hotel_and_room_type(db_conn)
    season_id = _seed_season(db_conn)
    seed_price_rule(
        db_conn,
        scope="global",
        target_margin_bps=1000,
        min_profit_by_lead_time=flat_min_profit(500),
        demand_curve=flat_demand_curve(),
    )
    seed_price_rule(
        db_conn, scope="room_type", scope_id=room_type_id, target_margin_bps=4000
    )

    rule = resolve_price_rule(db_conn, hotel_id, room_type_id, season_id)

    assert rule.target_margin_bps == 4000


def test_resolve_price_rule_fields_resolve_independently_across_scopes(
    db_conn: psycopg.Connection[Any],
) -> None:
    """The central inheritance claim: each of the three fields comes from
    whichever scope is the most specific one that set *that field*, all
    three potentially different scopes at once."""
    hotel_id, room_type_id = seed_hotel_and_room_type(db_conn)
    season_id = _seed_season(db_conn)
    global_min_profit = flat_min_profit(100)
    season_min_profit = flat_min_profit(200)
    global_demand = flat_demand_curve(10_000)
    hotel_demand = flat_demand_curve(12_000)

    seed_price_rule(
        db_conn,
        scope="global",
        target_margin_bps=1000,
        min_profit_by_lead_time=global_min_profit,
        demand_curve=global_demand,
    )
    # season overrides only min_profit_by_lead_time
    seed_price_rule(
        db_conn,
        scope="season",
        scope_id=season_id,
        min_profit_by_lead_time=season_min_profit,
    )
    # hotel overrides only demand_curve
    seed_price_rule(
        db_conn, scope="hotel", scope_id=hotel_id, demand_curve=hotel_demand
    )
    # room_type overrides only target_margin_bps
    seed_price_rule(
        db_conn, scope="room_type", scope_id=room_type_id, target_margin_bps=4000
    )

    rule = resolve_price_rule(db_conn, hotel_id, room_type_id, season_id)

    assert rule.target_margin_bps == 4000  # from room_type
    assert rule.min_profit_by_lead_time == season_min_profit  # from season
    assert rule.demand_curve == hotel_demand  # from hotel


def test_resolve_price_rule_raises_when_no_global_rule_exists(
    db_conn: psycopg.Connection[Any],
) -> None:
    hotel_id, room_type_id = seed_hotel_and_room_type(db_conn)
    season_id = _seed_season(db_conn)
    # A room_type-scoped rule exists, but nothing supplies the other two
    # fields anywhere in the chain -- there is no global row to fall
    # through to at all.
    seed_price_rule(
        db_conn, scope="room_type", scope_id=room_type_id, target_margin_bps=4000
    )

    with pytest.raises(IncompletePriceRuleChainError):
        resolve_price_rule(db_conn, hotel_id, room_type_id, season_id)


def test_resolve_price_rule_skips_an_inactive_rule(
    db_conn: psycopg.Connection[Any],
) -> None:
    """A deactivated rule (price_rules.is_active, migration 0020) is not in
    the chain at all: the field falls through to the next less specific
    scope that set it, exactly as if the row did not exist. price_rules has
    no DELETE grant for the admin dashboard, so this switch is the only way
    out of a rule created at the wrong scope."""
    hotel_id, room_type_id = seed_hotel_and_room_type(db_conn)
    season_id = _seed_season(db_conn)
    seed_price_rule(
        db_conn,
        scope="global",
        target_margin_bps=1000,
        min_profit_by_lead_time=flat_min_profit(500),
        demand_curve=flat_demand_curve(),
    )
    season_rule_id = seed_price_rule(
        db_conn, scope="season", scope_id=season_id, target_margin_bps=2000
    )
    seed_price_rule(
        db_conn,
        scope="hotel",
        scope_id=hotel_id,
        target_margin_bps=3000,
        is_active=False,
    )

    rule = resolve_price_rule(db_conn, hotel_id, room_type_id, season_id)

    # Asserting on the id, not just the value, is what distinguishes
    # "skipped the disabled hotel row" from "coincidentally the same
    # number" -- 2000 and season_rule_id must agree.
    assert rule.target_margin_bps == 2000
    assert rule.target_margin_rule_id == season_rule_id


def test_resolve_price_rule_falls_through_two_inactive_scopes_to_global(
    db_conn: psycopg.Connection[Any],
) -> None:
    """Pins the OR-chain end to end: disabling every non-global scope that
    could supply a field must still resolve from the (always-active)
    global rule, not raise."""
    hotel_id, room_type_id = seed_hotel_and_room_type(db_conn)
    season_id = _seed_season(db_conn)
    global_rule_id = seed_price_rule(
        db_conn,
        scope="global",
        target_margin_bps=1000,
        min_profit_by_lead_time=flat_min_profit(500),
        demand_curve=flat_demand_curve(),
    )
    seed_price_rule(
        db_conn,
        scope="season",
        scope_id=season_id,
        target_margin_bps=2000,
        is_active=False,
    )
    seed_price_rule(
        db_conn,
        scope="hotel",
        scope_id=hotel_id,
        target_margin_bps=3000,
        is_active=False,
    )

    rule = resolve_price_rule(db_conn, hotel_id, room_type_id, season_id)

    assert rule.target_margin_bps == 1000
    assert rule.target_margin_rule_id == global_rule_id
