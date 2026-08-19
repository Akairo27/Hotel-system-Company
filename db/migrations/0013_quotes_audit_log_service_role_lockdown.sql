-- Migration 0012 closed the default-ACL leak for anon/authenticated on
-- every table in public. Verifying it against a real Supabase project
-- surfaced a second, unrelated instance of the identical root cause:
-- service_role itself never had the excess privileges Supabase's own
-- default ACL grants on every new table explicitly revoked -- migrations
-- 0008 and 0011 only ever explicitly granted the SELECT/INSERT
-- service_role was meant to have, never revoked the rest. Confirmed
-- empirically, not assumed: has_table_privilege showed service_role
-- holds UPDATE and DELETE on both quotes and audit_log today, despite
-- both being documented -- and, for quotes, required by CLAUDE.md rule 3
-- -- as append-only. The local suite's own
-- test_quotes_is_append_only_*_rejected
-- (tests/integration/test_schema_constraints.py) and
-- test_audit_log_is_append_only_*_rejected
-- (tests/integration/test_audit_log_rls.py) pass locally regardless, for
-- the same reason migration 0012's local-vs-Supabase divergence exists
-- throughout this repo's tests: local Postgres never had Supabase's
-- default-ACL provisioning applied, so it was never vulnerable to this
-- leak in the first place -- those tests only ever verified the explicit
-- GRANT was correct, never that no implicit one also existed.

REVOKE UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER ON TABLE quotes FROM service_role;
REVOKE UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER ON TABLE audit_log FROM service_role;

-- Closing this straightforwardly would also close the only path a future
-- right-to-erasure request has: zeroing quotes.customer_phone for a
-- given phone number, the mechanism ARCHITECTURE.md §10 describes.
-- Rather than leave service_role's UPDATE open again -- which is what
-- created this gap the first time, a broad grant nobody meant to give --
-- the exception is a single-purpose SECURITY DEFINER function: it can
-- only ever set customer_phone to NULL for rows matching the phone it's
-- given, never touch any other column, never delete a row. Same
-- SECURITY DEFINER + fixed search_path pattern as current_app_role()/
-- current_user_can_view_cost() (migration 0010) -- runs as its owner
-- (postgres), pinned search_path stops a caller shadowing "quotes" with
-- an object earlier on their own search_path. Migration 0012's global
-- function-default lockdown already denies EXECUTE to anon/authenticated
-- on this function by default (no extra REVOKE needed here) -- the one
-- explicit GRANT below is the only access path, and it is service_role
-- only, matching how role/permission changes already only ever go
-- through a service_role Next.js Server Action (migration 0010's design
-- notes), never a client-side write. Returns the number of rows it
-- actually touched, so a caller can tell a real erasure apart from a
-- phone number that matched nothing.

CREATE FUNCTION quotes_erase_customer_phone(target_phone text) RETURNS bigint
LANGUAGE sql
SECURITY DEFINER
SET search_path = public
AS $$
    WITH erased AS (
        UPDATE quotes
        SET customer_phone = NULL
        WHERE customer_phone = target_phone
        RETURNING 1
    )
    SELECT count(*) FROM erased
$$;

GRANT EXECUTE ON FUNCTION quotes_erase_customer_phone(text) TO service_role;

-- audit_log has no customer-identifying column today -- structure only
-- (migration 0011), nothing writes to it yet -- so it gets no equivalent
-- function. Nothing to erase there until something actually logs
-- personal data into old_value/new_value, a decision for whichever PR
-- does that, not invented here.
