"""Shared band-lookup logic for the jsonb band configs in price_rules —
min_profit_by_lead_time.bands, demand_curve.lead_time_bands, and
demand_curve.occupancy_bands all share this same [min, max) lookup shape.

Callers can trust a stored band list is well-formed (non-empty, sorted-
contiguous, fully covering its domain): db/migrations/0006_price_rules.sql
enforces that at save time via price_rules_is_valid_lead_time_bands and
price_rules_is_valid_occupancy_bands. This function does not re-validate
that shape — it only looks a value up within it.
"""

from __future__ import annotations

from typing import Any

from services.pricing.errors import NoMatchingBandError


def lookup_band_value(
    bands: list[dict[str, Any]],
    value: float,
    *,
    min_key: str,
    max_key: str,
    value_key: str,
) -> int:
    """Returns the value_key of the band whose [min_key, max_key) range
    contains value. A max_key of None means "no upper bound".

    Raises:
        NoMatchingBandError: no band covers value. For a validly-stored
            band list this means value itself is out of range (e.g. a
            negative lead time from a check_in in the past), not a
            malformed config — that's rejected before it can be stored.
    """
    for band in bands:
        band_min = band[min_key]
        band_max = band[max_key]
        if value >= band_min and (band_max is None or value < band_max):
            return int(band[value_key])
    raise NoMatchingBandError(
        f"no band covers {value} (min_key={min_key!r}, max_key={max_key!r}) "
        f"in {bands!r}"
    )
