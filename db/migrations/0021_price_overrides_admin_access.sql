-- Admin/sales access to price_overrides (migration 0007), deferred by that
-- migration for exactly this reason. compute_quote's _fetch_active_override
-- (services/pricing/compute.py) already reads this table — this migration
-- is the write side, which never existed until now. compute.py itself is
-- untouched.
--
-- Unlike price_rules (0018), none of this table's three writable columns
-- reverse-derive cost: ask_price_override and min_allowed_override are
-- final prices, not a margin or a profit floor over cost, and expires_at is
-- a timestamp. None of them go behind current_user_can_view_cost() — sales
-- needs to see and act on these values the same as any other quote input.
-- This is why this migration needs no masking VIEW at all, unlike
-- price_rules_for_dashboard / allotments_for_dashboard: there is nothing
-- here to mask, so the table-level SELECT grant below is unconditional.
--
-- Write access is admin-only for now (current_app_role() = 'admin'), by
-- explicit decision, not yet extended to sales. The extension point is
-- this one clause in the two write policies below — nothing else in this
-- migration's design needs to change to widen it later.
--
-- No DELETE grant, matching hotels/room_types/seasons/price_rules. Unlike
-- price_rules, a stray or wrong-range price_overrides row is genuinely
-- harmless once ended: _fetch_active_override already filters
-- `WHERE expires_at > %s` (now), so an expired row has zero effect on any
-- future quote — it does not keep shadowing an inheritance chain the way a
-- wrong-scope, still-active price_rules row does. "Ending" an override
-- early is therefore just setting expires_at to now or earlier through the
-- same write path as everything else here — no separate is_active column,
-- no separate "end" RPC.

GRANT SELECT ON TABLE price_overrides TO authenticated;
GRANT INSERT (
    hotel_id, room_type_id, stay_date, ask_price_override, min_allowed_override, expires_at
) ON TABLE price_overrides TO authenticated;
GRANT UPDATE (ask_price_override, min_allowed_override, expires_at)
ON TABLE price_overrides TO authenticated;

-- Row visibility, not value masking — same FORCE ROW LEVEL SECURITY
-- deny-by-default reasoning as every other admin-access migration
-- (0014/0015/0016/0018). Confirmed empirically this session (not assumed)
-- that admin_upsert_price_overrides' ON CONFLICT DO UPDATE below also
-- depends on this policy to see a pre-existing conflicting row, the same
-- class of gotcha 0016/0018 found for an explicit UPDATE ... WHERE — see
-- that function's own comment.
CREATE POLICY price_overrides_select_for_active_users ON price_overrides
FOR SELECT TO authenticated
USING (current_app_role() IS NOT NULL);

CREATE POLICY price_overrides_insert_for_admin ON price_overrides
FOR INSERT TO authenticated
WITH CHECK (current_app_role() = 'admin');

CREATE POLICY price_overrides_update_for_admin ON price_overrides
FOR UPDATE TO authenticated
USING (current_app_role() = 'admin')
WITH CHECK (current_app_role() = 'admin');

-- One audit_log row per changed column, same shape as price_rules_audit_trigger
-- (0018/0020). SECURITY DEFINER for the same reason: this table's write
-- path runs as authenticated, which holds SELECT but not INSERT on
-- audit_log. Two triggers, not one, for the same reason 0018 gives: an
-- INSERT trigger's WHEN clause cannot reference OLD.
CREATE FUNCTION price_overrides_audit_trigger() RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    actor uuid := current_actor_id();
    prev price_overrides;
BEGIN
    IF actor IS NULL THEN
        RAISE EXCEPTION 'app.actor_id must be set before writing price_overrides';
    END IF;
    IF TG_OP = 'UPDATE' THEN
        prev := old;
    END IF;
    IF new.ask_price_override IS DISTINCT FROM prev.ask_price_override THEN
        INSERT INTO audit_log (table_name, row_id, column_name, old_value, new_value, changed_by)
        VALUES (
            'price_overrides',
            new.id::text,
            'ask_price_override',
            to_jsonb(prev.ask_price_override),
            to_jsonb(new.ask_price_override),
            actor
        );
    END IF;
    IF new.min_allowed_override IS DISTINCT FROM prev.min_allowed_override THEN
        INSERT INTO audit_log (table_name, row_id, column_name, old_value, new_value, changed_by)
        VALUES (
            'price_overrides',
            new.id::text,
            'min_allowed_override',
            to_jsonb(prev.min_allowed_override),
            to_jsonb(new.min_allowed_override),
            actor
        );
    END IF;
    IF new.expires_at IS DISTINCT FROM prev.expires_at THEN
        INSERT INTO audit_log (table_name, row_id, column_name, old_value, new_value, changed_by)
        VALUES (
            'price_overrides',
            new.id::text,
            'expires_at',
            to_jsonb(prev.expires_at),
            to_jsonb(new.expires_at),
            actor
        );
    END IF;
    RETURN new;
END;
$$;

CREATE TRIGGER price_overrides_audit_insert
AFTER INSERT ON price_overrides
FOR EACH ROW
EXECUTE FUNCTION price_overrides_audit_trigger();

CREATE TRIGGER price_overrides_audit_update
AFTER UPDATE ON price_overrides
FOR EACH ROW
WHEN (
    old.ask_price_override IS DISTINCT FROM new.ask_price_override
    OR old.min_allowed_override IS DISTINCT FROM new.min_allowed_override
    OR old.expires_at IS DISTINCT FROM new.expires_at
)
EXECUTE FUNCTION price_overrides_audit_trigger();

-- The only supported write path: one call creates or overwrites one row
-- per night in [p_start_date, p_end_date], matching the admin screen's
-- date-range design (not a single night at a time). SECURITY INVOKER (the
-- default), same reasoning as every other write RPC in this dashboard —
-- the policies above stay the real enforcement layer, and auth.uid() is
-- trustworthy here precisely because the function runs as the caller.
--
-- ON CONFLICT DO UPDATE, not price_rules' UPDATE-then-INSERT pattern
-- (0018): that pattern exists there specifically because granting SELECT
-- on price_rules' value columns to authenticated would let its masking be
-- bypassed by querying the base table directly — "DO UPDATE SET col =
-- excluded.col" requires a SELECT grant on col, confirmed empirically in
-- that PR. Neither problem applies here — this table has no masked column,
-- so the table-level SELECT grant above is already unconditional — so
-- ON CONFLICT DO UPDATE is the natural, atomic, single-statement way to
-- express "create or overwrite every night in this range."
--
-- Confirmed empirically this session (local Postgres, not assumed) that
-- this statement also needs price_overrides_select_for_active_users above
-- — and the failure mode is broader than 0016/0018's gotcha, not the same
-- shape: without a FOR SELECT policy, Postgres denies the whole
-- INSERT ... ON CONFLICT DO UPDATE outright ("new row violates row-level
-- security policy"), even when every row being inserted is brand new and
-- no actual conflict occurs. 0016/0018's UPDATE ... WHERE gotcha only bit
-- when a targeted row genuinely existed; this one bites unconditionally,
-- the moment an ON CONFLICT DO UPDATE clause is present at all, because
-- Postgres's RLS planning for that clause always requires the table's
-- SELECT policy to be satisfiable. Verified both directions: stripping the
-- policy makes even a first, non-conflicting 3-night insert fail; with it
-- present, both a fresh insert and a second, overlapping-range call that
-- overwrites some nights and creates others succeed and leave exactly the
-- expected values per night.
--
-- The 180-night cap matches admin/lib/priceOverrideRange.ts's
-- MAX_OVERRIDE_RANGE_NIGHTS exactly; that client-side check is the primary
-- guard (a live per-keystroke night counter in the form), this RAISE is
-- the server-side backstop — same defense-in-depth split as price_rules'
-- band validation (client-side port + DB CHECK).
CREATE FUNCTION admin_upsert_price_overrides(
    p_hotel_id bigint,
    p_room_type_id bigint,
    p_start_date date,
    p_end_date date,
    p_ask_price_override bigint,
    p_min_allowed_override bigint,
    p_expires_at timestamptz
)
RETURNS SETOF bigint
LANGUAGE plpgsql
SET search_path = public
AS $$
BEGIN
    IF p_start_date > p_end_date THEN
        RAISE EXCEPTION 'start date must not be after end date';
    END IF;
    IF p_end_date - p_start_date >= 180 THEN
        RAISE EXCEPTION 'date range must not exceed 180 nights';
    END IF;
    PERFORM set_config('app.actor_id', auth.uid()::text, true);
    RETURN QUERY
    INSERT INTO price_overrides (
        hotel_id, room_type_id, stay_date, ask_price_override, min_allowed_override, expires_at
    )
    SELECT
        p_hotel_id,
        p_room_type_id,
        night::date,
        p_ask_price_override,
        p_min_allowed_override,
        p_expires_at
    FROM generate_series(p_start_date, p_end_date, interval '1 day') AS night
    ON CONFLICT (hotel_id, room_type_id, stay_date)
    DO UPDATE SET
        ask_price_override = excluded.ask_price_override,
        min_allowed_override = excluded.min_allowed_override,
        expires_at = excluded.expires_at
    RETURNING id;
END;
$$;

GRANT EXECUTE ON FUNCTION admin_upsert_price_overrides(
    bigint, bigint, date, date, bigint, bigint, timestamptz
) TO authenticated;
