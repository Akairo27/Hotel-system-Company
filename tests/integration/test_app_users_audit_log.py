"""Verifies migration 0017's audit trail for app_users.can_view_cost and
app_users.app_role changes against a real Postgres instance — see
CLAUDE.md rule 3: the DB constraint is the source of truth, not
application discipline.

admin_set_can_view_cost/admin_set_app_role are the only supported way to
change these columns; the AFTER UPDATE trigger they rely on rejects any
UPDATE that reaches the row without app.actor_id set first — including one
issued directly by service_role, which already holds a real UPDATE grant
on app_users (migration 0010) and could otherwise bypass both wrappers
entirely.
"""

from __future__ import annotations

from typing import Any

import psycopg
import pytest

pytestmark = pytest.mark.usefixtures("db_conn")


def _seed_user(
    conn: psycopg.Connection[Any], *, role: str, can_view_cost: bool = False
) -> str:
    row = conn.execute("INSERT INTO auth.users DEFAULT VALUES RETURNING id").fetchone()
    assert row is not None
    user_id = str(row[0])
    conn.execute(
        "INSERT INTO app_users (id, full_name, app_role, can_view_cost) "
        "VALUES (%s, 'Test User', %s, %s)",
        (user_id, role, can_view_cost),
    )
    return user_id


def test_admin_set_can_view_cost_updates_value_and_logs_entry(
    db_conn: psycopg.Connection[Any],
) -> None:
    admin_id = _seed_user(db_conn, role="admin")
    target_id = _seed_user(db_conn, role="sales", can_view_cost=False)

    db_conn.execute("SET SESSION AUTHORIZATION service_role")
    try:
        db_conn.execute(
            "SELECT admin_set_can_view_cost(%s, %s, %s)", (target_id, True, admin_id)
        )
    finally:
        db_conn.execute("RESET SESSION AUTHORIZATION")

    value = db_conn.execute(
        "SELECT can_view_cost FROM app_users WHERE id = %s", (target_id,)
    ).fetchone()
    assert value == (True,)

    audit_row = db_conn.execute(
        "SELECT column_name, old_value, new_value, changed_by::text FROM audit_log "
        "WHERE table_name = 'app_users' AND row_id = %s",
        (target_id,),
    ).fetchone()
    assert audit_row == ("can_view_cost", False, True, admin_id)


def test_admin_set_app_role_updates_value_and_logs_entry(
    db_conn: psycopg.Connection[Any],
) -> None:
    admin_id = _seed_user(db_conn, role="admin")
    target_id = _seed_user(db_conn, role="sales")

    db_conn.execute("SET SESSION AUTHORIZATION service_role")
    try:
        db_conn.execute(
            "SELECT admin_set_app_role(%s, %s, %s)", (target_id, "admin", admin_id)
        )
    finally:
        db_conn.execute("RESET SESSION AUTHORIZATION")

    value = db_conn.execute(
        "SELECT app_role FROM app_users WHERE id = %s", (target_id,)
    ).fetchone()
    assert value == ("admin",)

    audit_row = db_conn.execute(
        "SELECT column_name, old_value, new_value, changed_by::text FROM audit_log "
        "WHERE table_name = 'app_users' AND row_id = %s",
        (target_id,),
    ).fetchone()
    assert audit_row == ("app_role", "sales", "admin", admin_id)


def test_changing_both_columns_writes_two_audit_rows(
    db_conn: psycopg.Connection[Any],
) -> None:
    admin_id = _seed_user(db_conn, role="admin")
    target_id = _seed_user(db_conn, role="sales", can_view_cost=False)

    db_conn.execute("SET SESSION AUTHORIZATION service_role")
    try:
        db_conn.execute(
            "SELECT admin_set_can_view_cost(%s, %s, %s)", (target_id, True, admin_id)
        )
        db_conn.execute(
            "SELECT admin_set_app_role(%s, %s, %s)", (target_id, "admin", admin_id)
        )
    finally:
        db_conn.execute("RESET SESSION AUTHORIZATION")

    rows = db_conn.execute(
        "SELECT column_name FROM audit_log WHERE table_name = 'app_users' "
        "AND row_id = %s ORDER BY id",
        (target_id,),
    ).fetchall()
    assert [r[0] for r in rows] == ["can_view_cost", "app_role"]


def test_admin_set_can_view_cost_rejects_unknown_user(
    db_conn: psycopg.Connection[Any],
) -> None:
    admin_id = _seed_user(db_conn, role="admin")

    db_conn.execute("SET SESSION AUTHORIZATION service_role")
    try:
        with pytest.raises(psycopg.errors.RaiseException):
            db_conn.execute(
                "SELECT admin_set_can_view_cost(gen_random_uuid(), true, %s)",
                (admin_id,),
            )
    finally:
        db_conn.execute("RESET SESSION AUTHORIZATION")


def test_bypassing_wrapper_via_direct_service_role_update_is_rejected(
    db_conn: psycopg.Connection[Any],
) -> None:
    """service_role already holds a real UPDATE grant on app_users
    (migration 0010) — nothing at the GRANT layer stops a direct write.
    The trigger is what makes this fail instead of silently skipping the
    audit trail, which a wrapper function alone could never guarantee."""
    target_id = _seed_user(db_conn, role="sales", can_view_cost=False)

    db_conn.execute("SET SESSION AUTHORIZATION service_role")
    try:
        with pytest.raises(psycopg.errors.RaiseException, match=r"app\.actor_id"):
            db_conn.execute(
                "UPDATE app_users SET can_view_cost = true WHERE id = %s",
                (target_id,),
            )
    finally:
        db_conn.execute("RESET SESSION AUTHORIZATION")

    value = db_conn.execute(
        "SELECT can_view_cost FROM app_users WHERE id = %s", (target_id,)
    ).fetchone()
    assert value == (False,)


def test_deactivating_a_user_does_not_require_actor_id(
    db_conn: psycopg.Connection[Any],
) -> None:
    """The trigger's WHEN clause scopes to can_view_cost/app_role only — a
    plain service_role write to is_active (or full_name) must not start
    demanding app.actor_id it was never designed to need."""
    target_id = _seed_user(db_conn, role="sales")

    db_conn.execute("SET SESSION AUTHORIZATION service_role")
    try:
        db_conn.execute(
            "UPDATE app_users SET is_active = false WHERE id = %s", (target_id,)
        )
    finally:
        db_conn.execute("RESET SESSION AUTHORIZATION")

    count = db_conn.execute(
        "SELECT count(*) FROM audit_log WHERE table_name = 'app_users' AND row_id = %s",
        (target_id,),
    ).fetchone()
    assert count == (0,)
