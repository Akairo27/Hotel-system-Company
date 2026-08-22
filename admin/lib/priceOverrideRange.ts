// Client-side pre-check for admin_upsert_price_overrides
// (db/migrations/0021_price_overrides_admin_access.sql). Unlike
// admin/lib/priceRuleBands.ts, this is not a port of a jsonb band
// validator kept in sync with a SQL function — price_overrides carries no
// jsonb shape, so there is no cross-language ground truth to test against
// and no conformance fixture here.
//
// The night counter (nightCount) is the primary guard the user asked for:
// a live, per-keystroke count in the form, computed entirely in the
// browser with no query, so a fat-fingered end date is caught before save
// rather than after. MAX_OVERRIDE_RANGE_NIGHTS matches the RPC's own
// RAISE EXCEPTION check exactly (see that migration's comment) — the RPC
// check is the server-side backstop, not the primary guard, same
// defense-in-depth split as price_rules' band validation.
//
// 180, not 366: a year-off typo in the end date (e.g. 2027 instead of
// 2026) produces a 365-night range, which would pass under a 366 cap and
// silently do the wrong thing. 180 is deliberately tight enough that a
// year-off mistake always trips it; anyone who genuinely needs a longer
// span enters it as two ranges.
export const MAX_OVERRIDE_RANGE_NIGHTS = 180;

export interface OverrideRangeValidationResult {
  valid: boolean;
  message: string;
}

const VALID: OverrideRangeValidationResult = { valid: true, message: "" };

function invalid(message: string): OverrideRangeValidationResult {
  return { valid: false, message };
}

// startDate/endDate are "YYYY-MM-DD" <input type="date"> values, parsed as
// UTC midnight so the count is never off by one across a local timezone's
// DST transition — appending "T00:00:00Z" and using Date.parse is what
// makes that UTC, unlike `new Date(startDate)` alone, which Date's own
// spec defines as local time for a bare date-only string in some engines
// and UTC in others.
export function nightCount(startDate: string, endDate: string): number {
  const startMs = Date.parse(`${startDate}T00:00:00Z`);
  const endMs = Date.parse(`${endDate}T00:00:00Z`);
  return Math.round((endMs - startMs) / 86_400_000) + 1;
}

export function validateOverrideRange(
  startDate: string,
  endDate: string,
  askPriceOverride: number,
  minAllowedOverride: number
): OverrideRangeValidationResult {
  if (!startDate || !endDate) {
    return invalid("يجب تحديد تاريخ البداية والنهاية.");
  }
  if (endDate < startDate) {
    return invalid("تاريخ النهاية يجب ألا يسبق تاريخ البداية.");
  }
  const nights = nightCount(startDate, endDate);
  if (nights > MAX_OVERRIDE_RANGE_NIGHTS) {
    return invalid(
      `هذا المدى يغطي ${nights} ليلة — الحد الأقصى ${MAX_OVERRIDE_RANGE_NIGHTS} ليلة ` +
        "لكل حفظ. من يحتاج مدى أطول يدخله على دفعتين."
    );
  }
  if (!Number.isInteger(askPriceOverride) || askPriceOverride < 0) {
    return invalid("سعر العرض يجب أن يكون رقماً صحيحاً غير سالب.");
  }
  if (!Number.isInteger(minAllowedOverride) || minAllowedOverride < 0) {
    return invalid("الحد الأدنى المسموح يجب أن يكون رقماً صحيحاً غير سالب.");
  }
  if (minAllowedOverride > askPriceOverride) {
    return invalid("الحد الأدنى المسموح لا يمكن أن يتجاوز سعر العرض.");
  }
  return VALID;
}
