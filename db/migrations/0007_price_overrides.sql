-- Manual price overrides. When one is active for a given hotel/room_type
-- night, compute_quote (phase 2 PR B) uses these values directly for that
-- night instead of computing margin/demand/floor — ARCHITECTURE.md §5:
-- "تجاوز يدوي إن وُجد ← يتقدم على الاثنين، لمدة محددة".
--
-- No admin UI to create these exists yet (phase 3 builds it) — this
-- migration and the engine's read-side check are the phase-2 half.

CREATE TABLE price_overrides (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    hotel_id bigint NOT NULL,
    room_type_id bigint NOT NULL,
    stay_date date NOT NULL,
    ask_price_override bigint NOT NULL
    CONSTRAINT price_overrides_ask_price_non_negative CHECK (ask_price_override >= 0),
    min_allowed_override bigint NOT NULL
    CONSTRAINT price_overrides_min_allowed_non_negative CHECK (min_allowed_override >= 0),
    CONSTRAINT price_overrides_min_allowed_not_above_ask CHECK (
        min_allowed_override <= ask_price_override
    ),
    expires_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    -- Matches the (room_type_id, hotel_id) pair against room_types, so an
    -- override can never be recorded against a room type from another hotel.
    FOREIGN KEY (room_type_id, hotel_id) REFERENCES room_types (id, hotel_id),
    -- One active override per hotel/room_type/night — never two conflicting.
    UNIQUE (hotel_id, room_type_id, stay_date)
);

ALTER TABLE price_overrides ENABLE ROW LEVEL SECURITY;
ALTER TABLE price_overrides FORCE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE price_overrides FROM anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE price_overrides TO service_role;
