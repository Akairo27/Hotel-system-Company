-- quotes.nights must carry enough detail to answer "why was this priced
-- this way" from the record itself, months later — not from guessing.
-- Enforced at save time, not left to application discipline: the same
-- reasoning as db/migrations/0006_price_rules.sql's band validation.
--
-- Each element of nights is one of two shapes:
--   - override_applied = true: a manual override was used verbatim, so
--     there is no margin/demand/floor computation to report beyond the
--     date, season, and the two final prices.
--   - override_applied = false: every step of the computation is
--     recorded — the occupancy read at pricing time, which price_rules
--     row supplied each of the three inherited fields (they can be
--     three different rows, per the field-by-field inheritance design),
--     the applied demand factor split into its occupancy and lead-time
--     components, and the price at each step (cost -> after margin ->
--     final ask; cost -> final min_allowed).

CREATE FUNCTION quotes_is_valid_night_record(night jsonb) RETURNS boolean
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT COALESCE(
        jsonb_typeof(night -> 'date') = 'string'
        AND jsonb_typeof(night -> 'season_id') = 'number'
        AND jsonb_typeof(night -> 'ask') = 'number'
        AND jsonb_typeof(night -> 'min_allowed') = 'number'
        AND jsonb_typeof(night -> 'override_applied') = 'boolean'
        AND (
            (night ->> 'override_applied')::boolean
            OR (
                jsonb_typeof(night -> 'cost_per_night') = 'number'
                AND jsonb_typeof(night -> 'occupancy') = 'number'
                AND jsonb_typeof(night -> 'target_margin_bps') = 'number'
                AND jsonb_typeof(night -> 'target_margin_rule_id') = 'number'
                AND jsonb_typeof(night -> 'price_after_margin') = 'number'
                AND jsonb_typeof(night -> 'occupancy_multiplier_bps') = 'number'
                AND jsonb_typeof(night -> 'lead_time_multiplier_bps') = 'number'
                AND jsonb_typeof(night -> 'demand_factor_bps') = 'number'
                AND jsonb_typeof(night -> 'demand_curve_rule_id') = 'number'
                AND jsonb_typeof(night -> 'min_profit_halalas') = 'number'
                AND jsonb_typeof(night -> 'min_profit_rule_id') = 'number'
            )
        ),
        false
    )
$$;

-- A table-level CHECK cannot contain a bare subquery (only a scalar
-- function call), even one that only unnests the row's own column —
-- confirmed empirically: ALTER TABLE ... ADD CONSTRAINT with a NOT
-- EXISTS (SELECT ...) directly in it raises "cannot use subquery in
-- check constraint". Wrapping the per-array iteration in its own
-- function, same as quotes_is_valid_night_record above, is what makes
-- it a plain function call from the constraint's point of view.
CREATE FUNCTION quotes_all_nights_are_complete(nights jsonb) RETURNS boolean
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT
        jsonb_typeof(nights) = 'array'
        AND jsonb_array_length(nights) > 0
        AND NOT EXISTS (
            SELECT 1 FROM jsonb_array_elements(nights) AS night
            WHERE NOT quotes_is_valid_night_record(night)
        )
$$;

ALTER TABLE quotes ADD CONSTRAINT quotes_nights_are_complete CHECK (
    quotes_all_nights_are_complete(nights)
);
