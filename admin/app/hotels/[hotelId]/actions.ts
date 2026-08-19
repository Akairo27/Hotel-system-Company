"use server";

import { redirect } from "next/navigation";
import { createClient } from "@/utils/supabase/server";
import { getCurrentAppUser } from "@/lib/session";

function hotelPath(hotelId: number): string {
  return `/hotels/${hotelId}`;
}

function redirectWithError(hotelId: number, message: string): never {
  redirect(hotelPath(hotelId) + "?error=" + encodeURIComponent(message));
}

// See admin/app/hotels/actions.ts's requireAdmin for why a Server Action
// re-checks the role itself instead of trusting that only an admin ever
// saw the form that submits to it.
async function requireAdmin(hotelId: number): Promise<void> {
  const appUser = await getCurrentAppUser();
  if (!appUser || appUser.app_role !== "admin") {
    redirectWithError(hotelId, "هذا الإجراء يتطلب صلاحية المدير.");
  }
}

function readRoomTypeName(hotelId: number, formData: FormData): string {
  const roomTypeName = formData.get("room_type_name");
  if (typeof roomTypeName !== "string" || roomTypeName.trim() === "") {
    redirectWithError(hotelId, "اسم نوع الغرفة مطلوب.");
  }
  return roomTypeName.trim();
}

export async function createRoomType(hotelId: number, formData: FormData): Promise<void> {
  await requireAdmin(hotelId);
  const roomTypeName = readRoomTypeName(hotelId, formData);

  const supabase = await createClient();
  const { error } = await supabase
    .from("room_types")
    .insert({ hotel_id: hotelId, room_type_name: roomTypeName });
  if (error) {
    redirectWithError(hotelId, error.message);
  }
  redirect(hotelPath(hotelId));
}

export async function renameRoomType(
  hotelId: number,
  roomTypeId: number,
  formData: FormData,
): Promise<void> {
  await requireAdmin(hotelId);
  const roomTypeName = readRoomTypeName(hotelId, formData);

  const supabase = await createClient();
  // Same zero-rows-not-an-error RLS behavior as hotels/actions.ts's
  // renameHotel — see the comment there.
  const { data, error } = await supabase
    .from("room_types")
    .update({ room_type_name: roomTypeName })
    .eq("id", roomTypeId)
    .select("id");
  if (error) {
    redirectWithError(hotelId, error.message);
  }
  if (!data || data.length === 0) {
    redirectWithError(hotelId, "غير مصرح لك بتعديل نوع الغرفة هذا.");
  }
  redirect(hotelPath(hotelId));
}
