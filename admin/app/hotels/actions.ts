"use server";

import { redirect } from "next/navigation";
import { createClient } from "@/utils/supabase/server";
import { getCurrentAppUser } from "@/lib/session";

const HOTELS_PATH = "/hotels";

function redirectWithError(message: string): never {
  redirect(HOTELS_PATH + "?error=" + encodeURIComponent(message));
}

// Render-time gating (hiding the form for a non-admin) is not a security
// boundary on its own — a request can reach a Server Action without going
// through the UI — so every write here re-checks the role itself. The RLS
// policies added by migration 0014 are the real, DB-level backstop; this
// is the friendly-error fast path in front of them.
async function requireAdmin(): Promise<void> {
  const appUser = await getCurrentAppUser();
  if (!appUser || appUser.app_role !== "admin") {
    redirectWithError("هذا الإجراء يتطلب صلاحية المدير.");
  }
}

function readHotelName(formData: FormData): string {
  const hotelName = formData.get("hotel_name");
  if (typeof hotelName !== "string" || hotelName.trim() === "") {
    redirectWithError("اسم الفندق مطلوب.");
  }
  return hotelName.trim();
}

export async function createHotel(formData: FormData): Promise<void> {
  await requireAdmin();
  const hotelName = readHotelName(formData);

  const supabase = await createClient();
  const { error } = await supabase.from("hotels").insert({ hotel_name: hotelName });
  if (error) {
    redirectWithError(error.message);
  }
  redirect(HOTELS_PATH);
}

export async function renameHotel(hotelId: number, formData: FormData): Promise<void> {
  await requireAdmin();
  const hotelName = readHotelName(formData);

  const supabase = await createClient();
  // Unlike INSERT's WITH CHECK, a denied UPDATE does not raise a Postgres
  // error — RLS's admin-only USING clause just filters the row out of the
  // update, so it matches zero rows silently instead. requireAdmin() above
  // already covers the normal case; this is the DB-level layer underneath
  // it, verified in tests/integration/test_hotels_room_types_rls.py.
  const { data, error } = await supabase
    .from("hotels")
    .update({ hotel_name: hotelName })
    .eq("id", hotelId)
    .select("id");
  if (error) {
    redirectWithError(error.message);
  }
  if (!data || data.length === 0) {
    redirectWithError("غير مصرح لك بتعديل هذا الفندق.");
  }
  redirect(HOTELS_PATH);
}
