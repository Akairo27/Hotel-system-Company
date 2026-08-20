"use server";

import { redirect } from "next/navigation";
import { getCurrentAppUser } from "@/lib/session";
import { createServiceRoleClient } from "@/utils/supabase/service";
import type { AppRole } from "@/lib/types";

const USERS_PATH = "/users";

function redirectWithError(message: string): never {
  redirect(USERS_PATH + "?error=" + encodeURIComponent(message));
}

// app_users has zero write grant to authenticated at all (migration 0010,
// to prevent a user promoting their own role or flipping their own
// can_view_cost) — every write here goes through service_role instead of
// the request-scoped client every other screen in this dashboard uses.
// Render-time gating is not a security boundary on its own (Next.js's own
// Server Actions guide), so this still re-checks the role itself before
// touching service_role, same as every other write in this dashboard.
async function requireAdmin(): Promise<string> {
  const appUser = await getCurrentAppUser();
  if (!appUser || appUser.app_role !== "admin") {
    redirectWithError("هذا الإجراء يتطلب صلاحية المدير.");
  }
  return appUser.id;
}

export async function updateCanViewCost(
  targetUserId: string,
  formData: FormData,
): Promise<void> {
  const actorId = await requireAdmin();
  const newCanViewCost = formData.get("can_view_cost") === "true";

  const serviceClient = createServiceRoleClient();
  const { error } = await serviceClient.rpc("admin_set_can_view_cost", {
    target_user_id: targetUserId,
    new_can_view_cost: newCanViewCost,
    actor_id: actorId,
  });
  if (error) {
    redirectWithError(error.message);
  }
  redirect(USERS_PATH);
}

export async function updateAppRole(
  targetUserId: string,
  formData: FormData,
): Promise<void> {
  const actorId = await requireAdmin();
  const newAppRole = formData.get("app_role");
  if (newAppRole !== "admin" && newAppRole !== "sales") {
    redirectWithError("دور غير صالح.");
  }
  const validatedRole: AppRole = newAppRole;

  const serviceClient = createServiceRoleClient();
  const { error } = await serviceClient.rpc("admin_set_app_role", {
    target_user_id: targetUserId,
    new_app_role: validatedRole,
    actor_id: actorId,
  });
  if (error) {
    redirectWithError(error.message);
  }
  redirect(USERS_PATH);
}
