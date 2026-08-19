"use client";

import { useState } from "react";
import type { CalendarType, Season } from "@/lib/types";
import { endOfMonthSentinel } from "@/lib/seasonCalendar";
import { monthName, MONTH_NUMBERS } from "@/lib/monthNames";
import { seasonColor } from "@/lib/seasonColor";
import { SeasonEditForm } from "./SeasonEditForm";
import { createDefaultSeason, createSeason, renameDefaultSeason } from "./actions";

interface SeasonListProps {
  seasons: Season[];
  isAdmin: boolean;
  onSeasonChange: (updated: Season) => void;
  onReorder: (orderedSeasonIds: number[]) => void;
  reorderError: string | null;
}

export function SeasonList({
  seasons,
  isAdmin,
  onSeasonChange,
  onReorder,
  reorderError,
}: SeasonListProps) {
  const defaultSeason = seasons.find((season) => season.is_default) ?? null;
  // Highest priority first — matches resolve_season_id's own tie-break
  // (higher priority wins), so the list's visual top-to-bottom order is
  // exactly "who wins first" without the admin needing to read numbers.
  const orderedSeasons = seasons
    .filter((season) => !season.is_default)
    .sort((a, b) => b.priority - a.priority || a.id - b.id);

  const [draggedId, setDraggedId] = useState<number | null>(null);

  function handleDrop(targetId: number): void {
    if (draggedId === null || draggedId === targetId) {
      setDraggedId(null);
      return;
    }
    const ids = orderedSeasons.map((season) => season.id);
    const fromIndex = ids.indexOf(draggedId);
    const toIndex = ids.indexOf(targetId);
    if (fromIndex === -1 || toIndex === -1) {
      setDraggedId(null);
      return;
    }
    ids.splice(fromIndex, 1);
    ids.splice(toIndex, 0, draggedId);
    setDraggedId(null);
    onReorder(ids);
  }

  return (
    <section>
      <h2>المواسم</h2>
      {isAdmin && <p>الأعلى في القائمة يفوز عند تداخل المواسم — اسحب لإعادة الترتيب.</p>}
      {reorderError && <p role="alert">{reorderError}</p>}

      <ul>
        {orderedSeasons.map((season) => (
          <li
            key={season.id}
            draggable={isAdmin}
            onDragStart={isAdmin ? () => setDraggedId(season.id) : undefined}
            onDragOver={isAdmin ? (event) => event.preventDefault() : undefined}
            onDrop={isAdmin ? () => handleDrop(season.id) : undefined}
          >
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
            {isAdmin ? (
              <details>
                <summary>{season.season_name}</summary>
                <SeasonEditForm season={season} onChange={onSeasonChange} />
              </details>
            ) : (
              season.season_name
            )}
          </li>
        ))}
      </ul>

      <DefaultSeasonBlock defaultSeason={defaultSeason} isAdmin={isAdmin} />

      {isAdmin && <AddSeasonForm />}
    </section>
  );
}

function DefaultSeasonBlock({
  defaultSeason,
  isAdmin,
}: {
  defaultSeason: Season | null;
  isAdmin: boolean;
}) {
  if (defaultSeason === null && !isAdmin) {
    return <p>لا يوجد موسم افتراضي بعد.</p>;
  }
  if (defaultSeason === null) {
    return (
      <form action={createDefaultSeason}>
        <p>
          لا يوجد موسم افتراضي بعد — أي تاريخ لا يقع ضمن موسم محدد يحتاج مرجعاً. أنشئ الموسم
          الافتراضي المطلوب (ARCHITECTURE.md §4).
        </p>
        <button type="submit">إنشاء الموسم الافتراضي</button>
      </form>
    );
  }

  if (!isAdmin) {
    return (
      <p>
        الموسم الافتراضي (يغطي كل الفجوات): <strong>{defaultSeason.season_name}</strong>
      </p>
    );
  }

  return (
    <form action={renameDefaultSeason}>
      <input type="hidden" name="season_id" value={defaultSeason.id} />
      <label>
        اسم الموسم الافتراضي (يغطي كل الفجوات، حدوده غير قابلة للتعديل)
        <input name="season_name" defaultValue={defaultSeason.season_name} required />
      </label>
      <button type="submit">حفظ</button>
    </form>
  );
}

function AddSeasonForm() {
  const [calendarType, setCalendarType] = useState<CalendarType>("hijri");
  const [endMonth, setEndMonth] = useState(1);
  const [endDay, setEndDay] = useState(1);
  const [endsAtMonthEnd, setEndsAtMonthEnd] = useState(false);

  function toggleEndsAtMonthEnd(checked: boolean): void {
    setEndsAtMonthEnd(checked);
    if (checked) {
      setEndDay(endOfMonthSentinel(calendarType, endMonth));
    }
  }

  function handleCalendarTypeChange(next: CalendarType): void {
    setCalendarType(next);
    if (endsAtMonthEnd) {
      setEndDay(endOfMonthSentinel(next, endMonth));
    }
  }

  function handleEndMonthChange(next: number): void {
    setEndMonth(next);
    if (endsAtMonthEnd) {
      setEndDay(endOfMonthSentinel(calendarType, next));
    }
  }

  return (
    <form action={createSeason}>
      <h3>إضافة موسم</h3>
      <label>
        اسم الموسم
        <input name="season_name" required />
      </label>

      <label>
        التقويم
        <select
          name="calendar_type"
          value={calendarType}
          onChange={(event) => handleCalendarTypeChange(event.target.value as CalendarType)}
        >
          <option value="hijri">هجري</option>
          <option value="gregorian">ميلادي</option>
        </select>
      </label>

      <fieldset>
        <legend>البداية</legend>
        <select name="start_month" defaultValue={1}>
          {MONTH_NUMBERS.map((monthNumber) => (
            <option key={monthNumber} value={monthNumber}>
              {monthName(calendarType, monthNumber)}
            </option>
          ))}
        </select>
        <input type="number" name="start_day" min={1} max={31} defaultValue={1} required />
      </fieldset>

      <fieldset>
        <legend>النهاية</legend>
        <select
          name="end_month"
          value={endMonth}
          onChange={(event) => handleEndMonthChange(Number(event.target.value))}
        >
          {MONTH_NUMBERS.map((monthNumber) => (
            <option key={monthNumber} value={monthNumber}>
              {monthName(calendarType, monthNumber)}
            </option>
          ))}
        </select>
        {endsAtMonthEnd ? (
          <input type="hidden" name="end_day" value={endDay} />
        ) : (
          <input
            type="number"
            name="end_day"
            min={1}
            max={31}
            value={endDay}
            onChange={(event) => setEndDay(Number(event.target.value))}
            required
          />
        )}
        <label>
          <input
            type="checkbox"
            checked={endsAtMonthEnd}
            onChange={(event) => toggleEndsAtMonthEnd(event.target.checked)}
          />
          حتى نهاية الشهر
        </label>
      </fieldset>

      <button type="submit">إضافة</button>
    </form>
  );
}
