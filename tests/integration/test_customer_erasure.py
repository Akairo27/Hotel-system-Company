"""Verifies migration 0013's one narrow exception to quotes' append-only
guarantee: quotes_erase_customer_phone(), a SECURITY DEFINER function that
can only ever set customer_phone to NULL for rows matching a given phone
number — never any other column, never a row deletion.

service_role's direct UPDATE/DELETE rejection on quotes and audit_log is
already covered by test_schema_constraints.py's
test_quotes_is_append_only_*_rejected and test_audit_log_rls.py's
test_audit_log_is_append_only_*_rejected — not duplicated here.
"""

from __future__ import annotations

from typing import Any

import psycopg
import pytest

from tests.integration._seed import seed_hotel_and_room_type

pytestmark = pytest.mark.usefixtures("db_conn")

# Same minimal, structurally valid quotes.nights shape as
# test_schema_constraints.py's _VALID_QUOTE_NIGHTS — one override-applied
# night, no computation-detail fields required. See
# db/migrations/0009_quotes_nights_audit.sql.
_VALID_QUOTE_NIGHTS = (
    '[{"date": "2026-09-01", "season_id": 1, "ask": 20000, "min_allowed": 10000, '
    '"override_applied": true}]'
)


def _seed_quote(db_conn: psycopg.Connection[Any], *, customer_phone: str) -> int:
    hotel_id, room_type_id = seed_hotel_and_room_type(db_conn)
    row = db_conn.execute(
        "INSERT INTO quotes (hotel_id, room_type_id, check_in, check_out, rooms, "
        "ask_price_total, min_allowed_total, nights, negotiation_open, "
        "customer_phone) "
        "VALUES (%s, %s, '2026-09-01', '2026-09-02', 1, 20000, 10000, %s::jsonb, "
        "true, %s) RETURNING id",
        (hotel_id, room_type_id, _VALID_QUOTE_NIGHTS, customer_phone),
    ).fetchone()
    assert row is not None
    return int(row[0])


def test_erase_customer_phone_zeroes_only_the_matching_phone(
    db_conn: psycopg.Connection[Any],
) -> None:
    """The pricing record itself — ask/min_allowed/nights, the numbers
    CLAUDE.md rule 3 cares about — must survive untouched. A second
    customer's quote must survive untouched too: the function targets by
    exact phone match, not a blanket wipe."""
    target_id = _seed_quote(db_conn, customer_phone="+966500000001")
    other_id = _seed_quote(db_conn, customer_phone="+966500000002")

    db_conn.execute("SET SESSION AUTHORIZATION service_role")
    try:
        erased = db_conn.execute(
            "SELECT quotes_erase_customer_phone(%s)", ("+966500000001",)
        ).fetchone()
    finally:
        db_conn.execute("RESET SESSION AUTHORIZATION")

    assert erased == (1,)
    rows = db_conn.execute(
        "SELECT id, customer_phone, ask_price_total, min_allowed_total, nights "
        "FROM quotes WHERE id IN (%s, %s) ORDER BY id",
        (target_id, other_id),
    ).fetchall()
    by_id = {row[0]: row[1:] for row in rows}
    assert by_id[target_id][0] is None
    assert by_id[target_id][1:] == (
        20000,
        10000,
        [
            {
                "date": "2026-09-01",
                "season_id": 1,
                "ask": 20000,
                "min_allowed": 10000,
                "override_applied": True,
            }
        ],
    )
    assert by_id[other_id][0] == "+966500000002"


def test_erase_customer_phone_matching_nothing_is_a_safe_no_op(
    db_conn: psycopg.Connection[Any],
) -> None:
    quote_id = _seed_quote(db_conn, customer_phone="+966500000001")

    db_conn.execute("SET SESSION AUTHORIZATION service_role")
    try:
        erased = db_conn.execute(
            "SELECT quotes_erase_customer_phone(%s)", ("+966599999999",)
        ).fetchone()
    finally:
        db_conn.execute("RESET SESSION AUTHORIZATION")

    assert erased == (0,)
    phone = db_conn.execute(
        "SELECT customer_phone FROM quotes WHERE id = %s", (quote_id,)
    ).fetchone()
    assert phone == ("+966500000001",)


def test_authenticated_cannot_call_erase_customer_phone(
    db_conn: psycopg.Connection[Any],
) -> None:
    """Trip-wire, same spirit as test_cost_tables_rls.py: migration
    0012's global function-default lockdown already denies this by
    default — this fails loudly the day a future migration grants
    EXECUTE on this specific function too broadly. authenticated has
    schema USAGE (migration 0010), so this is a real permission denial,
    not a missing-schema error."""
    db_conn.execute("SET SESSION AUTHORIZATION authenticated")
    try:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            db_conn.execute(
                "SELECT quotes_erase_customer_phone(%s)", ("+966500000001",)
            )
    finally:
        db_conn.execute("RESET SESSION AUTHORIZATION")


def test_anon_cannot_call_erase_customer_phone(
    db_conn: psycopg.Connection[Any],
) -> None:
    """anon has no schema USAGE at all locally, so this fails one step
    earlier than the authenticated case — same local-vs-real-Supabase
    divergence documented in test_default_privileges_lockdown.py; the
    security outcome (zero access), not the error code, is what matters."""
    db_conn.execute("SET SESSION AUTHORIZATION anon")
    try:
        with pytest.raises(psycopg.errors.UndefinedFunction):
            db_conn.execute(
                "SELECT quotes_erase_customer_phone(%s)", ("+966500000001",)
            )
    finally:
        db_conn.execute("RESET SESSION AUTHORIZATION")
