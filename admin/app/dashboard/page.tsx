import { redirect } from "next/navigation";
import { getCurrentAppUser } from "@/lib/session";

// Deliberately bare: PR A's job is proving the auth + roles foundation
// works end to end, not building a real screen. The first real screen
// (hotels/room types) is PR B, per the phase-3 decision to land
// permissions before anything they would otherwise have to be retrofitted
// onto.
export default async function DashboardPage() {
  const appUser = await getCurrentAppUser();
  if (!appUser) {
    redirect("/login?error=" + encodeURIComponent("لا يوجد حساب مرتبط بهذا الدخول."));
  }

  return (
    <main>
      <h1>مرحباً، {appUser.full_name}</h1>
      <p>الدور: {appUser.app_role}</p>
      <p>عرض التكلفة: {appUser.can_view_cost ? "مفعّل" : "غير مفعّل"}</p>
    </main>
  );
}
