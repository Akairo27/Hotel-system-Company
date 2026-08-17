-- Pricing rules, resolved field by field through the phase-2 inheritance
-- chain: global -> season -> hotel -> room_type (see
-- services/pricing/rules.py, phase 2 PR B). A more specific scope's row
-- only overrides the fields it sets; a NULL field falls through to the
-- next less specific matching row for that field alone.
--
-- scope_id is a polymorphic reference (season/hotel/room_type id
-- depending on scope), matching ARCHITECTURE.md's documented shape. It is
-- not FK-enforced — Postgres has no native polymorphic foreign key — so
-- the only writer of this table (the phase-3 admin dashboard) is
-- responsible for populating it from real entity lookups.

CREATE TABLE price_rules (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    scope text NOT NULL
    CONSTRAINT price_rules_scope_valid CHECK (scope IN ('global', 'season', 'hotel', 'room_type')),
    scope_id bigint,
    -- Basis points: 10000 = x1.00 (100%). Integer, never float — CLAUDE.md rule 5.
    target_margin_bps integer
    CONSTRAINT price_rules_target_margin_bps_non_negative CHECK (
        target_margin_bps IS NULL OR target_margin_bps >= 0
    ),
    -- {"bands": [{"min_lead_days": int, "max_lead_days": int|null,
    -- "min_profit_halalas": int}, ...]}
    min_profit_by_lead_time jsonb,
    -- {"occupancy_bands": [...], "lead_time_bands": [...]}, each a list of
    -- {"min": num, "max": num|null, "multiplier_bps": int}
    demand_curve jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    -- scope_id is NULL for, and only for, the global scope.
    CONSTRAINT price_rules_scope_id_matches_scope CHECK ((scope = 'global') = (scope_id IS NULL)),
    -- The global rule is the base of the inheritance chain — it has
    -- nothing to fall through to, so every field must be set.
    CONSTRAINT price_rules_global_is_complete CHECK (
        scope != 'global'
        OR (
            target_margin_bps IS NOT NULL
            AND min_profit_by_lead_time IS NOT NULL
            AND demand_curve IS NOT NULL
        )
    ),
    UNIQUE (scope, scope_id)
);

-- At most one global rule. Postgres treats every NULL as distinct, so the
-- UNIQUE (scope, scope_id) above does not by itself constrain multiple
-- scope='global' rows (scope_id is NULL in all of them) — same pattern as
-- seasons_single_default in migration 0002.
CREATE UNIQUE INDEX price_rules_single_global ON price_rules (scope) WHERE scope = 'global';

ALTER TABLE price_rules ENABLE ROW LEVEL SECURITY;
ALTER TABLE price_rules FORCE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE price_rules FROM anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE price_rules TO service_role;
