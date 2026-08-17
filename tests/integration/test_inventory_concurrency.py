"""The mandatory phase 1 concurrency tests from PLAN.md: real, separate
database connections racing each other — no mocks. This is the actual
guarantee ARCHITECTURE.md §6 and the inventory_never_oversold constraint
exist to provide; a test using one connection or a mocked lock would not
prove anything about it.
"""

from __future__ import annotations

import threading
from datetime import UTC, date, datetime
from typing import Any

import psycopg
import pytest

from services.inventory.errors import (
    DuplicateHoldRequestError,
    HoldAlreadyResolvedError,
    InsufficientInventoryError,
)
from services.inventory.operations import confirm_hold, create_hold, release_hold
from tests.integration._seed import seed_allotment_nights, seed_hotel_and_room_type

pytestmark = pytest.mark.usefixtures("db_conn")

_NOW = datetime(2026, 6, 1, tzinfo=UTC)
_CHECK_IN = date(2026, 7, 1)
_CHECK_OUT = date(2026, 7, 2)
_THREAD_JOIN_TIMEOUT_S = 10


def _room_night_state(
    conn: psycopg.Connection[Any], hotel_id: int, room_type_id: int
) -> tuple[int, int]:
    row = conn.execute(
        "SELECT held, reserved FROM room_night_inventory rni "
        "JOIN allotments a ON a.id = rni.allotment_id "
        "WHERE a.hotel_id = %s AND a.room_type_id = %s",
        (hotel_id, room_type_id),
    ).fetchone()
    assert row is not None
    held, reserved = row
    return int(held), int(reserved)


def test_concurrent_holds_on_last_room_one_succeeds_one_fails(
    db_conn: psycopg.Connection[Any], test_database_url: str
) -> None:
    hotel_id, room_type_id = seed_hotel_and_room_type(db_conn)
    seed_allotment_nights(
        db_conn, hotel_id, room_type_id, _CHECK_IN, nights=1, total_rooms=1
    )

    barrier = threading.Barrier(2)
    outcomes: dict[int, Any] = {}

    def attempt(thread_id: int) -> None:
        with psycopg.connect(test_database_url) as conn:
            barrier.wait()
            try:
                outcomes[thread_id] = create_hold(
                    conn,
                    hotel_id,
                    room_type_id,
                    _CHECK_IN,
                    _CHECK_OUT,
                    1,
                    _NOW,
                    idempotency_key=f"last-room-{thread_id}",
                )
            except Exception as exc:
                outcomes[thread_id] = exc

    threads = [threading.Thread(target=attempt, args=(i,)) for i in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=_THREAD_JOIN_TIMEOUT_S)

    results = list(outcomes.values())
    successes = [r for r in results if isinstance(r, int)]
    failures = [r for r in results if isinstance(r, InsufficientInventoryError)]

    assert len(successes) == 1, f"expected exactly one success, got: {results}"
    assert len(failures) == 1, f"expected exactly one clean failure, got: {results}"

    held, reserved = _room_night_state(db_conn, hotel_id, room_type_id)
    assert held == 1
    assert reserved == 0


def test_concurrent_holds_on_last_room_is_reproducible(
    db_conn: psycopg.Connection[Any], test_database_url: str
) -> None:
    """Runs the same race multiple times in a row. A flaky concurrency
    guarantee is not a guarantee — see PLAN.md's requirement to test the
    gates before trusting them.
    """
    for round_number in range(5):
        check_in = date(2026, 8, 1 + round_number)
        check_out = date(2026, 8, 2 + round_number)
        hotel_id, room_type_id = seed_hotel_and_room_type(db_conn)
        seed_allotment_nights(
            db_conn, hotel_id, room_type_id, check_in, nights=1, total_rooms=1
        )

        barrier = threading.Barrier(2)
        outcomes: dict[int, Any] = {}

        def attempt(
            thread_id: int,
            hotel_id: int = hotel_id,
            room_type_id: int = room_type_id,
            check_in: date = check_in,
            check_out: date = check_out,
            round_number: int = round_number,
            barrier: threading.Barrier = barrier,
            outcomes: dict[int, Any] = outcomes,
        ) -> None:
            with psycopg.connect(test_database_url) as conn:
                barrier.wait()
                try:
                    outcomes[thread_id] = create_hold(
                        conn,
                        hotel_id,
                        room_type_id,
                        check_in,
                        check_out,
                        1,
                        _NOW,
                        idempotency_key=f"reproducible-{round_number}-{thread_id}",
                    )
                except Exception as exc:
                    outcomes[thread_id] = exc

        threads = [threading.Thread(target=attempt, args=(i,)) for i in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=_THREAD_JOIN_TIMEOUT_S)

        results = list(outcomes.values())
        successes = [r for r in results if isinstance(r, int)]
        failures = [r for r in results if isinstance(r, InsufficientInventoryError)]
        assert len(successes) == 1, f"round {round_number}: {results}"
        assert len(failures) == 1, f"round {round_number}: {results}"


def test_concurrent_release_of_same_hold_happens_exactly_once(
    db_conn: psycopg.Connection[Any], test_database_url: str
) -> None:
    hotel_id, room_type_id = seed_hotel_and_room_type(db_conn)
    seed_allotment_nights(
        db_conn, hotel_id, room_type_id, _CHECK_IN, nights=1, total_rooms=5
    )
    hold_id = create_hold(
        db_conn,
        hotel_id,
        room_type_id,
        _CHECK_IN,
        _CHECK_OUT,
        3,
        _NOW,
        idempotency_key="release-once",
    )

    barrier = threading.Barrier(2)
    outcomes: dict[int, Any] = {}

    def attempt(thread_id: int) -> None:
        with psycopg.connect(test_database_url) as conn:
            barrier.wait()
            try:
                release_hold(conn, hold_id, _NOW)
                outcomes[thread_id] = "released"
            except Exception as exc:
                outcomes[thread_id] = exc

    threads = [threading.Thread(target=attempt, args=(i,)) for i in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=_THREAD_JOIN_TIMEOUT_S)

    results = list(outcomes.values())
    released = [r for r in results if r == "released"]
    already_resolved = [r for r in results if isinstance(r, HoldAlreadyResolvedError)]

    assert len(released) == 1, f"expected exactly one release, got: {results}"
    assert len(already_resolved) == 1, f"expected exactly one rejection, got: {results}"

    held, reserved = _room_night_state(db_conn, hotel_id, room_type_id)
    assert held == 0  # released exactly once, never decremented into negative
    assert reserved == 0


def test_concurrent_confirmations_on_overlapping_ranges_both_succeed(
    db_conn: psycopg.Connection[Any], test_database_url: str
) -> None:
    """Two holds on the same hotel/room type with overlapping date ranges,
    confirmed from two separate connections at the same time. Before this
    fix, confirm_hold adjusted room_night_inventory with a plain UPDATE and
    never locked nights in a fixed order first, so its lock-acquisition
    order was whatever the query planner picked — inconsistent with
    create_hold's ascending stay_date order, and a candidate for a
    deadlock under contention. confirm_hold now locks nights via the same
    ordered _lock_nights_for_update create_hold uses, so both confirmations
    must complete without either transaction being aborted for a deadlock.
    """
    hotel_id, room_type_id = seed_hotel_and_room_type(db_conn)
    base = date(2026, 7, 1)
    seed_allotment_nights(
        db_conn, hotel_id, room_type_id, base, nights=6, total_rooms=4
    )
    hold_a = create_hold(
        db_conn,
        hotel_id,
        room_type_id,
        base,
        date(2026, 7, 5),
        2,
        _NOW,
        idempotency_key="overlap-a",
    )  # nights 1-4
    hold_b = create_hold(
        db_conn,
        hotel_id,
        room_type_id,
        date(2026, 7, 3),
        date(2026, 7, 7),
        2,
        _NOW,
        idempotency_key="overlap-b",
    )  # nights 3-6, overlaps hold_a on nights 3-4

    barrier = threading.Barrier(2)
    outcomes: dict[str, Any] = {}

    def confirm(name: str, hold_id: int) -> None:
        with psycopg.connect(test_database_url) as conn:
            barrier.wait()
            try:
                confirm_hold(conn, hold_id, _NOW, payment_received_in_full=True)
                outcomes[name] = "confirmed"
            except Exception as exc:
                outcomes[name] = exc

    threads = [
        threading.Thread(target=confirm, args=("a", hold_a)),
        threading.Thread(target=confirm, args=("b", hold_b)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=_THREAD_JOIN_TIMEOUT_S)

    results = [outcomes.get("a"), outcomes.get("b")]
    assert results == ["confirmed", "confirmed"], f"expected both to succeed: {results}"

    rows = db_conn.execute(
        "SELECT rni.stay_date, held, reserved FROM room_night_inventory rni "
        "JOIN allotments a ON a.id = rni.allotment_id "
        "WHERE a.hotel_id = %s AND a.room_type_id = %s ORDER BY rni.stay_date",
        (hotel_id, room_type_id),
    ).fetchall()
    assert [r[1] for r in rows] == [0, 0, 0, 0, 0, 0]  # nothing left held
    # Nights 3-4 (index 2, 3) carry both holds' rooms; the rest carry one.
    assert [r[2] for r in rows] == [2, 2, 4, 4, 2, 2]


def test_concurrent_create_hold_with_same_idempotency_key_one_wins(
    db_conn: psycopg.Connection[Any], test_database_url: str
) -> None:
    """A genuine race on the same idempotency_key — not the sequential
    retry case covered in test_inventory_operations.py. The unique
    constraint on holds.idempotency_key is the actual authority here; the
    application-level pre-check cannot see the other transaction's
    uncommitted insert.
    """
    hotel_id, room_type_id = seed_hotel_and_room_type(db_conn)
    seed_allotment_nights(
        db_conn, hotel_id, room_type_id, _CHECK_IN, nights=1, total_rooms=5
    )

    barrier = threading.Barrier(2)
    outcomes: dict[int, Any] = {}

    def attempt(thread_id: int) -> None:
        with psycopg.connect(test_database_url) as conn:
            barrier.wait()
            try:
                outcomes[thread_id] = create_hold(
                    conn,
                    hotel_id,
                    room_type_id,
                    _CHECK_IN,
                    _CHECK_OUT,
                    1,
                    _NOW,
                    idempotency_key="racing-key",
                )
            except Exception as exc:
                outcomes[thread_id] = exc

    threads = [threading.Thread(target=attempt, args=(i,)) for i in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=_THREAD_JOIN_TIMEOUT_S)

    results = list(outcomes.values())
    successes = [r for r in results if isinstance(r, int)]
    duplicates = [r for r in results if isinstance(r, DuplicateHoldRequestError)]

    assert len(successes) == 1, f"expected exactly one success, got: {results}"
    assert len(duplicates) == 1, f"expected exactly one duplicate error, got: {results}"

    held, reserved = _room_night_state(db_conn, hotel_id, room_type_id)
    assert held == 1  # the losing transaction's held increment was rolled back
    assert reserved == 0
