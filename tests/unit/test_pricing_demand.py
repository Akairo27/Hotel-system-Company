"""services/pricing/demand.py's compute_demand_factor_bps — pure given a
demand_curve dict and (occupancy, lead_days) values. compute_occupancy
itself needs a database (room_night_inventory) and is tested in
tests/integration/test_pricing_demand.py.
"""

from __future__ import annotations

from services.pricing.demand import compute_demand_factor_bps

_DEMAND_CURVE = {
    "occupancy_bands": [
        {"min": 0.0, "max": 0.5, "multiplier_bps": 10_000},
        {"min": 0.5, "max": 1.0, "multiplier_bps": 15_000},
    ],
    "lead_time_bands": [
        {"min_lead_days": 0, "max_lead_days": 3, "multiplier_bps": 12_000},
        {"min_lead_days": 3, "max_lead_days": None, "multiplier_bps": 10_000},
    ],
}


def test_compute_demand_factor_combines_low_occupancy_and_far_lead_time() -> None:
    # 1.0x occupancy multiplier * 1.0x lead-time multiplier = 1.0x
    assert compute_demand_factor_bps(_DEMAND_CURVE, 0.2, 10) == 10_000


def test_compute_demand_factor_combines_high_occupancy_and_near_lead_time() -> None:
    # 1.5x occupancy multiplier * 1.2x lead-time multiplier = 1.8x
    assert compute_demand_factor_bps(_DEMAND_CURVE, 0.8, 1) == 18_000


def test_compute_demand_factor_rounds_down() -> None:
    curve = {
        "occupancy_bands": [{"min": 0, "max": 1, "multiplier_bps": 15_000}],
        "lead_time_bands": [
            {"min_lead_days": 0, "max_lead_days": None, "multiplier_bps": 333}
        ],
    }
    # true value: 15000 * 333 / 10000 = 499.5 -- must floor to 499, not round to 500.
    assert compute_demand_factor_bps(curve, 0.1, 0) == 499
