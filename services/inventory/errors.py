"""Exception types raised by services/inventory.

Every one of these maps to a specific, expected failure mode described in
ARCHITECTURE.md §6 — never a bare Exception, per CLAUDE.md §2.
"""

from __future__ import annotations


class InventoryError(Exception):
    """Base class for every exception this package raises."""


class AllotmentNotFoundError(InventoryError):
    """Raised when a requested date has no allotment for the given hotel
    and room type — the stay cannot be priced or held at all."""


class InsufficientInventoryError(InventoryError):
    """Raised when a hold would push a night past its available rooms.

    The database's inventory_never_oversold constraint is what actually
    prevents the oversell; this exception is the application-facing
    translation of that CheckViolation. See CLAUDE.md rule 3.
    """


class HoldNotFoundError(InventoryError):
    """Raised when an operation references a hold id that does not exist."""


class HoldAlreadyResolvedError(InventoryError):
    """Raised when confirming or releasing a hold that was already
    confirmed or released — the caller has stale state."""


class HoldExpiredError(InventoryError):
    """Raised when confirming a hold whose expiry has already passed."""
