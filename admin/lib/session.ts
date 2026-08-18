import { createClient } from "@/utils/supabase/server";
import type { AppUser } from "@/lib/types";

// Reads the signed-in user's own app_users row through the request's own
// RLS-scoped client — never through a service_role client, so this can
// never accidentally return someone else's row. Returns null both when
// nobody is signed in and when a signed-in auth.users identity has no
// matching app_users row yet (an admin must provision one before the
// person can use the dashboard at all).
export async function getCurrentAppUser(): Promise<AppUser | null> {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) {
    return null;
  }

  const { data } = await supabase
    .from("app_users")
    .select("id, full_name, role, can_view_cost, is_active, created_at")
    .eq("id", user.id)
    .maybeSingle<AppUser>();

  return data;
}
