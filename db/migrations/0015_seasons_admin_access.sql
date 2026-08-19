-- Grants the admin dashboard access to seasons, deferred by migration 0001
-- the same way hotels/room_types were until migration 0014. Same shape as
-- 0014: read access is open to any active app_users row (sales needs to see
-- season boundaries while quoting), writes (INSERT/UPDATE) are admin-only,
-- gated by current_app_role() (migration 0010). No DELETE grant at all —
-- a deleted season could silently reclassify already-quoted stay dates onto
-- a different price_rules scope; that decision is deferred out of this
-- migration, same as hotels/room_types. Only service_role can delete a row
-- today, same as before this migration.

GRANT SELECT, INSERT, UPDATE ON TABLE seasons TO authenticated;

CREATE POLICY seasons_select_for_active_users ON seasons
FOR SELECT TO authenticated
USING (current_app_role() IS NOT NULL);

CREATE POLICY seasons_insert_for_admin ON seasons
FOR INSERT TO authenticated
WITH CHECK (current_app_role() = 'admin');

CREATE POLICY seasons_update_for_admin ON seasons
FOR UPDATE TO authenticated
USING (current_app_role() = 'admin')
WITH CHECK (current_app_role() = 'admin');
