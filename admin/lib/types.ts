// Mirrors db/migrations pending 0010_app_users_and_roles.sql (see
// docs/phase-3-pr-a/README.md). Hand-maintained until `supabase gen types
// typescript` is run against the applied schema — that command needs a
// linked Supabase project and network access neither of which this
// session's permissions allow, so this is not yet auto-generated.
export type AppRole = "admin" | "sales";

export interface AppUser {
  id: string;
  full_name: string;
  role: AppRole;
  can_view_cost: boolean;
  is_active: boolean;
  created_at: string;
}
