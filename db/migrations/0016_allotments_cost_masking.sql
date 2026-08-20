-- PR D (cost/margin/floor management): the first migration to open any
-- read/write access to allotments.cost_per_night for authenticated, per
-- ARCHITECTURE.md §8's "إخفاء عمود التكلفة" decision — a masking VIEW with
-- a conditional column, never a column-level GRANT (breaks SELECT *) or a
-- separate view per role (two objects to keep in sync).
--
-- Scope, per the phase-3 decision: cost_per_night only. total_rooms and
-- allotment creation belong to the still-unbuilt daily-allotment-entry
-- screen — this migration adds no INSERT grant on allotments at all, and
-- no column but cost_per_night becomes writable here.

-- Confirmed live against hotel-sales-agent-dev, not assumed: `postgres`
-- there holds rolbypassrls = true (queried pg_roles directly), so the
-- masking view below — owned by whichever role runs this migration — sees
-- every row regardless of allotments' FORCE ROW LEVEL SECURITY. No SELECT
-- policy scoped to authenticated is needed for the view itself to work;
-- the grant/policy pair below exists only for the write path's WHERE
-- clause, a separate concern.
GRANT SELECT (id) ON TABLE allotments TO authenticated;
GRANT UPDATE (cost_per_night) ON TABLE allotments TO authenticated;

-- Confirmed empirically, not assumed from how migration 0014's policies
-- read: a FOR UPDATE policy's USING clause governs which rows an UPDATE
-- can touch, but does NOT by itself make a row visible to the WHERE
-- clause that identifies it — a bare `SELECT id FROM allotments` (and,
-- transitively, `UPDATE ... WHERE id = $1`) returned zero rows for a
-- qualifying admin until this policy existed, with FORCE ROW LEVEL
-- SECURITY defaulting to deny-all in the absence of any FOR SELECT
-- policy. Scoped to the same `id`-only column grant above — row
-- visibility, not cost visibility.
CREATE POLICY allotments_select_id_for_active_users ON allotments
FOR SELECT TO authenticated
USING (current_app_role() IS NOT NULL);

-- An admin without cost visibility must not blindly overwrite a value they
-- cannot see — the same current_user_can_view_cost() gate ARCHITECTURE.md
-- §8 uses for reads applies to this write too, not just current_app_role().
CREATE POLICY allotments_update_cost_for_admin ON allotments
FOR UPDATE TO authenticated
USING (current_app_role() = 'admin' AND current_user_can_view_cost())
WITH CHECK (current_app_role() = 'admin' AND current_user_can_view_cost());

-- authenticated has no direct SELECT on cost_per_night at all — masking
-- can't be bypassed by querying allotments directly instead of this view;
-- there is nothing to select there in the first place.
--
-- The view's owner holds rolbypassrls (confirmed on hotel-sales-agent-dev,
-- see above), so RLS's own `current_app_role() IS NOT NULL` row-visibility
-- convention (migrations 0014/0015) never applies to it automatically —
-- without repeating that same condition directly in the view's WHERE
-- clause, any authenticated Supabase identity would see every row here,
-- app_users membership or not. Masking the cost column alone is not the
-- same guarantee as row visibility being gated the same way as every
-- other admin-dashboard table.
CREATE VIEW allotments_for_dashboard AS
SELECT
    id,
    hotel_id,
    room_type_id,
    stay_date,
    total_rooms,
    CASE WHEN current_user_can_view_cost() THEN cost_per_night ELSE NULL END AS cost_per_night,
    created_at
FROM allotments
WHERE current_app_role() IS NOT NULL;

GRANT SELECT ON allotments_for_dashboard TO authenticated;

-- Reads the session-local actor handoff triggers use, mirroring
-- auth.uid()'s own NULLIF(current_setting(...), '')::uuid idiom
-- (tests/conftest.py's _AUTH_SCHEMA_SQL) exactly — confirmed empirically
-- that the plain form is not enough: once app.actor_id has been SET LOCAL
-- at least once in a session, Postgres resets it to '' (not NULL) once
-- that transaction ends, so a later transaction's bare `IS NULL` check
-- misses an unset value and lets an invalid-uuid error leak through
-- instead of this function's own clear rejection.
CREATE FUNCTION current_actor_id() RETURNS uuid
LANGUAGE sql
STABLE
SET search_path = public
AS $$
    SELECT NULLIF(current_setting('app.actor_id', true), '')::uuid
$$;

GRANT EXECUTE ON FUNCTION current_actor_id() TO authenticated, service_role;

-- Audit trail (audit_log, migration 0011 — its own comment names this PR
-- as the first writer). A trigger, not just the wrapper function below: a
-- trigger fires no matter which path reaches the row — this RPC, or any
-- future direct UPDATE — a function only fires for callers that remember
-- to use it, which is exactly the gap already closed for append-only
-- (quotes/audit_log), cost masking (this migration), and now this. If
-- app.actor_id is not set, the write is rejected outright, not logged with
-- a null actor. SECURITY DEFINER is required here specifically because
-- this table's write path runs as authenticated (unlike app_users' write
-- path in migration 0017, which runs as service_role), and authenticated
-- has no INSERT grant on audit_log.
CREATE FUNCTION allotments_audit_trigger() RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    actor uuid := current_actor_id();
BEGIN
    IF actor IS NULL THEN
        RAISE EXCEPTION 'app.actor_id must be set before updating allotments.cost_per_night';
    END IF;
    INSERT INTO audit_log (table_name, row_id, column_name, old_value, new_value, changed_by)
    VALUES (
        'allotments',
        NEW.id::text,
        'cost_per_night',
        to_jsonb(OLD.cost_per_night),
        to_jsonb(NEW.cost_per_night),
        actor
    );
    RETURN NEW;
END;
$$;

CREATE TRIGGER allotments_audit_cost_per_night
AFTER UPDATE ON allotments
FOR EACH ROW
WHEN (OLD.cost_per_night IS DISTINCT FROM NEW.cost_per_night)
EXECUTE FUNCTION allotments_audit_trigger();

-- The only supported write path for cost_per_night. set_config(..., true)
-- is SET LOCAL semantics, scoped to this call's own transaction (one RPC
-- call is one transaction) — it can never leak into a later, unrelated
-- request on a pooled connection. auth.uid() is used directly here, not a
-- client-supplied parameter, because this function runs as authenticated
-- (SECURITY INVOKER, the default — deliberately not DEFINER, so the RLS
-- policy above stays the real enforcement layer, same philosophy as every
-- other write in this dashboard), where auth.uid() is real and cannot be
-- spoofed by the caller. A denied UPDATE does not raise on its own (RLS's
-- USING clause just filters the row out, same gotcha migration 0014 found)
-- — NOT FOUND makes that explicit instead of returning silent success.
CREATE FUNCTION admin_set_allotment_cost(allotment_id bigint, new_cost_per_night bigint)
RETURNS void
LANGUAGE plpgsql
SET search_path = public
AS $$
BEGIN
    PERFORM set_config('app.actor_id', auth.uid()::text, true);
    UPDATE allotments SET cost_per_night = new_cost_per_night WHERE id = allotment_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'not permitted to update this allotment' USING ERRCODE = '42501';
    END IF;
END;
$$;

GRANT EXECUTE ON FUNCTION admin_set_allotment_cost(bigint, bigint) TO authenticated;
