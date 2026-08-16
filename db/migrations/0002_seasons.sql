-- Seasons are a standalone calendar definition, not scoped to a hotel:
-- price_rules (phase 2) links a season to a hotel or room type through its
-- own scope column, not the other way around.
--
-- start_day/end_day are bounded to a generic 1-31 here; whether a given day
-- is valid for a given month and calendar is a phase-2 pricing-engine
-- concern (lib/hijri.py), not a migration-time constraint.

CREATE TABLE seasons (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    season_name text NOT NULL,
    calendar_type text NOT NULL
    CONSTRAINT seasons_calendar_type_valid CHECK (calendar_type IN ('hijri', 'gregorian')),
    start_month smallint NOT NULL
    CONSTRAINT seasons_start_month_valid CHECK (start_month BETWEEN 1 AND 12),
    start_day smallint NOT NULL
    CONSTRAINT seasons_start_day_valid CHECK (start_day BETWEEN 1 AND 31),
    end_month smallint NOT NULL
    CONSTRAINT seasons_end_month_valid CHECK (end_month BETWEEN 1 AND 12),
    end_day smallint NOT NULL
    CONSTRAINT seasons_end_day_valid CHECK (end_day BETWEEN 1 AND 31),
    priority integer NOT NULL DEFAULT 0,
    is_default boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT now()
);

-- At most one default season. ARCHITECTURE.md requires exactly one to
-- always exist; guaranteeing that requires the admin UI to protect the
-- default from deletion (phase 3) rather than a migration-time rule.
CREATE UNIQUE INDEX seasons_single_default ON seasons (is_default) WHERE is_default;

ALTER TABLE seasons ENABLE ROW LEVEL SECURITY;
ALTER TABLE seasons FORCE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE seasons FROM anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE seasons TO service_role;
