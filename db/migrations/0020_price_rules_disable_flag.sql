-- price_rules gets no DELETE grant for authenticated, matching
-- hotels/room_types (migration 0014) and seasons (0015). For those tables
-- that is harmless — an extra row is clutter an admin can ignore. Here it
-- is not: a price_rules row created at the wrong scope silently shadows
-- the inheritance chain for every quote touching that scope, and nothing
-- migration 0018 makes writable can undo it. All three updatable columns
-- there are values, not switches — NULLing them out leaves the row still
-- matching, and services/pricing/rules.py resolves each field to the most
-- specific row that set it, so an all-NULL row stops mattering only by
-- accident.
--
-- is_active is the switch: reversible, audited, and — with the matching
-- WHERE change in services/pricing/rules.py that ships alongside this
-- migration — actually excluded from resolution. The column alone changes
-- nothing; the query is what reads it.
ALTER TABLE price_rules ADD COLUMN is_active boolean NOT NULL DEFAULT TRUE;

-- The global rule is the base of the inheritance chain — nothing falls
-- through past it. Deactivating it would make resolve_price_rule raise
-- IncompletePriceRuleChainError for every quote in the system, so that
-- state is not made recoverable, it is made unrepresentable: same
-- reasoning and same mechanism as price_rules_global_is_complete
-- (migration 0006).
ALTER TABLE price_rules ADD CONSTRAINT price_rules_global_always_active
CHECK (scope != 'global' OR is_active);

-- Additive to migration 0018's column-level UPDATE grant rather than a
-- restatement of it: Postgres accumulates per-column grants, so the three
-- value columns stay updatable alongside this switch.
GRANT UPDATE (is_active) ON TABLE price_rules TO authenticated;

-- authenticated holds SELECT on (id, scope, scope_id) only (migration
-- 0018), so this view is the dashboard's only way to read is_active at
-- all — without it an admin cannot tell a disabled rule from an enabled
-- one, and the reversibility this migration exists for is a promise the
-- UI cannot keep. Inactive rows are deliberately still returned: hiding
-- them is how a disabled rule becomes impossible to re-enable.
--
-- Restated wholesale rather than CREATE OR REPLACE VIEW: that form can
-- only append columns, which would put is_active behind the two masked
-- CASE columns and trip sqlfluff's ST06 (simple targets before
-- calculations). Dropping the view discards migration 0018's GRANT with
-- it, so that grant is reissued below.
DROP VIEW price_rules_for_dashboard;

CREATE VIEW price_rules_for_dashboard AS
SELECT
    id,
    scope,
    scope_id,
    demand_curve,
    created_at,
    is_active,
    CASE WHEN current_user_can_view_cost() THEN target_margin_bps END AS target_margin_bps,
    CASE
        WHEN current_user_can_view_cost() THEN min_profit_by_lead_time
    END AS min_profit_by_lead_time
FROM price_rules
WHERE current_app_role() IS NOT NULL;

GRANT SELECT ON price_rules_for_dashboard TO authenticated;

-- Extends migration 0018's trigger function with a fourth tracked column.
-- CREATE OR REPLACE keeps the function's oid, so the price_rules_audit_insert
-- trigger keeps pointing at it untouched. The UPDATE trigger is not so
-- lucky: a trigger's WHEN clause is fixed at creation, so widening it
-- means dropping and recreating that trigger specifically.
CREATE OR REPLACE FUNCTION price_rules_audit_trigger() RETURNS trigger
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
    IF new.is_active IS DISTINCT FROM prev.is_active THEN
        INSERT INTO audit_log (table_name, row_id, column_name, old_value, new_value, changed_by)
        VALUES (
            'price_rules',
            new.id::text,
            'is_active',
            to_jsonb(prev.is_active),
            to_jsonb(new.is_active),
            actor
        );
    END IF;
    RETURN new;
END;
$$;

DROP TRIGGER price_rules_audit_update ON price_rules;

CREATE TRIGGER price_rules_audit_update
AFTER UPDATE ON price_rules
FOR EACH ROW
WHEN (
    old.target_margin_bps IS DISTINCT FROM new.target_margin_bps
    OR old.min_profit_by_lead_time IS DISTINCT FROM new.min_profit_by_lead_time
    OR old.demand_curve IS DISTINCT FROM new.demand_curve
    OR old.is_active IS DISTINCT FROM new.is_active
)
EXECUTE FUNCTION price_rules_audit_trigger();

-- Deliberately not folded into admin_upsert_price_rule (migration 0018):
-- that function's contract is "these are the rule's three values", and
-- every caller must pass all three. Enabling or disabling a rule is a
-- toggle on one row, not an edit of its values — routing it through the
-- upsert would force a screen that only wants to flip a switch to first
-- read and resend three values it may not even be allowed to see.
--
-- SECURITY INVOKER (the default) and auth.uid() rather than a
-- caller-supplied actor, same as migration 0016's admin_set_allotment_cost:
-- the RLS UPDATE policy stays the real enforcement layer, and a denied
-- UPDATE surfaces as NOT FOUND rather than silent success. Disabling the
-- global rule fails earlier and louder than that, on
-- price_rules_global_always_active above.
CREATE FUNCTION admin_set_price_rule_active(rule_id bigint, new_is_active boolean)
RETURNS void
LANGUAGE plpgsql
SET search_path = public
AS $$
BEGIN
    PERFORM set_config('app.actor_id', auth.uid()::text, true);
    UPDATE price_rules SET is_active = new_is_active WHERE id = rule_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'not permitted to change this price rule' USING ERRCODE = '42501';
    END IF;
END;
$$;

GRANT EXECUTE ON FUNCTION admin_set_price_rule_active(bigint, boolean) TO authenticated;
