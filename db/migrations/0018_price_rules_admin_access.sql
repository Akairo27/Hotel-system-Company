-- Deferred by migration 0006 for exactly this reason: price_rules' jsonb
-- band configs (min_profit_by_lead_time, demand_curve) are guarded by CHECK
-- constraints that call price_rules_is_valid_lead_time_bands and
-- price_rules_is_valid_occupancy_bands — a raw Postgres violation of either
-- is not something a non-technical admin can act on, so the admin screen
-- and this migration ship together with a client-side validator that
-- diagnoses the same failure in Arabic before the row ever reaches this
-- table. This migration is the DB half only: grants, RLS, masking, audit.
--
-- Two of this table's three value columns reverse-derive cost, not one.
-- target_margin_bps is the multiplier applied to cost, and
-- min_profit_by_lead_time is a floor denominated in halalas of profit over
-- cost — anyone holding a quoted price and either column can solve back to
-- the cost figure ARCHITECTURE.md §8 exists to hide. Both go behind
-- current_user_can_view_cost() in the masking view below. demand_curve is
-- pure occupancy/lead-time multipliers with no cost term anywhere in it, so
-- it stays readable by any active app_users row, the same way
-- allotments.total_rooms did in migration 0016.
--
-- No DELETE grant to authenticated, same as migrations 0014/0015: a deleted
-- price_rules row silently re-points every stay date it covered at the
-- next-less-specific scope in the inheritance chain, moving prices with
-- nothing in the audit trail to say why. service_role stays the only role
-- that can delete one. (The reversible way out of a wrong-scope row is
-- price_rules.is_active, migration 0020 — a stuck-forever misconfiguration
-- here is not the same class of harmless clutter a stray hotels/seasons row
-- is, so unlike those tables this one gets a real undo path.)
--
-- Correction to migration 0016's comment, recorded forward rather than
-- edited into that already-applied migration (CLAUDE.md §7: migrations are
-- forward-only): 0016 confirmed rolbypassrls = true for `postgres` on
-- hotel-sales-agent-dev and described that as a Supabase fact, without
-- saying whether local Postgres differs. Confirmed this session that it
-- does not — local `postgres` also holds rolsuper = true, rolbypassrls =
-- true, exactly like Supabase's. There is no local/production divergence in
-- how the masking view below sees rows; 0016's comment should not be read
-- as implying one.

-- Migration 0012 revoked EXECUTE on every function in public from
-- authenticated, and its own comment justified leaving these two locked
-- down on the grounds that authenticated has no INSERT/UPDATE grant on
-- price_rules at all. The INSERT grant below is the statement that stops
-- being true. Confirmed empirically, not reasoned from the documentation: a
-- CHECK constraint that calls a SQL function is evaluated with the
-- *writing* role's privileges, so without these two grants a structurally
-- valid INSERT fails with "permission denied for function
-- price_rules_is_valid_lead_time_bands" — SQLSTATE 42501,
-- insufficient_privilege, not check_violation — before any band validation
-- runs at all.
GRANT EXECUTE ON FUNCTION price_rules_is_valid_lead_time_bands(jsonb, text) TO authenticated;
GRANT EXECUTE ON FUNCTION price_rules_is_valid_occupancy_bands(jsonb) TO authenticated;

-- Column-scoped, never table-level: a table-level SELECT here would let any
-- authenticated identity read target_margin_bps straight off the base
-- table and walk around the masking view entirely. Confirmed the scoping
-- holds against the indirect routes too — with only these three columns
-- granted, filtering or ordering by a column outside the grant fails
-- 42501, not just a direct SELECT of it.
--
-- scope and scope_id are readable because the write path below identifies
-- its row by them (migration 0016 granted SELECT (id) for the same
-- reason), and insertable because creating a rule has to say what it
-- scopes to — but deliberately not updatable: re-pointing an existing rule
-- from one hotel to another is a delete plus a create, not an edit, and it
-- would move a financial value onto a different entity while the audit
-- trail recorded no change at all. created_at gets no grant either, so it
-- can only ever be its DEFAULT.
GRANT SELECT (id, scope, scope_id) ON TABLE price_rules TO authenticated;
GRANT INSERT (scope, scope_id, target_margin_bps, min_profit_by_lead_time, demand_curve)
ON TABLE price_rules TO authenticated;
GRANT UPDATE (target_margin_bps, min_profit_by_lead_time, demand_curve)
ON TABLE price_rules TO authenticated;

-- Confirmed empirically, the same gotcha migration 0016 found for
-- allotments: a FOR UPDATE policy's USING clause decides which rows an
-- UPDATE may touch, but does not make a row visible to the WHERE clause
-- that identifies it. With only the two write policies below and this one
-- absent, an UPDATE that an admin otherwise qualifies for still matches
-- zero rows — FORCE ROW LEVEL SECURITY denies by default when no FOR
-- SELECT policy exists. Scoped to the same three columns granted above:
-- this is row visibility, not margin visibility.
CREATE POLICY price_rules_select_scope_for_active_users ON price_rules
FOR SELECT TO authenticated
USING (current_app_role() IS NOT NULL);

-- Write access is admin AND cost visibility, the pairing migration 0016
-- established for allotments_update_cost_for_admin: an admin who cannot
-- see a margin must not overwrite it blind. Applied to INSERT as well as
-- UPDATE here, because unlike allotments these rows are created from the
-- dashboard, and creating the global rule sets all three financial values
-- in one statement.
CREATE POLICY price_rules_insert_for_admin ON price_rules
FOR INSERT TO authenticated
WITH CHECK (current_app_role() = 'admin' AND current_user_can_view_cost());

CREATE POLICY price_rules_update_for_admin ON price_rules
FOR UPDATE TO authenticated
USING (current_app_role() = 'admin' AND current_user_can_view_cost())
WITH CHECK (current_app_role() = 'admin' AND current_user_can_view_cost());

-- Same masking-view shape as allotments_for_dashboard (migration 0016),
-- with two conditional columns instead of one. The view is owned by the
-- migration role and is not security_invoker, so it reads price_rules with
-- its owner's privileges — which is what lets it project columns
-- authenticated holds no grant on at all, and why the WHERE clause has to
-- restate the row-visibility rule by hand: the owner is not subject to
-- this table's RLS, so without it any authenticated identity would see
-- every rule whether or not they have an app_users row.
CREATE VIEW price_rules_for_dashboard AS
SELECT
    id,
    scope,
    scope_id,
    demand_curve,
    created_at,
    CASE WHEN current_user_can_view_cost() THEN target_margin_bps END AS target_margin_bps,
    CASE
        WHEN current_user_can_view_cost() THEN min_profit_by_lead_time
    END AS min_profit_by_lead_time
FROM price_rules
WHERE current_app_role() IS NOT NULL;

GRANT SELECT ON price_rules_for_dashboard TO authenticated;

-- One audit_log row per changed financial column, same shape as migration
-- 0017's app_users trigger. SECURITY DEFINER for migration 0016's reason
-- rather than 0017's: this table's write path runs as authenticated, which
-- holds SELECT but not INSERT on audit_log.
--
-- prev is declared as a price_rules row rather than a record so the INSERT
-- case can share one body with the UPDATE case: an unassigned composite
-- variable reads back as NULL in every field, where an unassigned "record"
-- raises "record prev is not assigned yet" on first field access. old
-- itself cannot be read on INSERT at all, hence the TG_OP guard rather
-- than a NULL test on old.
--
-- to_jsonb() is applied uniformly, including to the two columns that are
-- already jsonb — confirmed it is the identity function there and does
-- not re-encode a jsonb value as a JSON string. It is also strict, so a
-- NULL column lands in audit_log as SQL NULL rather than the jsonb literal
-- 'null' — exactly what an INSERT should record as old_value.
CREATE FUNCTION price_rules_audit_trigger() RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    actor uuid := current_actor_id();
    prev price_rules;
BEGIN
    IF actor IS NULL THEN
        RAISE EXCEPTION 'app.actor_id must be set before writing price_rules';
    END IF;
    IF TG_OP = 'UPDATE' THEN
        prev := old;
    END IF;
    IF new.target_margin_bps IS DISTINCT FROM prev.target_margin_bps THEN
        INSERT INTO audit_log (table_name, row_id, column_name, old_value, new_value, changed_by)
        VALUES (
            'price_rules',
            new.id::text,
            'target_margin_bps',
            to_jsonb(prev.target_margin_bps),
            to_jsonb(new.target_margin_bps),
            actor
        );
    END IF;
    IF new.min_profit_by_lead_time IS DISTINCT FROM prev.min_profit_by_lead_time THEN
        INSERT INTO audit_log (table_name, row_id, column_name, old_value, new_value, changed_by)
        VALUES (
            'price_rules',
            new.id::text,
            'min_profit_by_lead_time',
            to_jsonb(prev.min_profit_by_lead_time),
            to_jsonb(new.min_profit_by_lead_time),
            actor
        );
    END IF;
    IF new.demand_curve IS DISTINCT FROM prev.demand_curve THEN
        INSERT INTO audit_log (table_name, row_id, column_name, old_value, new_value, changed_by)
        VALUES (
            'price_rules',
            new.id::text,
            'demand_curve',
            to_jsonb(prev.demand_curve),
            to_jsonb(new.demand_curve),
            actor
        );
    END IF;
    RETURN new;
END;
$$;

-- Two triggers, not one: "AFTER INSERT OR UPDATE ... WHEN (old.x IS
-- DISTINCT FROM new.x)" is rejected outright by Postgres with "INSERT
-- trigger's WHEN condition cannot reference OLD values". The UPDATE case
-- therefore keeps migrations 0016/0017's WHEN-clause short-circuit, and
-- the INSERT case, which has nothing to compare against, takes every row
-- and lets the function body decide.
--
-- The INSERT trigger firing unconditionally means every seed path that
-- creates a price_rules row must now set app.actor_id first, the same way
-- every write to allotments.cost_per_night already must — including this
-- repository's own test fixtures (tests/integration/_seed.py's
-- seed_price_rule and the two positive-case inserts in
-- test_schema_constraints.py). This is deliberate, not an oversight: a
-- price_rules row is created, not just edited, and an unattributed INSERT
-- of a margin or profit floor is exactly the gap the trigger exists to
-- close.
CREATE TRIGGER price_rules_audit_insert
AFTER INSERT ON price_rules
FOR EACH ROW
EXECUTE FUNCTION price_rules_audit_trigger();

CREATE TRIGGER price_rules_audit_update
AFTER UPDATE ON price_rules
FOR EACH ROW
WHEN (
    old.target_margin_bps IS DISTINCT FROM new.target_margin_bps
    OR old.min_profit_by_lead_time IS DISTINCT FROM new.min_profit_by_lead_time
    OR old.demand_curve IS DISTINCT FROM new.demand_curve
)
EXECUTE FUNCTION price_rules_audit_trigger();

-- The only supported write path, SECURITY INVOKER (the default) for
-- migration 0016's reason: the policies above stay the real enforcement
-- layer, and auth.uid() is trustworthy here precisely because the
-- function runs as the caller.
--
-- UPDATE-then-INSERT rather than ON CONFLICT, for two independently
-- sufficient reasons, both confirmed empirically:
--
-- 1. ON CONFLICT (scope, scope_id) cannot upsert the global rule. Postgres
--    treats NULLs as distinct and the global row is the one with scope_id
--    IS NULL, so it never matches that arbiter — the INSERT falls through
--    and dies on the price_rules_single_global partial index instead.
--    Naming that partial index as the arbiter fixes the global case and
--    fits no scoped one, so ON CONFLICT would mean two code paths where
--    this is one.
-- 2. "DO UPDATE SET col = excluded.col" requires SELECT on col of the
--    target table — confirmed by watching the identical statement start
--    working the moment the three value columns were added to the SELECT
--    grant. That is precisely the grant this migration must not make.
--
-- The EXISTS re-check is what stops a denied UPDATE from turning into an
-- attempted INSERT: RLS filters the row out rather than raising (the
-- gotcha migration 0014 found), so without it a sales user editing an
-- existing rule falls through to the INSERT branch and gets a confusing
-- unique-violation instead of a permission error.
--
-- This is a whole-row replace, not a patch: a NULL argument clears that
-- column, which is the correct semantics for a field-by-field inheritance
-- table where NULL means "this scope does not override this field". The
-- caller must send all three values every time, including ones it did not
-- change.
CREATE FUNCTION admin_upsert_price_rule(
    rule_scope text,
    rule_scope_id bigint,
    new_target_margin_bps integer,
    new_min_profit_by_lead_time jsonb,
    new_demand_curve jsonb
)
RETURNS bigint
LANGUAGE plpgsql
SET search_path = public
AS $$
DECLARE
    rule_id bigint;
BEGIN
    PERFORM set_config('app.actor_id', auth.uid()::text, true);
    UPDATE price_rules
    SET
        target_margin_bps = new_target_margin_bps,
        min_profit_by_lead_time = new_min_profit_by_lead_time,
        demand_curve = new_demand_curve
    WHERE scope = rule_scope AND scope_id IS NOT DISTINCT FROM rule_scope_id
    RETURNING id INTO rule_id;
    IF FOUND THEN
        RETURN rule_id;
    END IF;
    IF EXISTS (
        SELECT 1 FROM price_rules
        WHERE scope = rule_scope AND scope_id IS NOT DISTINCT FROM rule_scope_id
    ) THEN
        RAISE EXCEPTION 'not permitted to update this price rule' USING ERRCODE = '42501';
    END IF;
    INSERT INTO price_rules (
        scope, scope_id, target_margin_bps, min_profit_by_lead_time, demand_curve
    )
    VALUES (
        rule_scope,
        rule_scope_id,
        new_target_margin_bps,
        new_min_profit_by_lead_time,
        new_demand_curve
    )
    RETURNING id INTO rule_id;
    RETURN rule_id;
END;
$$;

GRANT EXECUTE ON FUNCTION admin_upsert_price_rule(text, bigint, integer, jsonb, jsonb)
TO authenticated;
