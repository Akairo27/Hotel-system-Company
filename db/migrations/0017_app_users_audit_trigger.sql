-- PR D: role and can_view_cost changes on app_users — the first writes to
-- this table since migration 0010 created it SELECT-only for authenticated
-- (to prevent self-escalation, see that migration's own comment). Both
-- still go only through a service_role Server Action; this migration adds
-- an AFTER UPDATE trigger so every change lands in audit_log no matter how
-- it reaches the row — a service_role UPDATE issued outside the wrapper
-- functions below is rejected, not silently unlogged, same reasoning as
-- migration 0016's allotments trigger.
--
-- No SECURITY DEFINER needed on the trigger function itself: every write
-- path to app_users runs as service_role, which already holds SELECT,
-- INSERT on audit_log (migration 0011) — unlike migration 0016's
-- allotments case, there is no privilege gap to cross here.
-- current_actor_id() (migration 0016) handles the app.actor_id-reset-to-
-- empty-string-not-NULL Postgres behavior that a bare current_setting()
-- check misses — see that migration's comment.
CREATE FUNCTION app_users_audit_trigger() RETURNS trigger
LANGUAGE plpgsql
SET search_path = public
AS $$
DECLARE
    actor uuid := current_actor_id();
BEGIN
    IF actor IS NULL THEN
        RAISE EXCEPTION 'app.actor_id must be set before updating app_users role/can_view_cost';
    END IF;
    IF NEW.can_view_cost IS DISTINCT FROM OLD.can_view_cost THEN
        INSERT INTO audit_log (table_name, row_id, column_name, old_value, new_value, changed_by)
        VALUES (
            'app_users',
            NEW.id::text,
            'can_view_cost',
            to_jsonb(OLD.can_view_cost),
            to_jsonb(NEW.can_view_cost),
            actor
        );
    END IF;
    IF NEW.app_role IS DISTINCT FROM OLD.app_role THEN
        INSERT INTO audit_log (table_name, row_id, column_name, old_value, new_value, changed_by)
        VALUES (
            'app_users',
            NEW.id::text,
            'app_role',
            to_jsonb(OLD.app_role),
            to_jsonb(NEW.app_role),
            actor
        );
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER app_users_audit_role_and_cost_visibility
AFTER UPDATE ON app_users
FOR EACH ROW
WHEN (
    OLD.can_view_cost IS DISTINCT FROM NEW.can_view_cost
    OR OLD.app_role IS DISTINCT FROM NEW.app_role
)
EXECUTE FUNCTION app_users_audit_trigger();

-- Wrapper RPCs: the only supported way to change these two columns.
-- SECURITY DEFINER + fixed search_path, same convention as
-- current_app_role()/quotes_erase_customer_phone (migrations 0010/0013) —
-- not because service_role needs the extra privilege (it already holds
-- UPDATE on app_users), but for the same search_path-hijack hygiene this
-- codebase applies to every function reachable only by a trusted caller.
-- actor_id is a parameter here, not auth.uid(), because a service_role
-- session does not carry the acting admin's JWT the way an authenticated
-- session does (unlike migration 0016's allotments path) — the calling
-- Next.js Server Action must derive it from its own getCurrentAppUser()
-- read, server-side, never from client input.
CREATE FUNCTION admin_set_can_view_cost(
    target_user_id uuid, new_can_view_cost boolean, actor_id uuid
)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
    PERFORM set_config('app.actor_id', actor_id::text, true);
    UPDATE app_users SET can_view_cost = new_can_view_cost WHERE id = target_user_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'no such app_users row: %', target_user_id;
    END IF;
END;
$$;

GRANT EXECUTE ON FUNCTION admin_set_can_view_cost(uuid, boolean, uuid) TO service_role;

CREATE FUNCTION admin_set_app_role(target_user_id uuid, new_app_role text, actor_id uuid)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
    PERFORM set_config('app.actor_id', actor_id::text, true);
    UPDATE app_users SET app_role = new_app_role WHERE id = target_user_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'no such app_users row: %', target_user_id;
    END IF;
END;
$$;

GRANT EXECUTE ON FUNCTION admin_set_app_role(uuid, text, uuid) TO service_role;
