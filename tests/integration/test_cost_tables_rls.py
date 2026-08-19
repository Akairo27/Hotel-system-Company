"""Trip-wire: the admin dashboard's `authenticated` role must never be able
to SELECT a cost-bearing table directly, until whichever PR grants it
access pairs that grant with column-level cost masking (see
ARCHITECTURE.md §8, "إخفاء عمود التكلفة"). This test carries no value in
proving today's protection — that's already covered by CLAUDE.md rule 3
(the REVOKE/GRANT is the source of truth) and the migrations' own
comments. Its value is failing loudly, right here, the day someone adds
`GRANT SELECT ... TO authenticated` on one of these tables without also
adding the masking view and a test for it — instead of that gap only
being discovered after PR B/D ships it.
"""

from __future__ import annotations

from typing import Any

import psycopg
import pytest
from psycopg import sql

pytestmark = pytest.mark.usefixtures("db_conn")

_COST_BEARING_TABLES = ("allotments", "quotes", "room_night_inventory")


@pytest.mark.parametrize("table", _COST_BEARING_TABLES)
def test_authenticated_cannot_select_cost_table(
    db_conn: psycopg.Connection[Any], table: str
) -> None:
    """authenticated has schema USAGE (migration 0010) but no table-level
    grant on any of these — permission denied at the table, not a missing
    schema. If this ever starts returning rows instead, cost data is
    reachable from the browser without column masking in place."""
    select = sql.SQL("SELECT * FROM {table}").format(table=sql.Identifier(table))
    db_conn.execute("SET SESSION AUTHORIZATION authenticated")
    try:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            db_conn.execute(select)
    finally:
        db_conn.execute("RESET SESSION AUTHORIZATION")


@pytest.mark.parametrize("table", _COST_BEARING_TABLES)
def test_anon_cannot_select_cost_table(
    db_conn: psycopg.Connection[Any], table: str
) -> None:
    """anon has no schema USAGE at all, so this fails one step earlier than
    the authenticated case — relation not found, not permission denied.
    Same outcome (zero rows reachable), different failure mode; see
    test_rls_denies_anon in test_app_users_and_roles_rls.py for why."""
    select = sql.SQL("SELECT * FROM {table}").format(table=sql.Identifier(table))
    db_conn.execute("SET SESSION AUTHORIZATION anon")
    try:
        with pytest.raises(psycopg.errors.UndefinedTable):
            db_conn.execute(select)
    finally:
        db_conn.execute("RESET SESSION AUTHORIZATION")
