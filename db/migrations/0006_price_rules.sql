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
--
-- min_profit_by_lead_time and demand_curve are jsonb band configs. A
-- malformed band set (a gap, an overlap, missing coverage) must fail at
-- INSERT/UPDATE time, not be discovered later at pricing time by falling
-- through to some default — there is no safe default for "no minimum
-- profit floor defined for this lead time". The two functions below
-- enforce that a stored band set is structurally complete: sorted by its
-- lower bound, contiguous, and covering its whole domain.

-- Validates an open-ended band chain: bands must be a non-empty array,
-- every band must have min_lead_days (>=0), max_lead_days (a number
-- greater than min_lead_days, or JSON null), and value_key (>=0) present
-- as actual JSON numbers — a band missing a required key is rejected
-- outright, not treated as an implied default. Sorted by min_lead_days,
-- the bands must form one contiguous chain starting at 0 with exactly one
-- band left open-ended (max_lead_days null) at the end. Shared by
-- min_profit_by_lead_time.bands (value_key 'min_profit_halalas') and
-- demand_curve.lead_time_bands (value_key 'multiplier_bps') — same shape,
-- different value field.
--
-- COALESCE(..., false) matters: without it, a malformed band (e.g. a
-- missing key) can make an internal comparison evaluate to SQL NULL
-- instead of false, and a CHECK constraint treats NULL as satisfied —
-- silently accepting exactly the malformed input this function exists to
-- reject. Every comparison that could see a missing/wrong-typed value is
-- therefore guarded by an explicit jsonb_typeof check first.
CREATE FUNCTION price_rules_is_valid_lead_time_bands(bands jsonb, value_key text)
RETURNS boolean
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT COALESCE(
        jsonb_typeof(bands) = 'array'
        AND jsonb_array_length(bands) > 0
        AND NOT EXISTS (
            SELECT 1
            FROM jsonb_array_elements(bands) AS band
            WHERE jsonb_typeof(band->'min_lead_days') IS DISTINCT FROM 'number'
               OR jsonb_typeof(band->value_key) IS DISTINCT FROM 'number'
               OR jsonb_typeof(band->'max_lead_days') NOT IN ('number', 'null')
        )
        AND NOT EXISTS (
            SELECT 1
            FROM jsonb_array_elements(bands) AS band
            WHERE (band->>'min_lead_days')::numeric < 0
               OR (band->>value_key)::numeric < 0
               OR (
                   jsonb_typeof(band->'max_lead_days') = 'number'
                   AND (band->>'max_lead_days')::numeric <= (band->>'min_lead_days')::numeric
               )
        )
        AND (
            SELECT min((band->>'min_lead_days')::numeric)
            FROM jsonb_array_elements(bands) AS band
        ) = 0
        AND (
            SELECT count(*)
            FROM jsonb_array_elements(bands) AS band
            WHERE jsonb_typeof(band->'max_lead_days') = 'null'
        ) = 1
        AND NOT EXISTS (
            SELECT 1 FROM (
                SELECT
                    band->'max_lead_days' AS max_lead_days,
                    LEAD((band->>'min_lead_days')::numeric)
                        OVER (ORDER BY (band->>'min_lead_days')::numeric) AS next_min
                FROM jsonb_array_elements(bands) AS band
            ) chain
            WHERE jsonb_typeof(max_lead_days) = 'number'
              AND (max_lead_days->>0)::numeric IS DISTINCT FROM next_min
        ),
        false
    )
$$;

-- Validates a bounded band chain (demand_curve.occupancy_bands):
-- occupancy is 0..1, both ends closed — there is no "open-ended"
-- occupancy the way lead time is open-ended into the future, so the
-- chain must start at min=0 and end at max=1 exactly, not null.
CREATE FUNCTION price_rules_is_valid_occupancy_bands(bands jsonb)
RETURNS boolean
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT COALESCE(
        jsonb_typeof(bands) = 'array'
        AND jsonb_array_length(bands) > 0
        AND NOT EXISTS (
            SELECT 1
            FROM jsonb_array_elements(bands) AS band
            WHERE jsonb_typeof(band->'min') IS DISTINCT FROM 'number'
               OR jsonb_typeof(band->'max') IS DISTINCT FROM 'number'
               OR jsonb_typeof(band->'multiplier_bps') IS DISTINCT FROM 'number'
        )
        AND NOT EXISTS (
            SELECT 1
            FROM jsonb_array_elements(bands) AS band
            WHERE (band->>'min')::numeric < 0
               OR (band->>'max')::numeric > 1
               OR (band->>'max')::numeric <= (band->>'min')::numeric
               OR (band->>'multiplier_bps')::numeric < 0
        )
        AND (
            SELECT min((band->>'min')::numeric) FROM jsonb_array_elements(bands) AS band
        ) = 0
        AND (
            SELECT max((band->>'max')::numeric) FROM jsonb_array_elements(bands) AS band
        ) = 1
        AND NOT EXISTS (
            SELECT 1 FROM (
                SELECT
                    (band->>'max')::numeric AS max_occ,
                    LEAD((band->>'min')::numeric)
                        OVER (ORDER BY (band->>'min')::numeric) AS next_min
                FROM jsonb_array_elements(bands) AS band
            ) chain
            WHERE max_occ IS DISTINCT FROM next_min AND next_min IS NOT NULL
        ),
        false
    )
$$;

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
    -- "min_profit_halalas": int}, ...]} — open-ended, must start at 0 and
    -- end with exactly one null max_lead_days band. See
    -- price_rules_is_valid_lead_time_bands above.
    min_profit_by_lead_time jsonb,
    -- {"occupancy_bands": [{"min": num, "max": num, "multiplier_bps": int}, ...],
    --  "lead_time_bands": [{"min_lead_days": int, "max_lead_days": int|null,
    --  "multiplier_bps": int}, ...]}. occupancy_bands is bounded 0..1 (both
    -- ends closed); lead_time_bands is open-ended like min_profit's bands.
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
    CONSTRAINT price_rules_min_profit_bands_valid CHECK (
        min_profit_by_lead_time IS NULL
        OR (
            (min_profit_by_lead_time -> 'bands') IS NOT NULL
            AND price_rules_is_valid_lead_time_bands(
                min_profit_by_lead_time -> 'bands', 'min_profit_halalas'
            )
        )
    ),
    CONSTRAINT price_rules_demand_curve_lead_time_bands_valid CHECK (
        demand_curve IS NULL
        OR (
            (demand_curve -> 'lead_time_bands') IS NOT NULL
            AND price_rules_is_valid_lead_time_bands(
                demand_curve -> 'lead_time_bands', 'multiplier_bps'
            )
        )
    ),
    CONSTRAINT price_rules_demand_curve_occupancy_bands_valid CHECK (
        demand_curve IS NULL
        OR (
            (demand_curve -> 'occupancy_bands') IS NOT NULL
            AND price_rules_is_valid_occupancy_bands(demand_curve -> 'occupancy_bands')
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
