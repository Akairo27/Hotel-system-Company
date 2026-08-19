"""Verifies audit_log is append-only and admin-read-only against a real
Postgres instance — see CLAUDE.md rule 3: the DB constraint is the source
of truth, not application discipline.

Needs docs/phase-3-pr-a/pending-migrations/0010_app_users_and_roles.sql and
0011_audit_log.sql promoted to db/migrations/ first — see
docs/phase-3-pr-a/README.md.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import psycopg
import pytest

pytestmark = pytest.mark.usefixtures("db_conn")


def _seed_user(conn: psycopg.Connection[Any], *, role: str = "sales") -> str:
    row = conn.execute("INSERT INTO auth.users DEFAULT VALUES RETURNING id").fetchone()
    assert row is not None
    user_id = str(row[0])
    conn.execute(
        "INSERT INTO app_users (id, full_name, app_role) VALUES (%s, 'Test User', %s)",
        (user_id, role),
    )
    return user_id


def _seed_audit_entry(conn: psycopg.Connection[Any], changed_by: str) -> int:
    row = conn.execute(
        "INSERT INTO audit_log (table_name, row_id, column_name, old_value, "
        "new_value, changed_by) "
        "VALUES ('allotments', '1', 'cost_per_night', '10000'::jsonb, "
        "'11000'::jsonb, %s) RETURNING id",
        (changed_by,),
    ).fetchone()
    assert row is not None
    return int(row[0])


def test_admin_can_select_audit_log(
    db_conn: psycopg.Connection[Any], sign_in_as: Callable[[str], None]
) -> None:
    admin_id = _seed_user(db_conn, role="admin")
    _seed_audit_entry(db_conn, admin_id)
    sign_in_as(admin_id)

    rows = db_conn.execute("SELECT * FROM audit_log").fetchall()
    assert len(rows) == 1


def test_sales_user_cannot_select_audit_log(
    db_conn: psycopg.Connection[Any], sign_in_as: Callable[[str], None]
) -> None:
    admin_id = _seed_user(db_conn, role="admin")
    _seed_audit_entry(db_conn, admin_id)
    sales_id = _seed_user(db_conn, role="sales")
    sign_in_as(sales_id)

    rows = db_conn.execute("SELECT * FROM audit_log").fetchall()
    assert rows == []


def test_anon_cannot_select_audit_log(db_conn: psycopg.Connection[Any]) -> None:
    """anon gets no grant on audit_log at all, same as app_users — see
    test_rls_denies_anon in test_app_users_and_roles_rls.py for why this
    is UndefinedTable rather than a table-level permission error."""
    admin_id = _seed_user(db_conn, role="admin")
    _seed_audit_entry(db_conn, admin_id)

    db_conn.execute("SET SESSION AUTHORIZATION anon")
    try:
        with pytest.raises(psycopg.errors.UndefinedTable):
            db_conn.execute("SELECT * FROM audit_log").fetchall()
    finally:
        db_conn.execute("RESET SESSION AUTHORIZATION")


def test_audit_log_is_append_only_update_rejected(
    db_conn: psycopg.Connection[Any],
) -> None:
    admin_id = _seed_user(db_conn, role="admin")
    entry_id = _seed_audit_entry(db_conn, admin_id)

    db_conn.execute("SET SESSION AUTHORIZATION service_role")
    try:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            db_conn.execute(
                "UPDATE audit_log SET new_value = '99'::jsonb WHERE id = %s",
                (entry_id,),
            )
    finally:
        db_conn.execute("RESET SESSION AUTHORIZATION")


def test_audit_log_is_append_only_delete_rejected(
    db_conn: psycopg.Connection[Any],
) -> None:
    admin_id = _seed_user(db_conn, role="admin")
    entry_id = _seed_audit_entry(db_conn, admin_id)

    db_conn.execute("SET SESSION AUTHORIZATION service_role")
    try:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            db_conn.execute("DELETE FROM audit_log WHERE id = %s", (entry_id,))
    finally:
        db_conn.execute("RESET SESSION AUTHORIZATION")


def test_audit_log_changed_by_must_reference_a_real_app_user(
    db_conn: psycopg.Connection[Any],
) -> None:
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        db_conn.execute(
            "INSERT INTO audit_log (table_name, row_id, column_name, "
            "new_value, changed_by) "
            "VALUES ('allotments', '1', 'cost_per_night', '11000'::jsonb, "
            "gen_random_uuid())"
        )
