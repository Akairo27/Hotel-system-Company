-- Widens 0019's audit_log allow-list to cover price_overrides' three
-- columns. Migration 0021's write path (admin_upsert_price_overrides)
-- writes ask_price_override/min_allowed_override/expires_at into
-- audit_log the same way price_rules' trigger does — without this, an
-- admin without can_view_cost would be unable to see price_overrides'
-- audit history at all, despite 0021's own decision that none of these
-- three columns are cost-sensitive (they are final prices, not a margin
-- or profit floor). Same posture as 0019: closed in the same PR that
-- widens audit_log's writers, not deferred, and keyed on the
-- (table_name, column_name) pair rather than column_name alone for the
-- same collision-safety reason 0019 gives.
ALTER POLICY audit_log_select_admin_only ON audit_log
USING (
    current_app_role() = 'admin'
    AND (
        current_user_can_view_cost()
        OR (table_name, column_name) IN (
            ('app_users', 'app_role'),
            ('app_users', 'can_view_cost'),
            ('price_rules', 'demand_curve'),
            ('price_rules', 'is_active'),
            ('price_overrides', 'ask_price_override'),
            ('price_overrides', 'min_allowed_override'),
            ('price_overrides', 'expires_at')
        )
    )
);
