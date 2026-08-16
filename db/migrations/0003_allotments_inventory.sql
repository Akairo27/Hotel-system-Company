-- allotments: the rooms a hotel commits to selling through us for one room
-- type on one date, and their cost (integer halalas — never a float).
--
-- room_night_inventory: the atomic unit ARCHITECTURE.md describes. Its
-- primary key is the natural (allotment_id, stay_date) pair — no surrogate
-- id — because every row exists only in relation to one allotment on one
-- date.
--
-- Column name note: ARCHITECTURE.md names this column "date". It is spelled
-- "stay_date" here because sqlfluff's default ruleset rejects both a bare
-- and a quoted "date" identifier (RF04 and RF06 disagree on the same word),
-- and CLAUDE.md forbids silencing a lint rule to route around that.

CREATE TABLE allotments (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    hotel_id bigint NOT NULL REFERENCES hotels (id),
    room_type_id bigint NOT NULL REFERENCES room_types (id),
    stay_date date NOT NULL,
    total_rooms integer NOT NULL
    CONSTRAINT allotments_total_rooms_non_negative CHECK (total_rooms >= 0),
    cost_per_night bigint NOT NULL
    CONSTRAINT allotments_cost_non_negative CHECK (cost_per_night >= 0),
    created_at timestamptz NOT NULL DEFAULT now(),
    -- One allotment per hotel/room-type/night — never two conflicting
    -- totals or costs for the same night.
    UNIQUE (hotel_id, room_type_id, stay_date),
    -- Lets room_night_inventory reference (allotment_id, stay_date) as a
    -- composite foreign key, so its date can never diverge from the
    -- allotment it belongs to.
    UNIQUE (id, stay_date)
);

ALTER TABLE allotments ENABLE ROW LEVEL SECURITY;
ALTER TABLE allotments FORCE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE allotments FROM anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE allotments TO service_role;

CREATE TABLE room_night_inventory (
    allotment_id bigint NOT NULL,
    stay_date date NOT NULL,
    total integer NOT NULL
    CONSTRAINT room_night_inventory_total_non_negative CHECK (total >= 0),
    reserved integer NOT NULL DEFAULT 0,
    held integer NOT NULL DEFAULT 0,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (allotment_id, stay_date),
    FOREIGN KEY (allotment_id, stay_date) REFERENCES allotments (id, stay_date),
    -- The last line of defence against double-selling. Never removed,
    -- weakened, or bypassed — see CLAUDE.md rule 4.
    CONSTRAINT inventory_never_oversold
    CHECK (reserved + held <= total AND reserved >= 0 AND held >= 0)
);

ALTER TABLE room_night_inventory ENABLE ROW LEVEL SECURITY;
ALTER TABLE room_night_inventory FORCE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE room_night_inventory FROM anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE room_night_inventory TO service_role;
