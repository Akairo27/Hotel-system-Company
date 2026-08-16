-- Hotels and the room types sold within them. No RLS policies are granted
-- here: enabling RLS with zero policies denies every row to anon and
-- authenticated by default. Grants for the admin dashboard arrive in phase 3.
--
-- service_role is the only role our own backend connects as (DATABASE_URL).
-- BYPASSRLS alone does not grant table access, so it also needs schema
-- usage and per-table grants, added alongside each table below.

GRANT USAGE ON SCHEMA public TO service_role;

CREATE TABLE hotels (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    hotel_name text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE hotels ENABLE ROW LEVEL SECURITY;
ALTER TABLE hotels FORCE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE hotels FROM anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE hotels TO service_role;

CREATE TABLE room_types (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    hotel_id bigint NOT NULL REFERENCES hotels (id),
    room_type_name text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    -- Lets holds reference (room_type_id, hotel_id) as a composite foreign
    -- key, so a hold can never be recorded against a mismatched pair.
    UNIQUE (id, hotel_id)
);

ALTER TABLE room_types ENABLE ROW LEVEL SECURITY;
ALTER TABLE room_types FORCE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE room_types FROM anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE room_types TO service_role;
