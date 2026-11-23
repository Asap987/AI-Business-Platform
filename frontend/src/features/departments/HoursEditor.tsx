"use client";

import { Input } from "@/components/ui/Input";

export const DAYS = [
  { key: "mon", label: "Monday" }, { key: "tue", label: "Tuesday" }, { key: "wed", label: "Wednesday" }, { key: "thu", label: "Thursday" },
  { key: "fri", label: "Friday" }, { key: "sat", label: "Saturday" }, { key: "sun", label: "Sunday" },
] as const;

export interface DayState { open: boolean; start: string; end: string; extra: string[][] }
export type WeekState = Record<string, DayState>;

/** Turns the saved hours into editable rows. Extra ranges beyond the first are kept so editing never drops them. */
export function toWeek(hours: Record<string, string[][]> | null): WeekState {
  const week: WeekState = {};
  for (const { key } of DAYS) {
    const spans = hours?.[key] ?? [];
    week[key] = spans.length ? { open: true, start: spans[0][0], end: spans[0][1], extra: spans.slice(1) } : { open: false, start: "08:00", end: "17:00", extra: [] };
  }
  return week;
}

export function fromWeek(week: WeekState): Record<string, string[][]> {
  const out: Record<string, string[][]> = {};
  for (const { key } of DAYS) {
    const d = week[key];
    if (d.open) out[key] = [[d.start, d.end], ...d.extra];
  }
  return out;
}

export function summariseHours(hours: Record<string, string[][]> | null): string {
  if (hours === null) return "Always open";
  const days = DAYS.filter(({ key }) => (hours[key] ?? []).length > 0);
  if (days.length === 0) return "Closed";
  return `${days.length} day${days.length === 1 ? "" : "s"} a week`;
}

export function HoursEditor({ week, onChange }: { week: WeekState; onChange: (w: WeekState) => void }) {
  const set = (key: string, patch: Partial<DayState>) => onChange({ ...week, [key]: { ...week[key], ...patch } });
  return (
    <ul className="space-y-2">
      {DAYS.map(({ key, label }) => {
        const d = week[key];
        return (
          <li key={key} className="grid grid-cols-[7rem_minmax(0,1fr)] items-center gap-2 sm:grid-cols-[9rem_minmax(0,1fr)]">
            <label className="flex items-center gap-2 text-sm text-ink">
              <input type="checkbox" checked={d.open} onChange={(e) => set(key, { open: e.target.checked })} /> {label}
            </label>
            {d.open ? (
              <div className="flex min-w-0 items-center gap-2">
                <div className="min-w-0 flex-1"><Input label={`${label} opens`} hideLabel type="time" value={d.start} onChange={(e) => set(key, { start: e.target.value })} /></div>
                <span aria-hidden="true" className="text-muted">to</span>
                <div className="min-w-0 flex-1"><Input label={`${label} closes`} hideLabel type="time" value={d.end} onChange={(e) => set(key, { end: e.target.value })} /></div>
                {d.extra.length ? <span className="text-xs text-muted">+{d.extra.length} more range(s) kept</span> : null}
              </div>
            ) : <span className="text-sm text-muted">Closed</span>}
          </li>
        );
      })}
    </ul>
  );
}
