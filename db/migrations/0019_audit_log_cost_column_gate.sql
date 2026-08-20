-- audit_log's read policy (migration 0011) gates on role alone —
-- current_app_role() = 'admin', with no can_view_cost check at all. That
-- was already one gap too wide the moment migration 0016 started writing
-- allotments.cost_per_night old/new values into this table: an admin
-- whose can_view_cost is false could read there exactly the number
-- ARCHITECTURE.md §8's masking view exists to keep from them.
--
-- Migration 0018 widens it further — price_rules' audit trigger writes
-- target_margin_bps and min_profit_by_lead_time here too, and a margin
-- reverse-derives cost from a price the same way every other masked
-- column in this schema does. Closed here, in the round that widened it,
-- rather than deferred: the request that adds a second masked column pays
-- for making the audit trail honor the same masking rule.
--
-- An explicit allow-list of the non-sensitive columns, not a deny-list of
-- the sensitive ones — deliberately inverted from this migration's first
-- draft. Same posture as migration 0012 (deny by default on public,
-- explicit grant for what's safe): a future financial audit column that
-- nobody remembers to add to this policy stays hidden until it is added,
-- not exposed until someone remembers to block it. The asymmetry is
-- intentional — an admin missing a row they should see complains and gets
-- noticed quickly; a cost figure leaking to someone who shouldn't see it
-- complains to no one. Fails closed, not open.
--
-- Keyed on the pair (table_name, column_name), not column_name alone:
-- audit_log is a shared table serving multiple sources, and a future
-- financial table's column that happens to share a name with one of these
-- four (is_active, demand_curve, ...) would leak automatically under a
-- name-only match. Matching the pair closes that off.
ALTER POLICY audit_log_select_admin_only ON audit_log
USING (
    current_app_role() = 'admin'
    AND (
        current_user_can_view_cost()
        OR (table_name, column_name) IN (
            ('app_users', 'app_role'),
            ('app_users', 'can_view_cost'),
            ('price_rules', 'demand_curve'),
            ('price_rules', 'is_active')
        )
    )
);
