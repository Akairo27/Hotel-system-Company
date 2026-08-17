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


class FullPaymentRequiredError(InventoryError):
    """Raised when confirming a hold that requires full payment up front
    (ARCHITECTURE.md §6's last-minute hold window) but the caller has not
    indicated payment was received in full.

    This must route to a human escalation, never a silent auto-confirm —
    see CLAUDE.md rule 10 on anything touching booking confirmation.
    """


class RoomNightCountMismatchError(InventoryError):
    """Raised when a held/reserved adjustment affects a different number of
    room_night_inventory rows than the stay's expected night count.

    A mismatch means part of the range has no inventory row to absorb the
    adjustment, which would otherwise let held or reserved drift out of
    sync with the rooms actually on hold — silently, since the UPDATE
    itself does not fail. See CLAUDE.md rule 3: application-level checks
    exist to fail fast and loud, not to be skipped.
    """


class DuplicateHoldRequestError(InventoryError):
    """Raised when two hold requests race on the same idempotency_key and
    both reach the INSERT — the database's unique constraint on
    holds.idempotency_key rejected the second one.

    The caller should look up the existing hold by idempotency_key rather
    than retry blindly; a duplicate WhatsApp message_id must never produce
    a second hold.
    """
