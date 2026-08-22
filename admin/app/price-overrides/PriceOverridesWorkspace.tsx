"use client";

import { useState } from "react";
import type { Hotel, PriceOverride, RoomType } from "@/lib/types";
import { PriceOverrideForm } from "./PriceOverrideForm";
import { endPriceOverrideNow } from "./actions";

interface PriceOverridesWorkspaceProps {
  initialOverrides: PriceOverride[];
  hotels: Hotel[];
  roomTypes: RoomType[];
  canEdit: boolean;
}

// Gregorian, pinned explicitly — "ar-SA" alone defaults to the Islamic
// calendar in most engines, and CLAUDE.md reserves Hijri conversion to
// lib/hijri.py alone. Same pattern admin/app/seasons/CalendarPreview.tsx
// already established for this exact reason.
const EXPIRES_AT_FORMAT = new Intl.DateTimeFormat("ar-SA-u-ca-gregory", {
  year: "numeric",
  month: "short",
  day: "numeric",
  hour: "2-digit",
  minute: "2-digit",
});

function groupKey(hotelId: number, roomTypeId: number): string {
  return `${hotelId}:${roomTypeId}`;
}

export function PriceOverridesWorkspace({
  initialOverrides,
  hotels,
  roomTypes,
  canEdit,
}: PriceOverridesWorkspaceProps) {
  const [overrides, setOverrides] = useState(initialOverrides);
  const [error, setError] = useState<string | null>(null);
  const [endingId, setEndingId] = useState<number | null>(null);

  // Resets local state when the server delivers a genuinely new
  // initialOverrides snapshot after revalidatePath("/price-overrides") —
  // same adjust-state-during-render idiom as PriceRulesWorkspace.tsx.
  const [prevInitialOverrides, setPrevInitialOverrides] = useState(initialOverrides);
  if (initialOverrides !== prevInitialOverrides) {
    setPrevInitialOverrides(initialOverrides);
    setOverrides(initialOverrides);
  }

  const hotelNames = new Map(hotels.map((hotel) => [hotel.id, hotel.hotel_name]));
  const roomTypeNames = new Map(
    roomTypes.map((roomType) => [roomType.id, roomType.room_type_name])
  );

  const groups = new Map<string, PriceOverride[]>();
  for (const override of overrides) {
    const key = groupKey(override.hotel_id, override.room_type_id);
    const rows = groups.get(key);
    if (rows) {
      rows.push(override);
    } else {
      groups.set(key, [override]);
    }
  }

  async function handleEndNow(override: PriceOverride): Promise<void> {
    setError(null);
    setEndingId(override.id);
    const result = await endPriceOverrideNow(
      override.hotel_id,
      override.room_type_id,
      override.stay_date,
      override.ask_price_override,
      override.min_allowed_override
    );
    setEndingId(null);
    if (result.error) {
      setError(result.error);
    }
  }

  return (
    <div>
      {canEdit && (
        <PriceOverrideForm
          hotels={hotels}
          roomTypes={roomTypes}
          onSaved={() => {
            // The Server Action already calls revalidatePath — nothing
            // local to reset here; the grouped table below reflects the
            // fresh server snapshot once it lands, same as
            // PriceRulesWorkspace's refresh().
          }}
        />
      )}

      {error && <p role="alert">{error}</p>}

      <h2>التجاوزات الحالية</h2>
      {groups.size === 0 && <p>لا توجد تجاوزات أسعار مسجلة.</p>}
      {[...groups.entries()].map(([key, rows]) => {
        const [hotelIdText, roomTypeIdText] = key.split(":");
        const hotelId = Number(hotelIdText);
        const roomTypeId = Number(roomTypeIdText);
        return (
          <details key={key} open>
            <summary>
              {hotelNames.get(hotelId) ?? `فندق #${hotelId}`} —{" "}
              {roomTypeNames.get(roomTypeId) ?? `نوع غرفة #${roomTypeId}`}
            </summary>
            <table>
              <thead>
                <tr>
                  <th>الليلة</th>
                  <th>سعر العرض</th>
                  <th>الحد الأدنى المسموح</th>
                  <th>ينتهي في</th>
                  <th>الحالة</th>
                  {canEdit && <th></th>}
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => {
                  const isActive = new Date(row.expires_at).getTime() > Date.now();
                  return (
                    <tr key={row.id}>
                      <td>{row.stay_date}</td>
                      <td>{row.ask_price_override}</td>
                      <td>{row.min_allowed_override}</td>
                      <td>{EXPIRES_AT_FORMAT.format(new Date(row.expires_at))}</td>
                      <td>{isActive ? "نشط" : "منتهٍ"}</td>
                      {canEdit && (
                        <td>
                          {isActive && (
                            <button
                              type="button"
                              onClick={() => handleEndNow(row)}
                              disabled={endingId === row.id}
                            >
                              {endingId === row.id ? "جارٍ الإنهاء…" : "إنهاء الآن"}
                            </button>
                          )}
                        </td>
                      )}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </details>
        );
      })}
    </div>
  );
}
