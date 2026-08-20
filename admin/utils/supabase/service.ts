import { createClient as createSupabaseClient } from "@supabase/supabase-js";

// service_role bypasses RLS entirely (CLAUDE.md rule 9: this key never
// leaves the server). Only ever import this module from a "use server"
// Server Action file — Next.js never bundles "use server" modules or their
// imports into client code, which is what actually keeps this key off the
// browser, not just naming convention. Never construct this client with a
// user-supplied value; every call site must independently re-check the
// caller's own role via getCurrentAppUser() first (see admin/app/users/
// actions.ts), the same defense-in-depth every other write in this
// dashboard already applies.
//
// SUPABASE_SERVICE_ROLE_KEY is deliberately unprefixed (no NEXT_PUBLIC_) —
// Next.js only inlines NEXT_PUBLIC_* variables into the client bundle, so
// this name is server-only by construction, on top of never being
// committed (see admin/.gitignore's .env* rule).
export function createServiceRoleClient() {
  return createSupabaseClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.SUPABASE_SERVICE_ROLE_KEY!,
    { auth: { autoRefreshToken: false, persistSession: false } },
  );
}
