// seasons carries no color column (db/migrations/0002_seasons.sql) — colors
// are assigned deterministically from a season's id rather than stored, so
// the same season always renders the same color without a schema change.
const PALETTE = [
  "#2563eb", // blue
  "#dc2626", // red
  "#16a34a", // green
  "#d97706", // amber
  "#9333ea", // purple
  "#0891b2", // cyan
  "#db2777", // pink
  "#65a30d", // lime
  "#4f46e5", // indigo
  "#ea580c", // orange
] as const;

export function seasonColor(seasonId: number): string {
  const index = ((seasonId % PALETTE.length) + PALETTE.length) % PALETTE.length;
  return PALETTE[index];
}

export const GAP_COLOR = "#d1d5db";
