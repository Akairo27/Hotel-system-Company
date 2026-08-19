import { createBrowserClient } from "@supabase/ssr";

// Only ever constructed with the anon key — RLS is what limits what this
// client can read or write, never the key itself. service_role never
// reaches browser code (CLAUDE.md rule 9).
export function createClient() {
  return createBrowserClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
  );
}
