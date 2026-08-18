-- Identity lives in Supabase Auth (auth.users); this table only adds the
-- roles and permissions RLS policies key off of. Per the phase-3 decision:
-- claims embedded in a JWT go stale until the user logs out and back in,
-- so every policy resolves role/can_view_cost by reading this table live
-- through a SECURITY DEFINER function, never by trusting the JWT itself.
--
-- can_view_cost is deliberately independent of role, not implied by it:
-- ARCHITECTURE.md frames cost visibility as its own dedicated policy, and
-- the phase-3 decision describes it as a toggle the client flips per
-- person from the screen — an admin without cost visibility, or a sales
-- user with it, are both meant to be expressible. No uniqueness constraint
-- caps how many users can have it on; if the client wants that capped to
-- exactly one, that is a UI rule enforced in the phase-3-PR-D screen, not
-- a database constraint, matching how seasons_single_default (migration
-- 0002) is the one place in this schema a "there can be only one" rule is
-- actually enforced at the DB level.

-- Migration 0001 granted schema USAGE to service_role only — nothing
-- before this migration ever gave authenticated a real table or function
-- grant, so there was nothing for it to resolve. This is the first one
-- that does (the SELECT grant below, plus current_app_role()'s and
-- current_user_can_view_cost()'s EXECUTE grants): without schema USAGE,
-- Postgres can't resolve any unqualified "app_users" or "current_app_role()"
-- reference for that role at all, SECURITY DEFINER or not — it fails with
-- "does not exist", not a permission error, before the grant below is ever
-- consulted.
GRANT USAGE ON SCHEMA public TO authenticated;

CREATE TABLE app_users (
    id uuid PRIMARY KEY REFERENCES auth.users (id) ON DELETE CASCADE,
    full_name text NOT NULL,
    app_role text NOT NULL
    CONSTRAINT app_users_role_valid CHECK (app_role IN ('admin', 'sales')),
    can_view_cost boolean NOT NULL DEFAULT false,
    is_active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now()
);

-- Deactivating (is_active = false) is how an admin removes someone's
-- access — the row is never deleted while audit_log still references it
-- as changed_by (migration 0011's FK has no ON DELETE clause, so Postgres
-- rejects that DELETE outright rather than losing the audit trail's
-- attribution). Deleting auth.users cascades here too, so the same
-- protection applies transitively to removing the Auth identity itself.

ALTER TABLE app_users ENABLE ROW LEVEL SECURITY;
ALTER TABLE app_users FORCE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE app_users FROM anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE app_users TO service_role;

-- SELECT only for authenticated — deliberately no INSERT/UPDATE/DELETE
-- grant at all. Role and can_view_cost changes go through service_role
-- from a Next.js Server Action (phase-3 PR D's user-management screen),
-- never through a client-side RLS-checked write. An UPDATE policy that
-- let a user edit "their own row" would let that same user promote their
-- own role to admin or flip their own can_view_cost on — self-escalation
-- through the exact policy meant to gate cost visibility. No policy can
-- close that hole while still allowing the row's own owner to update any
-- of their own columns, so the write path is server_role-only instead.
GRANT SELECT ON TABLE app_users TO authenticated;

-- SECURITY DEFINER + a fixed search_path: the function runs as its owner
-- (the migration role, which is not subject to app_users' own RLS), which
-- is what lets a policy on app_users call this function without the
-- infinite-recursion a normal (SECURITY INVOKER) function would hit —
-- evaluating this SELECT would itself re-trigger the calling policy.
-- Pinning search_path stops a caller from shadowing "app_users" with an
-- object in a schema earlier on their own search_path.
CREATE FUNCTION current_app_role() RETURNS text
LANGUAGE sql
SECURITY DEFINER
STABLE
SET search_path = public
AS $$
    SELECT app_role FROM app_users WHERE id = auth.uid() AND is_active
$$;

CREATE FUNCTION current_user_can_view_cost() RETURNS boolean
LANGUAGE sql
SECURITY DEFINER
STABLE
SET search_path = public
AS $$
    SELECT COALESCE(
        (SELECT can_view_cost FROM app_users WHERE id = auth.uid() AND is_active),
        false
    )
$$;

GRANT EXECUTE ON FUNCTION current_app_role() TO authenticated;
GRANT EXECUTE ON FUNCTION current_user_can_view_cost() TO authenticated;

CREATE POLICY app_users_select_own ON app_users
FOR SELECT TO authenticated
USING (id = auth.uid());

CREATE POLICY app_users_select_all_for_admin ON app_users
FOR SELECT TO authenticated
USING (current_app_role() = 'admin');
