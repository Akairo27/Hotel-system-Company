import Link from "next/link";
import { notFound, redirect } from "next/navigation";
import { createClient } from "@/utils/supabase/server";
import { getCurrentAppUser } from "@/lib/session";
import type { Hotel, RoomType } from "@/lib/types";
import { createRoomType, renameRoomType } from "./actions";

export default async function HotelRoomTypesPage({
  params,
  searchParams,
}: {
  params: Promise<{ hotelId: string }>;
  searchParams: Promise<{ error?: string }>;
}) {
  const { hotelId } = await params;
  const { error } = await searchParams;
  const hotelIdNum = Number(hotelId);
  if (!Number.isInteger(hotelIdNum)) {
    notFound();
  }

  const appUser = await getCurrentAppUser();
  if (!appUser) {
    redirect("/login?error=" + encodeURIComponent("لا يوجد حساب مرتبط بهذا الدخول."));
  }

  const supabase = await createClient();
  const { data: hotel } = await supabase
    .from("hotels")
    .select("id, hotel_name, created_at")
    .eq("id", hotelIdNum)
    .maybeSingle<Hotel>();
  if (!hotel) {
    notFound();
  }

  const { data: roomTypes } = await supabase
    .from("room_types")
    .select("id, hotel_id, room_type_name, created_at")
    .eq("hotel_id", hotelIdNum)
    .order("room_type_name")
    .overrideTypes<RoomType[], { merge: false }>();

  const isAdmin = appUser.app_role === "admin";

  return (
    <main>
      <p>
        <Link href="/hotels">&larr; الفنادق</Link>
      </p>
      <h1>{hotel.hotel_name}</h1>
      {error && <p role="alert">{error}</p>}
      <h2>أنواع الغرف</h2>
      <ul>
        {(roomTypes ?? []).map((roomType) => (
          <li key={roomType.id}>
            {roomType.room_type_name}
            {isAdmin && <RenameRoomTypeForm hotelId={hotel.id} roomType={roomType} />}
          </li>
        ))}
      </ul>
      {isAdmin && <AddRoomTypeForm hotelId={hotel.id} />}
    </main>
  );
}

function RenameRoomTypeForm({ hotelId, roomType }: { hotelId: number; roomType: RoomType }) {
  const renameThisRoomType = renameRoomType.bind(null, hotelId, roomType.id);
  return (
    <form action={renameThisRoomType}>
      <label htmlFor={`room-type-name-${roomType.id}`}>الاسم الجديد</label>
      <input
        id={`room-type-name-${roomType.id}`}
        name="room_type_name"
        defaultValue={roomType.room_type_name}
        required
      />
      <button type="submit">حفظ</button>
    </form>
  );
}

function AddRoomTypeForm({ hotelId }: { hotelId: number }) {
  const createThisRoomType = createRoomType.bind(null, hotelId);
  return (
    <form action={createThisRoomType}>
      <h3>إضافة نوع غرفة</h3>
      <label htmlFor="new-room-type-name">الاسم</label>
      <input id="new-room-type-name" name="room_type_name" required />
      <button type="submit">إضافة</button>
    </form>
  );
}
