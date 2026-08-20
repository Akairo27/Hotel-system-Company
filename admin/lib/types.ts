// Mirrors db/migrations pending 0010_app_users_and_roles.sql (see
// docs/phase-3-pr-a/README.md). Hand-maintained until `supabase gen types
// typescript` is run against the applied schema — that command needs a
// linked Supabase project and network access neither of which this
// session's permissions allow, so this is not yet auto-generated.
export type AppRole = "admin" | "sales";

export interface AppUser {
  id: string;
  full_name: string;
  app_role: AppRole;
  can_view_cost: boolean;
  is_active: boolean;
  created_at: string;
}

// Mirrors db/migrations/0001_hotels_room_types.sql. Neither table carries a
// cost column, so unlike AppUser there is no ARCHITECTURE.md §8 masking
// concern here.
export interface Hotel {
  id: number;
  hotel_name: string;
  created_at: string;
}

export interface RoomType {
  id: number;
  hotel_id: number;
  room_type_name: string;
  created_at: string;
}

// Mirrors db/migrations/0002_seasons.sql. resolve_season_id
// (services/pricing/seasons.py) ignores a default row's own start/end
// entirely and falls back to it whenever no non-default season matches —
// its bounds exist only to satisfy the NOT NULL columns, never rendered.
export type CalendarType = "hijri" | "gregorian";

export interface Season {
  id: number;
  season_name: string;
  calendar_type: CalendarType;
  start_month: number;
  start_day: number;
  end_month: number;
  end_day: number;
  priority: number;
  is_default: boolean;
  created_at: string;
}

// Mirrors db/migrations/0016_allotments_cost_masking.sql's
// allotments_for_dashboard VIEW, not the allotments table itself —
// cost_per_night is null whenever the querying user's can_view_cost is
// false (ARCHITECTURE.md §8), so this type reflects that directly instead
// of pretending the column is always present.
export interface AllotmentForDashboard {
  id: number;
  hotel_id: number;
  room_type_id: number;
  stay_date: string;
  total_rooms: number;
  cost_per_night: number | null;
  created_at: string;
}

// Mirrors db/migrations/0006_price_rules.sql's jsonb band shapes, and the
// validation admin/lib/priceRuleBands.ts enforces client-side against the
// same shapes (see that module's own comment for the split between what
// Postgres's CHECK constraints guarantee and what this port additionally
// diagnoses). A band's max is null only in a lead-time chain's terminal,
// open-ended band — never in an occupancy chain, which is closed at 1.
export interface MinProfitBand {
  min_lead_days: number;
  max_lead_days: number | null;
  min_profit_halalas: number;
}

export interface MinProfitByLeadTime {
  bands: MinProfitBand[];
}

export interface DemandLeadTimeBand {
  min_lead_days: number;
  max_lead_days: number | null;
  multiplier_bps: number;
}

export interface OccupancyBand {
  min: number;
  max: number;
  multiplier_bps: number;
}

export interface DemandCurve {
  occupancy_bands: OccupancyBand[];
  lead_time_bands: DemandLeadTimeBand[];
}

export type PriceRuleScope = "global" | "season" | "hotel" | "room_type";

// Mirrors db/migrations/0018_price_rules_admin_access.sql's (and 0020's)
// price_rules_for_dashboard VIEW, not the price_rules table itself —
// target_margin_bps and min_profit_by_lead_time are null whenever the
// querying user's can_view_cost is false, the same masking shape as
// AllotmentForDashboard above; demand_curve and is_active carry no cost
// signal and are always present.
export interface PriceRuleForDashboard {
  id: number;
  scope: PriceRuleScope;
  scope_id: number | null;
  demand_curve: DemandCurve;
  created_at: string;
  is_active: boolean;
  target_margin_bps: number | null;
  min_profit_by_lead_time: MinProfitByLeadTime | null;
}
