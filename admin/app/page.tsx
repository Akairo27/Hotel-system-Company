import { redirect } from "next/navigation";

// middleware.ts already gates every non-public path (which "/" is not) on
// having a signed-in user, redirecting anyone else to /login before this
// ever renders — so by the time this runs, the visitor is always signed in
// and the only thing left to decide is where their landing page is.
export default function RootPage() {
  redirect("/dashboard");
}
