-- Every price quoted to a customer — append-only, per ARCHITECTURE.md §4:
-- "INSERT فقط — لا UPDATE ولا DELETE". Enforced by DB grant, not
-- application discipline (CLAUDE.md rule 3: the constraint is the
-- authority) — service_role is never granted UPDATE or DELETE on this
-- table, so an attempt to alter a quote fails at the database regardless
-- of what application code does.
--
-- customer_phone and conversation_id are nullable with no FK: the
-- conversations table this will eventually reference doesn't exist before
-- phase 4.

CREATE TABLE quotes (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    hotel_id bigint NOT NULL,
    room_type_id bigint NOT NULL,
    check_in date NOT NULL,
    check_out date NOT NULL CONSTRAINT quotes_check_out_after_check_in CHECK (check_out > check_in),
    rooms integer NOT NULL CONSTRAINT quotes_rooms_positive CHECK (rooms > 0),
    ask_price_total bigint NOT NULL
    CONSTRAINT quotes_ask_price_non_negative CHECK (ask_price_total >= 0),
    min_allowed_total bigint NOT NULL
    CONSTRAINT quotes_min_allowed_non_negative CHECK (min_allowed_total >= 0),
    CONSTRAINT quotes_min_allowed_not_above_ask CHECK (min_allowed_total <= ask_price_total),
    -- One entry per night: [{date, season_id, ask, min_allowed}, ...].
    nights jsonb NOT NULL,
    negotiation_open boolean NOT NULL,
    customer_phone text,
    conversation_id bigint,
    created_at timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (room_type_id, hotel_id) REFERENCES room_types (id, hotel_id)
);

ALTER TABLE quotes ENABLE ROW LEVEL SECURITY;
ALTER TABLE quotes FORCE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE quotes FROM anon, authenticated;
-- Append-only: SELECT and INSERT only. No UPDATE, no DELETE grant at all.
GRANT SELECT, INSERT ON TABLE quotes TO service_role;
