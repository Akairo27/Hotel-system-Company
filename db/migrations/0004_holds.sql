-- Temporary holds. No status column: status is derived from expires_at,
-- released_at, and confirmed_at, so it can never drift out of sync with the
-- timestamps that actually drive worker and confirmation behaviour.

CREATE TABLE holds (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    hotel_id bigint NOT NULL,
    room_type_id bigint NOT NULL,
    check_in date NOT NULL,
    check_out date NOT NULL CONSTRAINT holds_check_out_after_check_in CHECK (check_out > check_in),
    rooms integer NOT NULL CONSTRAINT holds_rooms_positive CHECK (rooms > 0),
    expires_at timestamptz NOT NULL,
    released_at timestamptz,
    confirmed_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    -- Matches the (room_type_id, hotel_id) pair against room_types, so a
    -- hold can never be recorded against a room type from another hotel.
    FOREIGN KEY (room_type_id, hotel_id) REFERENCES room_types (id, hotel_id),
    CONSTRAINT holds_not_released_and_confirmed CHECK (released_at IS NULL OR confirmed_at IS NULL)
);

ALTER TABLE holds ENABLE ROW LEVEL SECURITY;
ALTER TABLE holds FORCE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE holds FROM anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE holds TO service_role;
