-- Every migration through 0011 followed the same discipline: CREATE TABLE,
-- then ENABLE/FORCE ROW LEVEL SECURITY, then REVOKE ALL ... FROM anon,
-- authenticated, then GRANT ... TO service_role — a deny-list applied by
-- hand, per table, every time. That discipline only works as long as
-- nobody ever forgets the REVOKE line.
--
-- It matters more than it looks: Supabase's own project template installs
-- a default ACL — ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA
-- public GRANT ALL ON TABLES/SEQUENCES TO anon, authenticated,
-- service_role — that appears nowhere in this repo's own migrations.
-- Confirmed empirically against a real Supabase project, not assumed:
-- querying pg_default_acl on a freshly created project, before any
-- migration ran, showed exactly this grant, keyed to role "postgres" —
-- the same role every migration here runs as (apply_migration and CI
-- both connect as "postgres", confirmed via current_user). A forgotten
-- REVOKE on a future table does not go unnoticed at the RLS layer (rule
-- 10's deny-by-default still blocks row access as long as RLS is
-- enabled) — but it leaves that table's underlying grant wide open the
-- moment a policy is ever added without matching column-level care,
-- exactly the failure mode tests/integration/test_cost_tables_rls.py
-- exists to catch.
--
-- This migration flips the posture from deny-list to allow-list at the
-- schema level: nothing created in public by role postgres from this
-- point on is reachable by anon or authenticated unless a later
-- statement — in that same table's own migration — grants it
-- explicitly. Existing tables are untouched: ALTER DEFAULT PRIVILEGES
-- only governs objects created after it runs, never retroactively
-- changes privileges on objects that already exist (every one of
-- 0001-0011's tables already carries its own explicit REVOKE/GRANT
-- regardless). Scoped to "public" only — auth, storage, and realtime
-- are Supabase-managed schemas and untouched. Scoped to role "postgres"
-- only — confirmed nothing in public is owned by any other role today,
-- so this cannot orphan an existing grant.
--
-- Functions have the same problem, with two extra wrinkles confirmed
-- empirically, not assumed:
--
-- 1. Postgres grants EXECUTE on every new function to the PUBLIC
--    pseudo-role automatically, and every role (anon and authenticated
--    included) is implicitly a member of PUBLIC. REVOKE EXECUTE ... FROM
--    anon alone does nothing while PUBLIC still holds its own separate
--    grant. Checked pg_proc.proacl directly on this schema's existing
--    functions before writing the fix below: each one carried five
--    separate ACL entries — PUBLIC, postgres, anon, authenticated,
--    service_role — meaning Supabase's own default ACL for role postgres
--    in schema public grants anon/authenticated/service_role by name *in
--    addition to* the automatic PUBLIC grant, not instead of it.
--
-- 2. ALTER DEFAULT PRIVILEGES ... IN SCHEMA public REVOKE EXECUTE ON
--    FUNCTIONS FROM PUBLIC looks like the fix. It is necessary but, on
--    its own, not sufficient — and this was verified twice, the second
--    time correcting the first: initial testing against a real Supabase
--    project seemed to show that dropping IN SCHEMA (a global default)
--    was what fixed it. That conclusion was contaminated by leftover
--    state from the debugging session itself — an earlier schema-scoped
--    REVOKE attempt, run and left in place before the global one was
--    tried, had already scrubbed the schema-specific row on that
--    project, so the "it works now" test wasn't isolating the global
--    statement at all. Caught this for real once tests/conftest.py
--    started simulating Supabase's actual pristine defaults (see
--    tests/supabase_default_acl_baseline.sql) instead of plain
--    Postgres's own defaults: against a truly fresh baseline, the global
--    statement alone left a new function fully executable by both anon
--    and authenticated, because a schema-specific default-ACL row, where
--    one already exists — which a pristine Supabase project's "public"
--    schema does, from its own provisioning — wins over a global one for
--    that schema. Reproduced the fix from scratch against the fresh
--    baseline to confirm: both statements together, schema-scoped and
--    global, are what actually closes it.
--
-- The schema-scoped statement handles "public" specifically, the only
-- schema this repo's migrations create functions in today. The global
-- statement (FOR ROLE postgres, no IN SCHEMA) is kept alongside it
-- deliberately, not redundantly: it is what protects any OTHER schema
-- postgres might ever create a function in that does not already carry
-- its own pre-existing schema-specific row. Checked which schemas
-- already carry a postgres-scoped functions row today: public's own
-- (now handled by the schema-scoped statement below), and one more —
-- storage already has a pre-existing (postgres, storage, functions) row
-- from Supabase's own provisioning, still permissive
-- (anon/authenticated/service_role all EXECUTE), untouched by this
-- migration, that would win over the global statement if postgres ever
-- created a function there. auth and realtime have no such row (their
-- existing default-ACL entries all key to
-- supabase_auth_admin/supabase_admin, never postgres), so the global
-- statement would actually apply if postgres ever created a function in
-- either. None of this is exploitable today: confirmed postgres holds no
-- CREATE privilege on auth, storage, or realtime at all
-- (has_schema_privilege(...) false on all three) — but exact reach
-- matters more than a comforting overstatement, since a future Supabase
-- upgrade could change that CREATE privilege without this migration
-- knowing. Practical consequence: (a) if a future Supabase
-- engine/platform upgrade ever changes what postgres owns in
-- auth/storage/realtime and something there starts returning
-- "permission denied for function", check this migration and
-- specifically whether the affected schema already had its own
-- pre-existing default (storage-shaped, needs its own schema-scoped
-- statement here too) or not (auth/realtime-shaped, the existing global
-- statement already covers it); (b) any new function this repo's own
-- migrations ever create, in public or any other schema postgres is
-- actually allowed to create in, is unreachable by anon/authenticated by
-- default and needs its own explicit GRANT EXECUTE ... TO <role> — same
-- discipline as a new table needing its own GRANT, no exceptions for
-- "it's just a helper".
--
-- Closing this needs three things: the retroactive REVOKE for functions
-- that already exist, the schema-scoped default for "public" specifically,
-- and the global default as a backstop for any other schema.

ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public
REVOKE ALL ON TABLES FROM anon, authenticated;

ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public
REVOKE ALL ON SEQUENCES FROM anon, authenticated;

REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA public FROM public, anon, authenticated;

ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public
REVOKE EXECUTE ON FUNCTIONS FROM public, anon, authenticated;

ALTER DEFAULT PRIVILEGES FOR ROLE postgres
REVOKE EXECUTE ON FUNCTIONS FROM public, anon, authenticated;

-- Re-grant only the two functions RLS policies actually need
-- "authenticated" to call: migration 0010's app_users_select_all_for_admin
-- policy evaluates current_app_role() for every row-visibility check an
-- authenticated user makes against app_users, and the not-yet-built
-- cost-masking view (ARCHITECTURE.md §8) will call
-- current_user_can_view_cost() the same way. Confirmed the login ->
-- dashboard read still resolves correctly after the REVOKE above, by
-- replaying app_users_select_own's own auth.uid() lookup as
-- authenticated against a real project. The other four functions
-- (price_rules_is_valid_*, quotes_is_valid_night_record,
-- quotes_all_nights_are_complete) are CHECK-constraint validators that
-- only service_role's own INSERT/UPDATE on price_rules/quotes ever
-- needs to invoke — anon and authenticated have no INSERT/UPDATE grant
-- on either table at all, so they never had a legitimate reason to
-- execute these either, and stay fully locked down.

GRANT EXECUTE ON FUNCTION current_app_role() TO authenticated;
GRANT EXECUTE ON FUNCTION current_user_can_view_cost() TO authenticated;
