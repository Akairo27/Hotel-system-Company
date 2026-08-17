"""Exception types raised by services/pricing.

Mirrors services/inventory/errors.py's pattern — every exception maps to
a specific, expected failure mode described in ARCHITECTURE.md, never a
bare Exception, per CLAUDE.md §2.
"""

from __future__ import annotations


class PricingError(Exception):
    """Base class for every exception this package raises."""


class NoApplicableSeasonError(PricingError):
    """Raised when a date matches no season and no default season exists
    to fall back to.

    ARCHITECTURE.md requires exactly one default season to always exist
    ("لا يمكن أن يوجد تاريخ بلا سعر") — this is the failure mode for when
    that guarantee has been violated (e.g. an empty seasons table), not
    something normal resolution is expected to hit.
    """
