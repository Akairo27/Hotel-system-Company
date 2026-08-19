"use client";

import { useMemo, useState, type CSSProperties } from "react";
import type { Season } from "@/lib/types";
import {
  HIJRI_FIRST_YEAR,
  HIJRI_LAST_SELECTABLE_YEAR,
  currentHijriYearEstimate,
  hijriMonthGregorianSpan,
  hijriYearGregorianSpan,
  resolveYearCoverage,
  type DayCoverage,
} from "@/lib/seasonCalendar";
import { monthName } from "@/lib/monthNames";
import { seasonColor, GAP_COLOR } from "@/lib/seasonColor";

interface CalendarPreviewProps {
  seasons: Season[];
}

const GREGORIAN_DATE_FORMAT = new Intl.DateTimeFormat("ar-SA-u-ca-gregory", {
  day: "numeric",
  month: "short",
  timeZone: "UTC",
});

function formatGregorian(date: Date): string {
  return GREGORIAN_DATE_FORMAT.format(date);
}

function dayLabel(day: DayCoverage, defaultSeasonName: string): string {
  const dateLabel = formatGregorian(day.date);
  if (day.matching.length === 0) {
    return `${dateLabel} — ${defaultSeasonName} (افتراضي)`;
  }
  const names = day.matching.map((season) => season.season_name);
  const winnerName = day.winner?.season_name ?? defaultSeasonName;
  return day.matching.length > 1
    ? `${dateLabel} — تداخل: ${names.join("، ")} — يفوز: ${winnerName}`
    : `${dateLabel} — ${winnerName}`;
}

function dayStyle(day: DayCoverage): CSSProperties {
  const baseColor = day.winner ? seasonColor(day.winner.id) : GAP_COLOR;
  if (day.matching.length > 1) {
    return {
      backgroundColor: baseColor,
      backgroundImage:
        "repeating-linear-gradient(45deg, rgba(255,255,255,0.6) 0, " +
        "rgba(255,255,255,0.6) 2px, transparent 2px, transparent 6px)",
    };
  }
  return { backgroundColor: baseColor };
}

// Slices a full Hijri year's day-by-day coverage into its 12 month blocks
// using the real per-month Gregorian boundaries from the reference table
// (hijriMonthGregorianSpan) — never assumed or counted out by hand, since
// a Hijri month is 29 or 30 days depending on the year.
function groupByHijriMonth(days: DayCoverage[], hijriYear: number): DayCoverage[][] {
  return Array.from({ length: 12 }, (_, index) => {
    const span = hijriMonthGregorianSpan(hijriYear, index + 1);
    return days.filter((day) => day.date >= span.start && day.date < span.end);
  });
}

export function CalendarPreview({ seasons }: CalendarPreviewProps) {
  const [hijriYear, setHijriYear] = useState(() => currentHijriYearEstimate(new Date()));

  const defaultSeason = seasons.find((season) => season.is_default) ?? null;
  const defaultSeasonName = defaultSeason?.season_name ?? "بلا موسم افتراضي";
  const nonDefaultSeasons = useMemo(
    () => seasons.filter((season) => !season.is_default),
    [seasons]
  );

  const coverage = useMemo(() => resolveYearCoverage(seasons, hijriYear), [seasons, hijriYear]);
  const months = useMemo(
    () => groupByHijriMonth(coverage, hijriYear),
    [coverage, hijriYear]
  );

  const yearOptions = useMemo(
    () =>
      Array.from(
        { length: HIJRI_LAST_SELECTABLE_YEAR - HIJRI_FIRST_YEAR + 1 },
        (_, index) => HIJRI_FIRST_YEAR + index
      ),
    []
  );

  return (
    <section>
      <h2>معاينة التقويم</h2>
      <label>
        السنة الهجرية
        <select value={hijriYear} onChange={(event) => setHijriYear(Number(event.target.value))}>
          {yearOptions.map((year) => (
            <option key={year} value={year}>
              {year} هـ
            </option>
          ))}
        </select>
      </label>

      <ul>
        {nonDefaultSeasons.map((season) => (
          <li key={season.id}>
            <span
              aria-hidden
              style={{
                display: "inline-block",
                width: "0.9em",
                height: "0.9em",
                backgroundColor: seasonColor(season.id),
                marginInlineEnd: "0.4em",
              }}
            />
            {season.season_name}
          </li>
        ))}
        <li>
          <span
            aria-hidden
            style={{
              display: "inline-block",
              width: "0.9em",
              height: "0.9em",
              backgroundColor: GAP_COLOR,
              marginInlineEnd: "0.4em",
            }}
          />
          {defaultSeasonName} (افتراضي — يغطي الفجوات)
        </li>
      </ul>

      {months.map((monthDays, index) => {
        const monthNumber = index + 1;
        if (monthDays.length === 0) {
          return null;
        }
        const firstDay = monthDays[0];
        const lastDay = monthDays[monthDays.length - 1];
        return (
          <div key={monthNumber}>
            <strong>{monthName("hijri", monthNumber)}</strong>{" "}
            <span style={{ color: "#6b7280", fontSize: "0.85em" }}>
              {firstDay ? formatGregorian(firstDay.date) : ""}
              {" – "}
              {lastDay ? formatGregorian(lastDay.date) : ""}
            </span>
            <div style={{ display: "flex", gap: "2px" }}>
              {monthDays.map((day) => (
                <div
                  key={day.date.toISOString()}
                  title={dayLabel(day, defaultSeasonName)}
                  style={{
                    width: "14px",
                    height: "14px",
                    ...dayStyle(day),
                  }}
                />
              ))}
            </div>
          </div>
        );
      })}

      <p style={{ color: "#6b7280", fontSize: "0.85em" }}>
        المدى المعروض: {formatGregorian(hijriYearGregorianSpan(hijriYear).start)} –{" "}
        {formatGregorian(hijriYearGregorianSpan(hijriYear).end)} (ميلادي)
      </p>
    </section>
  );
}
