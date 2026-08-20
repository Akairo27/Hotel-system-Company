import Link from "next/link";
import { redirect } from "next/navigation";
import { createClient } from "@/utils/supabase/server";
import { getCurrentAppUser } from "@/lib/session";
import type { AllotmentForDashboard, Hotel, RoomType } from "@/lib/types";
import { updateAllotmentCost } from "./actions";

export default async function AllotmentsPage({
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
  const [{ data: allotments }, { data: hotels }, { data: roomTypes }] = await Promise.all([
    supabase
      .from("allotments_for_dashboard")
      .select("id, hotel_id, room_type_id, stay_date, total_rooms, cost_per_night, created_at")
      .order("stay_date")
      .overrideTypes<AllotmentForDashboard[], { merge: false }>(),
    supabase.from("hotels").select("id, hotel_name, created_at").overrideTypes<
      Hotel[],
      { merge: false }
    >(),
    supabase.from("room_types").select("id, hotel_id, room_type_name, created_at").overrideTypes<
      RoomType[],
      { merge: false }
    >(),
  ]);

  const hotelNames = new Map((hotels ?? []).map((h) => [h.id, h.hotel_name]));
  const roomTypeNames = new Map((roomTypes ?? []).map((rt) => [rt.id, rt.room_type_name]));
  const canEditCost = appUser.app_role === "admin" && appUser.can_view_cost;

  return (
    <main>
      <p>
        <Link href="/dashboard">&larr; لوحة التحكم</Link>
      </p>
      <h1>التكلفة</h1>
      {error && <p role="alert">{error}</p>}
      {!appUser.can_view_cost && <p>لا تملك صلاحية عرض التكلفة — راجع شاشة الصلاحيات.</p>}
      <table>
        <thead>
          <tr>
            <th>الفندق</th>
            <th>نوع الغرفة</th>
            <th>التاريخ</th>
            <th>عدد الغرف</th>
            <th>التكلفة لليلة (هللة)</th>
          </tr>
        </thead>
        <tbody>
          {(allotments ?? []).map((allotment) => (
            <tr key={allotment.id}>
              <td>{hotelNames.get(allotment.hotel_id) ?? allotment.hotel_id}</td>
              <td>{roomTypeNames.get(allotment.room_type_id) ?? allotment.room_type_id}</td>
              <td>{allotment.stay_date}</td>
              <td>{allotment.total_rooms}</td>
              <td>
                {canEditCost ? (
                  <CostForm allotment={allotment} />
                ) : (
                  (allotment.cost_per_night ?? "—")
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </main>
  );
}

function CostForm({ allotment }: { allotment: AllotmentForDashboard }) {
  const updateThisAllotmentsCost = updateAllotmentCost.bind(null, allotment.id);
  return (
    <form action={updateThisAllotmentsCost}>
      <label htmlFor={`cost-${allotment.id}`}>التكلفة لليلة (هللة)</label>
      <input
        id={`cost-${allotment.id}`}
        name="cost_per_night"
        type="number"
        min={0}
        step={1}
        defaultValue={allotment.cost_per_night ?? undefined}
        required
      />
      <button type="submit">حفظ</button>
    </form>
  );
}
