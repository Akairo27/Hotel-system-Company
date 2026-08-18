-- DRAFT — see 0010_app_users_and_roles.sql's header for why this lives
-- here instead of db/migrations/, and docs/phase-3-pr-a/README.md for the
-- promotion checklist.
--
-- Structure only, per the phase-3 PR-A scope — no trigger or application
-- code writes to this table yet. That arrives with PR D (cost/margin/floor
-- management), the first screen that changes a financial value an admin
-- can already see change out from under them.
--
-- row_id is text rather than typed to match each referenced table's own
-- primary key: app_users uses uuid, everything else in this schema
-- (hotels, room_types, seasons, price_rules, ...) uses bigint identity.
-- A generic audit table spanning both key types can't use a typed FK to
-- "the row it's about" without a separate audit table per source table,
-- which is exactly the kind of premature structure CLAUDE.md's craft
-- standards ask to avoid until a second concrete need justifies it.

CREATE TABLE audit_log (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    table_name text NOT NULL,
    row_id text NOT NULL,
    column_name text NOT NULL,
    old_value jsonb,
    new_value jsonb,
    changed_by uuid NOT NULL REFERENCES app_users (id),
    changed_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE audit_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_log FORCE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE audit_log FROM anon, authenticated;
-- Append-only, same reasoning as quotes (migration 0008): SELECT and
-- INSERT only, no UPDATE or DELETE grant to any role, ever. An audit
-- trail that can be edited is not an audit trail.
GRANT SELECT, INSERT ON TABLE audit_log TO service_role;

-- Read access is admin-only: an audit entry can carry a financial value
-- (old_value/new_value on a cost or margin column) that a non-admin user
-- must not see any more here than on the row it describes.
GRANT SELECT ON TABLE audit_log TO authenticated;

CREATE POLICY audit_log_select_admin_only ON audit_log
    FOR SELECT TO authenticated
    USING (current_app_role() = 'admin');
