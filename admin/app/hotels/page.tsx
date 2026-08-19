import Link from "next/link";
import { redirect } from "next/navigation";
import { createClient } from "@/utils/supabase/server";
import { getCurrentAppUser } from "@/lib/session";
import type { Hotel } from "@/lib/types";
import { createHotel, renameHotel } from "./actions";

export default async function HotelsPage({
  searchParams,
}: {
  searchParams: Promise<{ error?: string }>;
}) {
  const { error } = await searchParams;
  const appUser = await getCurrentAppUser();
  if (!appUser) {
    redirect("/login?error=" + encodeURIComponent("لا يوجد حساب مرتبط بهذا الدخول."));
  }

  const supabase = await createClient();
  const { data: hotels } = await supabase
    .from("hotels")
    .select("id, hotel_name, created_at")
    .order("hotel_name")
    .overrideTypes<Hotel[], { merge: false }>();

  const isAdmin = appUser.app_role === "admin";

  return (
    <main>
      <p>
        <Link href="/dashboard">&larr; لوحة التحكم</Link>
      </p>
      <h1>الفنادق</h1>
      {error && <p role="alert">{error}</p>}
      <ul>
        {(hotels ?? []).map((hotel) => (
          <li key={hotel.id}>
            <Link href={`/hotels/${hotel.id}`}>{hotel.hotel_name}</Link>
            {isAdmin && <RenameHotelForm hotel={hotel} />}
          </li>
        ))}
      </ul>
      {isAdmin && <AddHotelForm />}
    </main>
  );
}

function RenameHotelForm({ hotel }: { hotel: Hotel }) {
  const renameThisHotel = renameHotel.bind(null, hotel.id);
  return (
    <form action={renameThisHotel}>
      <label htmlFor={`hotel-name-${hotel.id}`}>الاسم الجديد</label>
      <input
        id={`hotel-name-${hotel.id}`}
        name="hotel_name"
        defaultValue={hotel.hotel_name}
        required
      />
      <button type="submit">حفظ</button>
    </form>
  );
}

function AddHotelForm() {
  return (
    <form action={createHotel}>
      <h2>إضافة فندق</h2>
      <label htmlFor="new-hotel-name">اسم الفندق</label>
      <input id="new-hotel-name" name="hotel_name" required />
      <button type="submit">إضافة</button>
    </form>
  );
}
