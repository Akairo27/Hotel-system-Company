"use client";

import { useState } from "react";
import type { CalendarType, Season } from "@/lib/types";
import { endOfMonthSentinel } from "@/lib/seasonCalendar";
import { monthName, MONTH_NUMBERS } from "@/lib/monthNames";
import { updateSeasonBounds } from "./actions";

interface SeasonEditFormProps {
  season: Season;
  onChange: (updated: Season) => void;
}

// One form per existing season, used both to edit it and — via controlled
// inputs reported to the parent on every keystroke — to drive the live
// calendar preview before the admin saves anything. Saving still goes
// through a real <form action> to updateSeasonBounds (migration 0015's
// admin-only RLS policy, rowcount-checked the same way PR B's hotel/room
// type renames are).
export function SeasonEditForm({ season, onChange }: SeasonEditFormProps) {
  // Whether the end_day currently on `season` already equals the
  // "through end of month" sentinel for its own end_month/calendar_type —
  // the toggle starts checked whenever the stored data already represents
  // that state, so re-opening an existing season doesn't silently show a
  // literal day number that was actually meant as "through the end".
  const [endsAtMonthEnd, setEndsAtMonthEnd] = useState(
    season.end_day >= endOfMonthSentinel(season.calendar_type, season.end_month)
  );
  const boundAction = updateSeasonBounds.bind(null, season.id);

  function update(partial: Partial<Season>): void {
    const next: Season = { ...season, ...partial };
    if (endsAtMonthEnd) {
      next.end_day = endOfMonthSentinel(next.calendar_type, next.end_month);
    }
    onChange(next);
  }

  function toggleEndsAtMonthEnd(checked: boolean): void {
    setEndsAtMonthEnd(checked);
    if (checked) {
      update({ end_day: endOfMonthSentinel(season.calendar_type, season.end_month) });
    }
  }

  return (
    <form action={boundAction}>
      <label>
        اسم الموسم
        <input
          name="season_name"
          value={season.season_name}
          onChange={(event) => update({ season_name: event.target.value })}
          required
        />
      </label>

      <label>
        التقويم
        <select
          name="calendar_type"
          value={season.calendar_type}
          onChange={(event) => update({ calendar_type: event.target.value as CalendarType })}
        >
          <option value="hijri">هجري</option>
          <option value="gregorian">ميلادي</option>
        </select>
      </label>

      <fieldset>
        <legend>البداية</legend>
        <select
          name="start_month"
          value={season.start_month}
          onChange={(event) => update({ start_month: Number(event.target.value) })}
        >
          {MONTH_NUMBERS.map((monthNumber) => (
            <option key={monthNumber} value={monthNumber}>
              {monthName(season.calendar_type, monthNumber)}
            </option>
          ))}
        </select>
        <input
          type="number"
          name="start_day"
          min={1}
          max={31}
          value={season.start_day}
          onChange={(event) => update({ start_day: Number(event.target.value) })}
          required
        />
      </fieldset>

      <fieldset>
        <legend>النهاية</legend>
        <select
          name="end_month"
          value={season.end_month}
          onChange={(event) => update({ end_month: Number(event.target.value) })}
        >
          {MONTH_NUMBERS.map((monthNumber) => (
            <option key={monthNumber} value={monthNumber}>
              {monthName(season.calendar_type, monthNumber)}
            </option>
          ))}
        </select>
        {endsAtMonthEnd ? (
          <input type="hidden" name="end_day" value={season.end_day} />
        ) : (
          <input
            type="number"
            name="end_day"
            min={1}
            max={31}
            value={season.end_day}
            onChange={(event) => update({ end_day: Number(event.target.value) })}
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

      <button type="submit">حفظ</button>
    </form>
  );
}
