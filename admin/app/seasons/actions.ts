"use server";

import { redirect } from "next/navigation";
import { revalidatePath } from "next/cache";
import { createClient } from "@/utils/supabase/server";
import { getCurrentAppUser } from "@/lib/session";
import type { CalendarType } from "@/lib/types";

const SEASONS_PATH = "/seasons";

function redirectWithError(message: string): never {
  redirect(SEASONS_PATH + "?error=" + encodeURIComponent(message));
}

// Render-time gating (hiding the form for a non-admin) is not a security
// boundary on its own — a request can reach a Server Action without going
// through the UI — so every write here re-checks the role itself. The RLS
// policies added by migration 0015 are the real, DB-level backstop; this
// is the friendly-error fast path in front of them.
async function requireAdmin(): Promise<void> {
  const appUser = await getCurrentAppUser();
  if (!appUser || appUser.app_role !== "admin") {
    redirectWithError("هذا الإجراء يتطلب صلاحية المدير.");
  }
}

interface SeasonBounds {
  seasonName: string;
  calendarType: CalendarType;
  startMonth: number;
  startDay: number;
  endMonth: number;
  endDay: number;
}

function readSeasonBounds(formData: FormData): SeasonBounds {
  const seasonName = formData.get("season_name");
  const calendarType = formData.get("calendar_type");
  const startMonth = Number(formData.get("start_month"));
  const startDay = Number(formData.get("start_day"));
  const endMonth = Number(formData.get("end_month"));
  const endDay = Number(formData.get("end_day"));

  if (typeof seasonName !== "string" || seasonName.trim() === "") {
    redirectWithError("اسم الموسم مطلوب.");
  }
  if (calendarType !== "hijri" && calendarType !== "gregorian") {
    redirectWithError("نوع التقويم غير صالح.");
  }
  if (
    !Number.isInteger(startMonth) ||
    !Number.isInteger(startDay) ||
    !Number.isInteger(endMonth) ||
    !Number.isInteger(endDay)
  ) {
    redirectWithError("تواريخ الموسم غير صالحة.");
  }

  return {
    seasonName: seasonName.trim(),
    calendarType,
    startMonth,
    startDay,
    endMonth,
    endDay,
  };
}

export async function createSeason(formData: FormData): Promise<void> {
  await requireAdmin();
  const bounds = readSeasonBounds(formData);

  const supabase = await createClient();
  // priority is left unset (DB default 0) — a brand-new season never
  // outranks an existing one by surprise; drag-to-reorder is the only path
  // that deliberately assigns priority (see reorderSeasons below).
  const { error } = await supabase.from("seasons").insert({
    season_name: bounds.seasonName,
    calendar_type: bounds.calendarType,
    start_month: bounds.startMonth,
    start_day: bounds.startDay,
    end_month: bounds.endMonth,
    end_day: bounds.endDay,
  });
  if (error) {
    redirectWithError(error.message);
  }
  redirect(SEASONS_PATH);
}

export async function updateSeasonBounds(
  seasonId: number,
  formData: FormData
): Promise<void> {
  await requireAdmin();
  const bounds = readSeasonBounds(formData);

  const supabase = await createClient();
  // Unlike INSERT's WITH CHECK, a denied UPDATE does not raise a Postgres
  // error — RLS's admin-only USING clause just filters the row out of the
  // update, so it matches zero rows silently instead. requireAdmin() above
  // already covers the normal case; this is the DB-level layer underneath
  // it, verified in tests/integration/test_seasons_rls.py.
  const { data, error } = await supabase
    .from("seasons")
    .update({
      season_name: bounds.seasonName,
      calendar_type: bounds.calendarType,
      start_month: bounds.startMonth,
      start_day: bounds.startDay,
      end_month: bounds.endMonth,
      end_day: bounds.endDay,
    })
    .eq("id", seasonId)
    .select("id");
  if (error) {
    redirectWithError(error.message);
  }
  if (!data || data.length === 0) {
    redirectWithError("غير مصرح لك بتعديل هذا الموسم.");
  }
  redirect(SEASONS_PATH);
}

export async function renameDefaultSeason(formData: FormData): Promise<void> {
  await requireAdmin();
  const seasonId = Number(formData.get("season_id"));
  const seasonName = formData.get("season_name");
  if (!Number.isInteger(seasonId) || typeof seasonName !== "string" || seasonName.trim() === "") {
    redirectWithError("اسم الموسم مطلوب.");
  }

  const supabase = await createClient();
  const { data, error } = await supabase
    .from("seasons")
    .update({ season_name: seasonName.trim() })
    .eq("id", seasonId)
    .eq("is_default", true)
    .select("id");
  if (error) {
    redirectWithError(error.message);
  }
  if (!data || data.length === 0) {
    redirectWithError("غير مصرح لك بتعديل هذا الموسم.");
  }
  redirect(SEASONS_PATH);
}

// The mandatory single default season (ARCHITECTURE.md §4, migration 0002's
// seasons_single_default index) — nothing else in this codebase creates
// one, so the admin screen offers this as an explicit one-time action when
// none exists yet. Bounds are the inert placeholder (1,1,1,1): a default
// row's own start/end is never consulted by resolve_season_id
// (services/pricing/seasons.py) — it's used purely as the fallback,
// regardless of its configured range — so there is nothing meaningful to
// enter here beyond a name.
export async function createDefaultSeason(): Promise<void> {
  await requireAdmin();

  const supabase = await createClient();
  const { error } = await supabase.from("seasons").insert({
    season_name: "الموسم الافتراضي",
    calendar_type: "hijri",
    start_month: 1,
    start_day: 1,
    end_month: 1,
    end_day: 1,
    is_default: true,
  });
  if (error) {
    redirectWithError(error.message);
  }
  redirect(SEASONS_PATH);
}

export interface ReorderResult {
  error?: string;
}

// Called directly from the drag-to-reorder client component (not a <form
// action>), so it returns a result instead of redirecting — the caller has
// already applied the new order optimistically to its local state and only
// needs to know whether the write actually landed.
export async function reorderSeasons(orderedSeasonIds: number[]): Promise<ReorderResult> {
  const appUser = await getCurrentAppUser();
  if (!appUser || appUser.app_role !== "admin") {
    return { error: "هذا الإجراء يتطلب صلاحية المدير." };
  }

  const supabase = await createClient();
  // Topmost in the dragged list = highest priority. Sequential UPDATEs
  // (not a bulk upsert) keep this on the same tested single-row RLS path
  // as every other write here — rowcount is checked per row, same gotcha.
  const highestPriority = orderedSeasonIds.length - 1;
  for (const [index, seasonId] of orderedSeasonIds.entries()) {
    const priority = highestPriority - index;
    const { data, error } = await supabase
      .from("seasons")
      .update({ priority })
      .eq("id", seasonId)
      .select("id");
    if (error) {
      return { error: error.message };
    }
    if (!data || data.length === 0) {
      return { error: "غير مصرح لك بإعادة ترتيب المواسم." };
    }
  }

  revalidatePath(SEASONS_PATH);
  return {};
}
