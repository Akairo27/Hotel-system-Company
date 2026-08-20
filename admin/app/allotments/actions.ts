"use server";

import { redirect } from "next/navigation";
import { createClient } from "@/utils/supabase/server";
import { getCurrentAppUser } from "@/lib/session";

const ALLOTMENTS_PATH = "/allotments";

function redirectWithError(message: string): never {
  redirect(ALLOTMENTS_PATH + "?error=" + encodeURIComponent(message));
}

// Defense-in-depth fast path in front of migration 0016's RLS policy
// (current_app_role() = 'admin' AND current_user_can_view_cost()), which
// remains the real enforcement layer — same pattern as every other write
// in this dashboard.
async function requireAdminWithCostVisibility(): Promise<void> {
  const appUser = await getCurrentAppUser();
  if (!appUser || appUser.app_role !== "admin" || !appUser.can_view_cost) {
    redirectWithError("هذا الإجراء يتطلب صلاحية المدير وصلاحية عرض التكلفة معاً.");
  }
}

export async function updateAllotmentCost(
  allotmentId: number,
  formData: FormData,
): Promise<void> {
  await requireAdminWithCostVisibility();
  const rawCost = formData.get("cost_per_night");
  const costPerNight = Number(rawCost);
  if (!Number.isInteger(costPerNight) || costPerNight < 0) {
    redirectWithError("التكلفة يجب أن تكون رقماً صحيحاً غير سالب (بالهللة).");
  }

  // The wrapper RPC, not a plain .update() — migration 0016's audit
  // trigger rejects any write to cost_per_night that does not go through
  // it (app.actor_id is only ever set inside admin_set_allotment_cost).
  const supabase = await createClient();
  const { error } = await supabase.rpc("admin_set_allotment_cost", {
    allotment_id: allotmentId,
    new_cost_per_night: costPerNight,
  });
  if (error) {
    redirectWithError(error.message);
  }
  redirect(ALLOTMENTS_PATH);
}
