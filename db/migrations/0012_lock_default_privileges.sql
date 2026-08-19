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
--    FUNCTIONS FROM PUBLIC looks like the fix, but tested empirically
--    against both a fresh local Postgres schema and a real Supabase
--    project and it is *not sufficient on its own*: a genuinely new
--    function created after that exact statement was still executable by
--    both anon and authenticated (verified via pg_proc.proacl coming
--    back NULL — meaning Postgres fell through to its built-in default
--    instead of consulting any default-ACL row at all). Dropping the
--    IN SCHEMA public clause — a default scoped to role postgres across
--    every schema, not schema-scoped — is what actually suppresses it;
--    re-verified the same way (new function, proacl populated,
--    anon/authenticated both false) and it landed. TABLES/SEQUENCES
--    above do not need this: their built-in Postgres default is already
--    "PUBLIC gets nothing", so a schema-scoped REVOKE-from-nothing is a
--    harmless no-op there, unlike the unsafe PUBLIC-gets-EXECUTE default
--    for functions.
--
-- IMPORTANT — this default is genuinely global (FOR ROLE postgres, no
-- IN SCHEMA), covering every schema postgres creates a function in, not
-- just public. Verified precisely what that does and does not reach,
-- rather than assuming "global" means "everywhere": a schema-specific
-- default-ACL row, where one already exists, wins over the global one —
-- confirmed by reproducing it locally (a schema with its own permissive
-- default plus a global restrictive one still let the permissive
-- schema-specific default through on a new function). Checked which
-- schemas already carry a postgres-scoped row today: public's own
-- (now-restricted-by-this-migration) row, and one more — storage already
-- had a pre-existing (postgres, storage, functions) row from Supabase's
-- own provisioning, still permissive (anon/authenticated/service_role
-- all EXECUTE), untouched by this migration, that would win over the
-- global REVOKE below if postgres ever created a function there. auth
-- and realtime have no such row (their existing default-ACL entries all
-- key to supabase_auth_admin/supabase_admin, never postgres), so the
-- global default here would actually apply if postgres ever created a
-- function in either. None of this is exploitable today: confirmed
-- postgres holds no CREATE privilege on auth, storage, or realtime at
-- all (has_schema_privilege(...) false on all three) — but exact
-- reach matters more than a comforting overstatement, since a future
-- Supabase upgrade could change that CREATE privilege without this
-- migration knowing. Practical consequence: (a) if a future Supabase
-- engine/platform upgrade ever changes what postgres owns in
-- auth/storage/realtime and something there starts returning
-- "permission denied for function", check this migration and specifically
-- whether the affected schema already had its own pre-existing default
-- (storage-shaped) or not (auth/realtime-shaped) — the fix looks
-- different depending on which; (b) any new function this repo's own
-- migrations ever create, in public or any other schema postgres is
-- actually allowed to create in, is unreachable by anon/authenticated by
-- default and needs its own explicit GRANT EXECUTE ... TO <role> — same
-- discipline as a new table needing its own GRANT, no exceptions for
-- "it's just a helper".
--
-- Closing this needs both layers revoked, for existing functions and for
-- the default going forward: REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA
-- public FROM PUBLIC, anon, authenticated is the retroactive half (public
-- only — the only schema this repo's migrations actually create functions
-- in today); the ALTER DEFAULT PRIVILEGES statement (global for role
-- postgres, per wrinkle 2 above) is the going-forward half, and it is
-- intentionally not schema-scoped.

ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public
REVOKE ALL ON TABLES FROM anon, authenticated;

ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public
REVOKE ALL ON SEQUENCES FROM anon, authenticated;

REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA public FROM public, anon, authenticated;

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
