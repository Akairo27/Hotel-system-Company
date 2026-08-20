"""Generates tests/price_rules_band_conformance_fixtures.json — ground
truth for admin/lib/priceRuleBands.ts's accept/reject decision, the same
role tests/generate_season_conformance_fixtures.py plays for
admin/lib/seasonCalendar.ts.

The two are not the same shape, for a reason specific to this fixture:
season conformance compares two *implementations* of the same logic
(Python's season_contains/resolve_season_id vs. TypeScript's port), so it
seeds scenarios into Postgres and lets the real Python functions compute
the expected answer. price_rules' band validity has no Python
implementation to compare against at all — services/pricing/bands.py
deliberately assumes a stored band list is well-formed and never
re-validates it (see that module's own docstring) — the *only* real
implementation is the SQL functions price_rules_is_valid_lead_time_bands
and price_rules_is_valid_occupancy_bands themselves
(db/migrations/0006_price_rules.sql). So this generator does not compare
two implementations; for each hand-authored candidate band list, it
queries those two SQL functions directly and records the boolean they
actually return — that boolean is the fixture's ground truth for
admin/lib/priceRuleBands.conformance.test.ts to check the TypeScript port
against.

That boolean is also the *only* thing the SQL functions can tell us:
CHECK constraints return true/false, never a reason. Each case below also
carries an `expectedDefect` field — which specific problem the case is
meant to exercise (a gap, an overlap, a missing zero start, ...) — but
that field is authored by hand when the case is written, not derived from
Postgres, and the conformance test checks it only against
admin/lib/priceRuleBands.ts's own classification, not against anything the
database says. Two independent sources of truth in one fixture: Postgres
for accept/reject, this file's author for the reason — see that test
file's own comment for why both matter (a validator that rejects for the
wrong reason passes an accept/reject-only check silently).

Every case here reuses band shapes already exercised directly against
Postgres in tests/integration/test_schema_constraints.py's
price_rules_min_profit_bands_* and price_rules_demand_curve_*_bands_*
tests — this file does not invent new malformed shapes, it re-expresses
already-trusted cases as a cross-language fixture, the same discipline
generate_season_conformance_fixtures.py's own docstring describes.

Requires a real Postgres instance. Run manually and commit the result
whenever a case changes:

    TEST_DATABASE_URL=postgresql://postgres:postgres@localhost:5432/hotel_sales_test \
        uv run python -m tests.generate_price_rules_band_conformance_fixtures
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import psycopg
from psycopg.types.json import Json

from tests.conftest import _AUTH_SCHEMA_SQL, _ROLES_SQL, MIGRATIONS_DIR

OUTPUT_PATH = (
    Path(__file__).resolve().parent / "price_rules_band_conformance_fixtures.json"
)


@dataclass(frozen=True)
class Case:
    name: str
    # "lead_time" queries price_rules_is_valid_lead_time_bands(bands, value_key);
    # "occupancy" queries price_rules_is_valid_occupancy_bands(bands).
    kind: str
    bands: Any
    expected_defect: str
    value_key: str = "min_profit_halalas"


CASES = [
    # --- lead_time: valid ---------------------------------------------
    Case(
        "lead_time_valid_single_open_ended_band",
        "lead_time",
        [{"min_lead_days": 0, "max_lead_days": None, "min_profit_halalas": 1000}],
        "valid",
    ),
    Case(
        "lead_time_valid_two_contiguous_bands",
        "lead_time",
        [
            {"min_lead_days": 0, "max_lead_days": 5, "min_profit_halalas": 5000},
            {"min_lead_days": 5, "max_lead_days": None, "min_profit_halalas": 2000},
        ],
        "valid",
    ),
    # --- lead_time: invalid ---------------------------------------------
    # Same shape as test_schema_constraints.py's
    # test_price_rules_min_profit_bands_reject_a_gap.
    Case(
        "lead_time_gap_between_bands",
        "lead_time",
        [
            {"min_lead_days": 0, "max_lead_days": 5, "min_profit_halalas": 5000},
            {"min_lead_days": 10, "max_lead_days": None, "min_profit_halalas": 2000},
        ],
        "gap",
    ),
    # Same shape as ..._reject_an_overlap.
    Case(
        "lead_time_overlap_between_bands",
        "lead_time",
        [
            {"min_lead_days": 0, "max_lead_days": 10, "min_profit_halalas": 5000},
            {"min_lead_days": 5, "max_lead_days": None, "min_profit_halalas": 2000},
        ],
        "overlap",
    ),
    # Same shape as ..._reject_missing_zero_start.
    Case(
        "lead_time_does_not_start_at_zero",
        "lead_time",
        [{"min_lead_days": 1, "max_lead_days": None, "min_profit_halalas": 5000}],
        "missing_zero_start",
    ),
    # Same shape as ..._reject_missing_open_end.
    Case(
        "lead_time_no_open_ended_band",
        "lead_time",
        [{"min_lead_days": 0, "max_lead_days": 30, "min_profit_halalas": 5000}],
        "missing_open_end",
    ),
    # Same shape as ..._reject_negative_profit.
    Case(
        "lead_time_negative_value",
        "lead_time",
        [{"min_lead_days": 0, "max_lead_days": None, "min_profit_halalas": -1}],
        "negative_value",
    ),
    Case("lead_time_empty_array", "lead_time", [], "missing_key"),
    Case(
        "lead_time_band_missing_a_key",
        "lead_time",
        [{"min_lead_days": 0, "min_profit_halalas": 1000}],
        "missing_key",
    ),
    Case(
        "lead_time_band_wrong_type",
        "lead_time",
        [{"min_lead_days": 0, "max_lead_days": None, "min_profit_halalas": "a lot"}],
        "wrong_type",
    ),
    # --- occupancy: valid ---------------------------------------------
    Case(
        "occupancy_valid_single_full_range_band",
        "occupancy",
        [{"min": 0, "max": 1, "multiplier_bps": 10000}],
        "valid",
    ),
    Case(
        "occupancy_valid_two_contiguous_bands",
        "occupancy",
        [
            {"min": 0, "max": 0.5, "multiplier_bps": 10000},
            {"min": 0.5, "max": 1, "multiplier_bps": 15000},
        ],
        "valid",
    ),
    # --- occupancy: invalid ---------------------------------------------
    # Same shape as ..._occupancy_bands_reject_a_gap.
    Case(
        "occupancy_gap_between_bands",
        "occupancy",
        [
            {"min": 0, "max": 0.5, "multiplier_bps": 10000},
            {"min": 0.6, "max": 1, "multiplier_bps": 12500},
        ],
        "gap",
    ),
    Case(
        "occupancy_overlap_between_bands",
        "occupancy",
        [
            {"min": 0, "max": 0.6, "multiplier_bps": 10000},
            {"min": 0.5, "max": 1, "multiplier_bps": 12500},
        ],
        "overlap",
    ),
    Case(
        "occupancy_does_not_start_at_zero",
        "occupancy",
        [{"min": 0.1, "max": 1, "multiplier_bps": 10000}],
        "missing_zero_start",
    ),
    # Same shape as ..._occupancy_bands_reject_unbounded_end.
    Case(
        "occupancy_does_not_reach_one",
        "occupancy",
        [{"min": 0, "max": 0.9, "multiplier_bps": 10000}],
        "missing_open_end",
    ),
    Case(
        "occupancy_negative_value",
        "occupancy",
        [{"min": -0.1, "max": 1, "multiplier_bps": 10000}],
        "negative_value",
    ),
    Case("occupancy_empty_array", "occupancy", [], "missing_key"),
    Case(
        "occupancy_band_missing_a_key",
        "occupancy",
        [{"min": 0, "max": 1}],
        "missing_key",
    ),
    Case(
        "occupancy_band_wrong_type",
        "occupancy",
        [{"min": 0, "max": "all of it", "multiplier_bps": 10000}],
        "wrong_type",
    ),
]


def _reset_schema(conn: psycopg.Connection[Any]) -> None:
    conn.execute(_ROLES_SQL)
    conn.execute(_AUTH_SCHEMA_SQL)
    conn.execute("DROP SCHEMA public CASCADE")
    conn.execute("CREATE SCHEMA public")
    for migration in sorted(MIGRATIONS_DIR.glob("*.sql")):
        conn.execute(migration.read_text(encoding="utf-8"))


def _query_is_valid(conn: psycopg.Connection[Any], case: Case) -> bool:
    if case.kind == "lead_time":
        row = conn.execute(
            "SELECT price_rules_is_valid_lead_time_bands(%s::jsonb, %s)",
            (Json(case.bands), case.value_key),
        ).fetchone()
    elif case.kind == "occupancy":
        row = conn.execute(
            "SELECT price_rules_is_valid_occupancy_bands(%s::jsonb)",
            (Json(case.bands),),
        ).fetchone()
    else:
        raise ValueError(f"unknown case kind: {case.kind!r}")
    assert row is not None
    return bool(row[0])


def build_fixtures(conn: psycopg.Connection[Any]) -> dict[str, Any]:
    cases = []
    for case in CASES:
        expected_valid = _query_is_valid(conn, case)
        # A case authored as "valid" must actually be accepted by
        # Postgres, and vice versa -- catches a typo in this file's own
        # CASES list before it ships as a wrong ground truth.
        if (case.expected_defect == "valid") != expected_valid:
            raise AssertionError(
                f"case {case.name!r}: expectedDefect={case.expected_defect!r} but "
                f"Postgres returned valid={expected_valid}"
            )
        cases.append(
            {
                "name": case.name,
                "kind": case.kind,
                "bands": case.bands,
                "valueKey": case.value_key,
                "expectedValid": expected_valid,
                "expectedDefect": case.expected_defect,
            }
        )
    return {"cases": cases}


if __name__ == "__main__":
    dsn = os.environ["TEST_DATABASE_URL"]
    with psycopg.connect(dsn, autocommit=True) as connection:
        _reset_schema(connection)
        fixtures = build_fixtures(connection)
    OUTPUT_PATH.write_text(
        json.dumps(fixtures, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
