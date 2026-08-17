"""Shared fixtures for tests that need a real Postgres instance.

TEST_DATABASE_URL must point at an already-existing, otherwise-empty
Postgres 17 database. If it is unset, every test depending on these
fixtures is skipped explicitly rather than faked with a mock connection.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import psycopg
import pytest
from psycopg import sql

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "db" / "migrations"

_ROLES_SQL = """
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'anon') THEN
        CREATE ROLE anon NOLOGIN;
    END IF;
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'authenticated') THEN
        CREATE ROLE authenticated NOLOGIN;
    END IF;
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'service_role') THEN
        CREATE ROLE service_role NOLOGIN BYPASSRLS;
    END IF;
END
$$;
"""

_TABLES_TO_TRUNCATE = (
    "quotes",
    "price_overrides",
    "price_rules",
    "holds",
    "room_night_inventory",
    "allotments",
    "seasons",
    "room_types",
    "hotels",
)


@pytest.fixture(scope="session")
def test_database_url() -> str:
    """The Postgres DSN for tests that require a real database connection."""
    dsn = os.environ.get("TEST_DATABASE_URL")
    if dsn is None:
        pytest.skip("TEST_DATABASE_URL not set — skipping real-database tests")
    return dsn


@pytest.fixture(scope="session")
def _schema(test_database_url: str) -> None:
    """Recreate the public schema and apply every migration, once per session.

    Postgres roles are cluster-wide, not per-database, so they are created
    if absent rather than by the schema reset.
    """
    with psycopg.connect(test_database_url, autocommit=True) as conn:
        conn.execute(_ROLES_SQL)
        conn.execute("DROP SCHEMA public CASCADE")
        conn.execute("CREATE SCHEMA public")
        for migration in sorted(MIGRATIONS_DIR.glob("*.sql")):
            conn.execute(migration.read_text(encoding="utf-8"))
    return None


@pytest.fixture
def db_conn(test_database_url: str, _schema: None) -> Iterator[psycopg.Connection[Any]]:
    """A fresh, truncated-clean autocommit connection at the same privilege
    level services/inventory holds through DATABASE_URL in production.

    Autocommit keeps a failed constraint from poisoning the rest of a test;
    code that needs an atomic multi-statement transaction opens one
    explicitly with ``conn.transaction()``. Tests that verify RLS actually
    denies an unprivileged role connect as anon/authenticated instead of
    using this fixture.
    """
    conn: psycopg.Connection[Any] = psycopg.connect(test_database_url, autocommit=True)
    table_list = sql.SQL(", ").join(sql.Identifier(t) for t in _TABLES_TO_TRUNCATE)
    truncate = sql.SQL("TRUNCATE {tables} RESTART IDENTITY CASCADE").format(
        tables=table_list
    )
    conn.execute(truncate)
    try:
        yield conn
    finally:
        conn.close()
