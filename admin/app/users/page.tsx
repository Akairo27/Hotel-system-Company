import Link from "next/link";
import { redirect } from "next/navigation";
import { createClient } from "@/utils/supabase/server";
import { getCurrentAppUser } from "@/lib/session";
import type { AppUser } from "@/lib/types";
import { updateAppRole, updateCanViewCost } from "./actions";

export default async function UsersPage({
  searchParams,
}: {
  searchParams: Promise<{ error?: string }>;
}) {
  const { error } = await searchParams;
  const appUser = await getCurrentAppUser();
  if (!appUser) {
    redirect("/login?error=" + encodeURIComponent("لا يوجد حساب مرتبط بهذا الدخول."));
  }
  if (appUser.app_role !== "admin") {
    redirect("/dashboard");
  }

  const supabase = await createClient();
  const { data: users } = await supabase
    .from("app_users")
    .select("id, full_name, app_role, can_view_cost, is_active, created_at")
    .order("full_name")
    .overrideTypes<AppUser[], { merge: false }>();

  return (
    <main>
      <p>
        <Link href="/dashboard">&larr; لوحة التحكم</Link>
      </p>
      <h1>الصلاحيات</h1>
      {error && <p role="alert">{error}</p>}
      <p>كل تغيير هنا يُسجَّل في سجل التغييرات — من غيّر، ماذا، ومتى.</p>
      <ul>
        {(users ?? []).map((user) => (
          <li key={user.id}>
            <strong>{user.full_name}</strong>
            {!user.is_active && " (غير نشط)"}
            <RoleForm user={user} />
            <CanViewCostForm user={user} />
          </li>
        ))}
      </ul>
    </main>
  );
}

function RoleForm({ user }: { user: AppUser }) {
  const updateThisUsersRole = updateAppRole.bind(null, user.id);
  const nextRole = user.app_role === "admin" ? "sales" : "admin";
  return (
    <form action={updateThisUsersRole}>
      <input type="hidden" name="app_role" value={nextRole} />
      <button type="submit">
        الدور: {user.app_role} — تحويل إلى {nextRole}
      </button>
    </form>
  );
}

function CanViewCostForm({ user }: { user: AppUser }) {
  const updateThisUsersCostVisibility = updateCanViewCost.bind(null, user.id);
  const nextValue = user.can_view_cost ? "false" : "true";
  return (
    <form action={updateThisUsersCostVisibility}>
      <input type="hidden" name="can_view_cost" value={nextValue} />
      <button type="submit">
        عرض التكلفة: {user.can_view_cost ? "مفعّل" : "غير مفعّل"} —{" "}
        {user.can_view_cost ? "إلغاء" : "تفعيل"}
      </button>
    </form>
  );
}
