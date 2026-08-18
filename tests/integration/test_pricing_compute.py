"""services/pricing/compute.py's compute_quote — the mandatory phase-2
test list from PLAN.md: a stay spanning two and three seasons, the floor
never dropping below cost, demand never touching min_allowed, manual
override precedence, plus the general correctness and validation cases.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any

import psycopg
import pytest

from services.pricing.compute import compute_quote
from services.pricing.errors import (
    AllotmentNotFoundError,
    IncompletePriceRuleChainError,
    InconsistentPriceConfigurationError,
)
from tests.integration._seed import (
    flat_demand_curve,
    flat_min_profit,
    seed_allotment_night,
    seed_hotel_and_room_type,
    seed_price_rule,
    seed_season,
)

pytestmark = pytest.mark.usefixtures("db_conn")

_NOW = datetime(2026, 8, 1, tzinfo=UTC)


def _seed_default_season(conn: psycopg.Connection[Any]) -> int:
    return seed_season(
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


def _seed_global_rule(
    conn: psycopg.Connection[Any],
    *,
    target_margin_bps: int = 2000,
    min_profit_halalas: int = 2000,
    demand_multiplier_bps: int = 10_000,
) -> None:
    seed_price_rule(
        conn,
        scope="global",
        target_margin_bps=target_margin_bps,
        min_profit_by_lead_time=flat_min_profit(min_profit_halalas),
        demand_curve=flat_demand_curve(demand_multiplier_bps),
    )


def test_compute_quote_prices_a_single_night(db_conn: psycopg.Connection[Any]) -> None:
    hotel_id, room_type_id = seed_hotel_and_room_type(db_conn)
    _seed_default_season(db_conn)
    _seed_global_rule(db_conn, target_margin_bps=2000, min_profit_halalas=2000)
    seed_allotment_night(
        db_conn,
        hotel_id,
        room_type_id,
        date(2026, 9, 1),
        total_rooms=5,
        cost_per_night=10_000,
    )

    quote = compute_quote(
        db_conn, hotel_id, room_type_id, date(2026, 9, 1), date(2026, 9, 2), 1, _NOW
    )

    # cost=10000, margin=20% -> markup 12000bps, demand 1.0x -> ask=12000
    assert quote.nights[0].ask == 12_000
    assert quote.nights[0].min_allowed == 12_000  # cost + 2000 floor
    assert quote.ask_price_total == 12_000
    assert quote.min_allowed_total == 12_000


def test_compute_quote_multiplies_by_room_count(
    db_conn: psycopg.Connection[Any],
) -> None:
    hotel_id, room_type_id = seed_hotel_and_room_type(db_conn)
    _seed_default_season(db_conn)
    _seed_global_rule(db_conn)
    seed_allotment_night(
        db_conn,
        hotel_id,
        room_type_id,
        date(2026, 9, 1),
        total_rooms=5,
        cost_per_night=10_000,
    )

    quote = compute_quote(
        db_conn, hotel_id, room_type_id, date(2026, 9, 1), date(2026, 9, 2), 3, _NOW
    )

    assert quote.ask_price_total == quote.nights[0].ask * 3
    assert quote.min_allowed_total == quote.nights[0].min_allowed * 3


def test_compute_quote_stay_spanning_two_seasons(
    db_conn: psycopg.Connection[Any],
) -> None:
    hotel_id, room_type_id = seed_hotel_and_room_type(db_conn)
    _seed_default_season(db_conn)
    _seed_global_rule(db_conn, target_margin_bps=1000, min_profit_halalas=1000)

    season_a = seed_season(
        db_conn,
        season_name="A",
        calendar_type="gregorian",
        start_month=9,
        start_day=1,
        end_month=9,
        end_day=2,
        priority=1,
    )
    season_b = seed_season(
        db_conn,
        season_name="B",
        calendar_type="gregorian",
        start_month=9,
        start_day=2,
        end_month=9,
        end_day=3,
        priority=1,
    )
    # Season B carries a higher margin than the global default.
    seed_price_rule(db_conn, scope="season", scope_id=season_b, target_margin_bps=5000)

    for offset in range(2):
        seed_allotment_night(
            db_conn,
            hotel_id,
            room_type_id,
            date(2026, 9, 1 + offset),
            total_rooms=5,
            cost_per_night=10_000,
        )

    quote = compute_quote(
        db_conn, hotel_id, room_type_id, date(2026, 9, 1), date(2026, 9, 3), 1, _NOW
    )

    assert quote.nights[0].season_id == season_a
    assert quote.nights[1].season_id == season_b
    assert quote.nights[0].ask == 11_000  # 10% margin
    assert quote.nights[1].ask == 15_000  # 50% margin
    assert quote.nights[0].season_id != quote.nights[1].season_id


def test_compute_quote_stay_spanning_three_seasons(
    db_conn: psycopg.Connection[Any],
) -> None:
    hotel_id, room_type_id = seed_hotel_and_room_type(db_conn)
    _seed_default_season(db_conn)
    _seed_global_rule(db_conn, target_margin_bps=1000, min_profit_halalas=1000)

    margins = {}
    for day, margin in zip((1, 2, 3), (2000, 3000, 4000), strict=True):
        season_id = seed_season(
            db_conn,
            season_name=f"S{day}",
            calendar_type="gregorian",
            start_month=9,
            start_day=day,
            end_month=9,
            end_day=day + 1,
            priority=1,
        )
        seed_price_rule(
            db_conn, scope="season", scope_id=season_id, target_margin_bps=margin
        )
        margins[season_id] = margin
        seed_allotment_night(
            db_conn,
            hotel_id,
            room_type_id,
            date(2026, 9, day),
            total_rooms=5,
            cost_per_night=10_000,
        )

    quote = compute_quote(
        db_conn, hotel_id, room_type_id, date(2026, 9, 1), date(2026, 9, 4), 1, _NOW
    )

    assert len(quote.nights) == 3
    season_ids = [n.season_id for n in quote.nights]
    assert len(set(season_ids)) == 3  # three genuinely distinct seasons
    for night in quote.nights:
        expected_markup_bps = 10_000 + margins[night.season_id]
        assert night.ask == 10_000 * expected_markup_bps // 10_000


@pytest.mark.parametrize(
    ("margin_bps", "min_profit"),
    [
        (0, 1),  # zero margin, minimal profit floor
        (50_000, 500),  # huge margin
        (5000, 2000),  # sizeable profit floor, comfortably cleared by ask
    ],
)
def test_compute_quote_floor_never_drops_below_cost(
    db_conn: psycopg.Connection[Any], margin_bps: int, min_profit: int
) -> None:
    """The mandatory floor test: across a range of margins, an aggressive
    demand multiplier, and profit-band values, min_allowed is always
    exactly cost + min_profit — never less than cost, regardless of what
    demand or margin do to ask_price. Each case gets its own hotel so the
    single global price_rules row per test run stays unambiguous."""
    hotel_id, room_type_id = seed_hotel_and_room_type(db_conn)
    _seed_default_season(db_conn)
    cost = 10_000
    seed_price_rule(
        db_conn,
        scope="global",
        target_margin_bps=margin_bps,
        min_profit_by_lead_time=flat_min_profit(min_profit),
        demand_curve=flat_demand_curve(20_000),  # aggressive 2x demand multiplier
    )
    seed_allotment_night(
        db_conn,
        hotel_id,
        room_type_id,
        date(2026, 9, 1),
        total_rooms=5,
        cost_per_night=cost,
    )

    quote = compute_quote(
        db_conn, hotel_id, room_type_id, date(2026, 9, 1), date(2026, 9, 2), 1, _NOW
    )

    assert quote.nights[0].min_allowed == cost + min_profit
    assert quote.nights[0].min_allowed >= cost


def test_compute_quote_demand_never_affects_min_allowed(
    db_conn: psycopg.Connection[Any],
) -> None:
    hotel_id, room_type_id = seed_hotel_and_room_type(db_conn)
    _seed_default_season(db_conn)
    seed_price_rule(
        db_conn,
        scope="global",
        target_margin_bps=2000,
        min_profit_by_lead_time=flat_min_profit(2000),
        demand_curve={
            "occupancy_bands": [
                {"min": 0, "max": 0.5, "multiplier_bps": 10_000},
                {
                    "min": 0.5,
                    "max": 1,
                    "multiplier_bps": 30_000,
                },  # 3x at high occupancy
            ],
            "lead_time_bands": [
                {"min_lead_days": 0, "max_lead_days": None, "multiplier_bps": 10_000}
            ],
        },
    )
    # Night 1: low occupancy. Night 2: high occupancy.
    seed_allotment_night(
        db_conn,
        hotel_id,
        room_type_id,
        date(2026, 9, 1),
        total_rooms=10,
        cost_per_night=10_000,
    )
    seed_allotment_night(
        db_conn,
        hotel_id,
        room_type_id,
        date(2026, 9, 2),
        total_rooms=10,
        reserved=8,
        cost_per_night=10_000,
    )

    quote = compute_quote(
        db_conn, hotel_id, room_type_id, date(2026, 9, 1), date(2026, 9, 3), 1, _NOW
    )

    assert quote.nights[0].ask != quote.nights[1].ask  # demand did change ask
    assert (
        quote.nights[0].min_allowed == quote.nights[1].min_allowed
    )  # but never the floor
    assert quote.nights[0].min_allowed == 12_000


def test_compute_quote_manual_override_takes_precedence(
    db_conn: psycopg.Connection[Any],
) -> None:
    hotel_id, room_type_id = seed_hotel_and_room_type(db_conn)
    _seed_default_season(db_conn)
    _seed_global_rule(db_conn)
    seed_allotment_night(
        db_conn,
        hotel_id,
        room_type_id,
        date(2026, 9, 1),
        total_rooms=5,
        cost_per_night=10_000,
    )
    db_conn.execute(
        "INSERT INTO price_overrides (hotel_id, room_type_id, stay_date, "
        "ask_price_override, min_allowed_override, expires_at) "
        "VALUES (%s, %s, '2026-09-01', 99_999, 5_000, %s)",
        (hotel_id, room_type_id, _NOW + timedelta(days=1)),
    )

    quote = compute_quote(
        db_conn, hotel_id, room_type_id, date(2026, 9, 1), date(2026, 9, 2), 1, _NOW
    )

    assert quote.nights[0].ask == 99_999
    assert quote.nights[0].min_allowed == 5_000


def test_compute_quote_expired_override_falls_back_to_normal_pricing(
    db_conn: psycopg.Connection[Any],
) -> None:
    hotel_id, room_type_id = seed_hotel_and_room_type(db_conn)
    _seed_default_season(db_conn)
    _seed_global_rule(db_conn, target_margin_bps=2000, min_profit_halalas=2000)
    seed_allotment_night(
        db_conn,
        hotel_id,
        room_type_id,
        date(2026, 9, 1),
        total_rooms=5,
        cost_per_night=10_000,
    )
    db_conn.execute(
        "INSERT INTO price_overrides (hotel_id, room_type_id, stay_date, "
        "ask_price_override, min_allowed_override, expires_at) "
        "VALUES (%s, %s, '2026-09-01', 99_999, 5_000, %s)",
        (hotel_id, room_type_id, _NOW - timedelta(days=1)),  # already expired
    )

    quote = compute_quote(
        db_conn, hotel_id, room_type_id, date(2026, 9, 1), date(2026, 9, 2), 1, _NOW
    )

    assert quote.nights[0].ask == 12_000
    assert quote.nights[0].min_allowed == 12_000


def test_compute_quote_records_a_quote_row(db_conn: psycopg.Connection[Any]) -> None:
    hotel_id, room_type_id = seed_hotel_and_room_type(db_conn)
    _seed_default_season(db_conn)
    _seed_global_rule(db_conn)
    seed_allotment_night(
        db_conn,
        hotel_id,
        room_type_id,
        date(2026, 9, 1),
        total_rooms=5,
        cost_per_night=10_000,
    )

    quote = compute_quote(
        db_conn,
        hotel_id,
        room_type_id,
        date(2026, 9, 1),
        date(2026, 9, 2),
        1,
        _NOW,
        customer_phone="+966500000000",
    )

    row = db_conn.execute(
        "SELECT hotel_id, room_type_id, ask_price_total, min_allowed_total, "
        "negotiation_open, customer_phone, jsonb_array_length(nights) "
        "FROM quotes WHERE id = %s",
        (quote.id,),
    ).fetchone()
    assert row is not None
    assert row == (
        hotel_id,
        room_type_id,
        quote.ask_price_total,
        quote.min_allowed_total,
        quote.negotiation_open,
        "+966500000000",
        1,
    )


def test_compute_quote_night_record_captures_the_full_computation(
    db_conn: psycopg.Connection[Any],
) -> None:
    """The audit-trail requirement: a computed night's stored record must
    be enough to answer "why was this priced this way" without guessing
    — occupancy at pricing time, which price_rules row supplied each
    field, the applied demand factor split into its two components, and
    the price at each step."""
    hotel_id, room_type_id = seed_hotel_and_room_type(db_conn)
    _seed_default_season(db_conn)
    margin_rule_id = seed_price_rule(
        db_conn,
        scope="global",
        target_margin_bps=2000,
        min_profit_by_lead_time=flat_min_profit(2000),
        demand_curve=flat_demand_curve(15_000),
    )
    seed_allotment_night(
        db_conn,
        hotel_id,
        room_type_id,
        date(2026, 9, 1),
        total_rooms=10,
        reserved=3,
        cost_per_night=10_000,
    )

    quote = compute_quote(
        db_conn, hotel_id, room_type_id, date(2026, 9, 1), date(2026, 9, 2), 1, _NOW
    )

    night = db_conn.execute(
        "SELECT nights -> 0 FROM quotes WHERE id = %s", (quote.id,)
    ).fetchone()
    assert night is not None
    record = night[0]

    assert record["override_applied"] is False
    assert record["season_id"] == quote.nights[0].season_id
    assert record["cost_per_night"] == 10_000
    assert record["occupancy"] == 0.3  # 3 reserved / 10 total
    assert record["target_margin_bps"] == 2000
    assert record["target_margin_rule_id"] == margin_rule_id
    assert record["demand_curve_rule_id"] == margin_rule_id
    assert record["min_profit_rule_id"] == margin_rule_id
    assert record["min_profit_halalas"] == 2000
    # cost=10000, margin=20% -> price_after_margin=12000
    assert record["price_after_margin"] == 12_000
    # flat_demand_curve(15_000) sets both axes to 1.5x -> combined 2.25x
    assert record["occupancy_multiplier_bps"] == 15_000
    assert record["lead_time_multiplier_bps"] == 15_000
    assert record["demand_factor_bps"] == 22_500
    # ask = price_after_margin(12000) * demand(22500bps) // 10000 = 27000
    assert record["ask"] == 27_000
    assert record["min_allowed"] == 12_000


def test_compute_quote_override_night_record_has_no_computation_detail(
    db_conn: psycopg.Connection[Any],
) -> None:
    hotel_id, room_type_id = seed_hotel_and_room_type(db_conn)
    _seed_default_season(db_conn)
    _seed_global_rule(db_conn)
    seed_allotment_night(
        db_conn,
        hotel_id,
        room_type_id,
        date(2026, 9, 1),
        total_rooms=5,
        cost_per_night=10_000,
    )
    db_conn.execute(
        "INSERT INTO price_overrides (hotel_id, room_type_id, stay_date, "
        "ask_price_override, min_allowed_override, expires_at) "
        "VALUES (%s, %s, '2026-09-01', 99_999, 5_000, %s)",
        (hotel_id, room_type_id, _NOW + timedelta(days=1)),
    )

    quote = compute_quote(
        db_conn, hotel_id, room_type_id, date(2026, 9, 1), date(2026, 9, 2), 1, _NOW
    )

    night = db_conn.execute(
        "SELECT nights -> 0 FROM quotes WHERE id = %s", (quote.id,)
    ).fetchone()
    assert night is not None
    record = night[0]

    assert record["override_applied"] is True
    assert record["ask"] == 99_999
    assert record["min_allowed"] == 5_000
    assert "cost_per_night" not in record
    assert "occupancy" not in record
    assert "target_margin_rule_id" not in record


def test_compute_quote_negotiation_open_when_far_from_check_in(
    db_conn: psycopg.Connection[Any],
) -> None:
    hotel_id, room_type_id = seed_hotel_and_room_type(db_conn)
    _seed_default_season(db_conn)
    _seed_global_rule(db_conn)
    check_in = (_NOW + timedelta(days=30)).date()
    seed_allotment_night(
        db_conn, hotel_id, room_type_id, check_in, total_rooms=5, cost_per_night=10_000
    )

    quote = compute_quote(
        db_conn, hotel_id, room_type_id, check_in, check_in + timedelta(days=1), 1, _NOW
    )

    assert quote.negotiation_open is True


def test_compute_quote_negotiation_closed_within_48_hours(
    db_conn: psycopg.Connection[Any],
) -> None:
    hotel_id, room_type_id = seed_hotel_and_room_type(db_conn)
    _seed_default_season(db_conn)
    _seed_global_rule(db_conn)
    check_in = _NOW.date()  # same day: well within 48h
    seed_allotment_night(
        db_conn, hotel_id, room_type_id, check_in, total_rooms=5, cost_per_night=10_000
    )

    quote = compute_quote(
        db_conn, hotel_id, room_type_id, check_in, check_in + timedelta(days=1), 1, _NOW
    )

    assert quote.negotiation_open is False


def test_compute_quote_raises_when_now_is_naive(
    db_conn: psycopg.Connection[Any],
) -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        compute_quote(
            db_conn,
            1,
            1,
            date(2026, 9, 1),
            date(2026, 9, 2),
            1,
            _NOW.replace(tzinfo=None),
        )


def test_compute_quote_raises_when_check_out_not_after_check_in(
    db_conn: psycopg.Connection[Any],
) -> None:
    with pytest.raises(ValueError, match="check_out must be after check_in"):
        compute_quote(db_conn, 1, 1, date(2026, 9, 2), date(2026, 9, 1), 1, _NOW)


def test_compute_quote_raises_when_rooms_not_positive(
    db_conn: psycopg.Connection[Any],
) -> None:
    with pytest.raises(ValueError, match="rooms must be positive"):
        compute_quote(db_conn, 1, 1, date(2026, 9, 1), date(2026, 9, 2), 0, _NOW)


def test_compute_quote_raises_when_check_in_is_in_the_past(
    db_conn: psycopg.Connection[Any],
) -> None:
    with pytest.raises(ValueError, match="check_in must not be in the past"):
        compute_quote(db_conn, 1, 1, date(2026, 7, 1), date(2026, 7, 2), 1, _NOW)


def test_compute_quote_raises_when_a_night_has_no_allotment(
    db_conn: psycopg.Connection[Any],
) -> None:
    hotel_id, room_type_id = seed_hotel_and_room_type(db_conn)
    _seed_default_season(db_conn)
    _seed_global_rule(db_conn)
    # No allotment seeded at all.

    with pytest.raises(AllotmentNotFoundError):
        compute_quote(
            db_conn, hotel_id, room_type_id, date(2026, 9, 1), date(2026, 9, 2), 1, _NOW
        )


def test_compute_quote_raises_when_floor_exceeds_ceiling(
    db_conn: psycopg.Connection[Any],
) -> None:
    """A misconfigured price rule — a profit floor no realistic ask_price
    could clear — must fail loudly with a clear exception, not silently
    insert an inconsistent quote (only caught downstream by the quotes
    table's own CHECK, whose raw message doesn't say which rule is wrong)."""
    hotel_id, room_type_id = seed_hotel_and_room_type(db_conn)
    _seed_default_season(db_conn)
    # cost=10000, 0% margin, 1.0x demand -> ask=10000; min_profit=50000 ->
    # min_allowed=60000, far above ask.
    seed_price_rule(
        db_conn,
        scope="global",
        target_margin_bps=0,
        min_profit_by_lead_time=flat_min_profit(50_000),
        demand_curve=flat_demand_curve(),
    )
    seed_allotment_night(
        db_conn,
        hotel_id,
        room_type_id,
        date(2026, 9, 1),
        total_rooms=5,
        cost_per_night=10_000,
    )

    with pytest.raises(InconsistentPriceConfigurationError):
        compute_quote(
            db_conn, hotel_id, room_type_id, date(2026, 9, 1), date(2026, 9, 2), 1, _NOW
        )

    # No partial quote was recorded.
    row = db_conn.execute("SELECT count(*) FROM quotes").fetchone()
    assert row == (0,)


def test_compute_quote_raises_when_no_price_rule_configured(
    db_conn: psycopg.Connection[Any],
) -> None:
    hotel_id, room_type_id = seed_hotel_and_room_type(db_conn)
    _seed_default_season(db_conn)
    seed_allotment_night(
        db_conn,
        hotel_id,
        room_type_id,
        date(2026, 9, 1),
        total_rooms=5,
        cost_per_night=10_000,
    )
    # No price_rules row at all.

    with pytest.raises(IncompletePriceRuleChainError):
        compute_quote(
            db_conn, hotel_id, room_type_id, date(2026, 9, 1), date(2026, 9, 2), 1, _NOW
        )


def test_compute_quote_ask_price_rounds_down(db_conn: psycopg.Connection[Any]) -> None:
    hotel_id, room_type_id = seed_hotel_and_room_type(db_conn)
    _seed_default_season(db_conn)
    # cost=1000, margin=0.07% (7bps), demand=1.0x -> true value 1000.7. A
    # round-half-up bug would give 1001; floor must give 1000.
    seed_price_rule(
        db_conn,
        scope="global",
        target_margin_bps=7,
        min_profit_by_lead_time=flat_min_profit(0),
        demand_curve=flat_demand_curve(),
    )
    seed_allotment_night(
        db_conn,
        hotel_id,
        room_type_id,
        date(2026, 9, 1),
        total_rooms=5,
        cost_per_night=1000,
    )

    quote = compute_quote(
        db_conn, hotel_id, room_type_id, date(2026, 9, 1), date(2026, 9, 2), 1, _NOW
    )

    assert quote.nights[0].ask == 1000
