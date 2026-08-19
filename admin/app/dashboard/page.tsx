import Link from "next/link";
import { redirect } from "next/navigation";
import { getCurrentAppUser } from "@/lib/session";

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
      <nav>
        <Link href="/hotels">الفنادق وأنواع الغرف</Link>
      </nav>
    </main>
  );
}
