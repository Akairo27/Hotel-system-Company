-- Grants the admin dashboard access to hotels/room_types, deferred by
-- migration 0001 ("grants for the admin dashboard arrive in phase 3").
-- Read access is open to any active app_users row regardless of role, so
-- sales can see inventory options while quoting; writes are admin-only,
-- gated by current_app_role() (migration 0010). No DELETE grant at all —
-- both tables are FK-referenced by allotments/holds, and deleting either
-- is a separate decision deferred out of this migration; only
-- service_role can delete a row today, same as before this migration.

GRANT SELECT, INSERT, UPDATE ON TABLE hotels TO authenticated;
GRANT SELECT, INSERT, UPDATE ON TABLE room_types TO authenticated;

CREATE POLICY hotels_select_for_active_users ON hotels
FOR SELECT TO authenticated
USING (current_app_role() IS NOT NULL);

CREATE POLICY hotels_insert_for_admin ON hotels
FOR INSERT TO authenticated
WITH CHECK (current_app_role() = 'admin');

CREATE POLICY hotels_update_for_admin ON hotels
FOR UPDATE TO authenticated
USING (current_app_role() = 'admin')
WITH CHECK (current_app_role() = 'admin');

CREATE POLICY room_types_select_for_active_users ON room_types
FOR SELECT TO authenticated
USING (current_app_role() IS NOT NULL);

CREATE POLICY room_types_insert_for_admin ON room_types
FOR INSERT TO authenticated
WITH CHECK (current_app_role() = 'admin');

CREATE POLICY room_types_update_for_admin ON room_types
FOR UPDATE TO authenticated
USING (current_app_role() = 'admin')
WITH CHECK (current_app_role() = 'admin');
