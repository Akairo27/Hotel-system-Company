import { createServerClient } from "@supabase/ssr";
import { cookies } from "next/headers";

// One client per request, built with the caller's own session cookies —
// every query this client makes is subject to that user's RLS policies,
// same as the anon-key browser client. Server Actions that must bypass
// RLS (role changes in phase-3 PR D) use a separate service_role client
// that is never exported from a file reachable by client components.
export async function createClient() {
  const cookieStore = await cookies();

  return createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      cookies: {
        getAll() {
          return cookieStore.getAll();
        },
        setAll(cookiesToSet) {
          try {
            cookiesToSet.forEach(({ name, value, options }) =>
              cookieStore.set(name, value, options),
            );
          } catch {
            // Called from a Server Component, which cannot write cookies.
            // Harmless as long as middleware.ts is refreshing the session
            // on every request, which it does.
          }
        },
      },
    },
  );
}
