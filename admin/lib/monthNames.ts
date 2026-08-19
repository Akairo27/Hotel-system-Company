import type { CalendarType } from "./types";

const HIJRI_MONTH_NAMES = [
  "محرم",
  "صفر",
  "ربيع الأول",
  "ربيع الآخر",
  "جمادى الأولى",
  "جمادى الآخرة",
  "رجب",
  "شعبان",
  "رمضان",
  "شوال",
  "ذو القعدة",
  "ذو الحجة",
] as const;

const GREGORIAN_MONTH_NAMES = [
  "يناير",
  "فبراير",
  "مارس",
  "أبريل",
  "مايو",
  "يونيو",
  "يوليو",
  "أغسطس",
  "سبتمبر",
  "أكتوبر",
  "نوفمبر",
  "ديسمبر",
] as const;

/** month is 1-12. */
export function monthName(calendarType: CalendarType, month: number): string {
  const names = calendarType === "hijri" ? HIJRI_MONTH_NAMES : GREGORIAN_MONTH_NAMES;
  return names[month - 1] ?? String(month);
}

export const MONTH_NUMBERS = Array.from({ length: 12 }, (_, index) => index + 1);
