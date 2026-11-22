"use client";

import { Card, CardHeader } from "@/components/ui/Card";
import type { ProjectData } from "@/types/project";
import { shortDate } from "./shared";

const DAY = 86_400_000;
const t = (iso: string) => new Date(`${iso.slice(0, 10)}T00:00:00Z`).getTime();

/** Gantt-style view built only from milestone dates, plus the module dependency list. */
export function RoadmapTab({ data }: { data: ProjectData }) {
  const ms = data.milestones;
  if (ms.length === 0) return <p className="text-sm text-muted">No milestones yet. Add some in the Tasks tab&apos;s milestone section.</p>;
  const starts = ms.map((m) => t(m.start_date ?? m.target_date));
  const ends = ms.map((m) => t(m.target_date));
  const min = Math.min(...starts);
  const max = Math.max(...ends, min + 30 * DAY);
  const span = max - min;
  const today = new Date(data.generated_at).getTime();
  const todayPct = today >= min && today <= max ? ((today - min) / span) * 100 : null;
  const phases = Array.from(new Set(ms.map((m) => m.phase || "Other")));
  const launch = data.launch;
  return (
    <div className="space-y-6">
      <Card className="overflow-hidden">
        <CardHeader title="Timeline" description="Bars run from each milestone's start to its proposed target date. Green means reached." />
        <div className="overflow-x-auto px-5 pb-5">
          <div className="relative min-w-[640px]">
            {todayPct !== null ? <div className="absolute inset-y-0 w-px bg-danger/60" style={{ left: `${todayPct}%` }} aria-hidden="true"><span className="absolute -top-0 left-1 text-[10px] text-danger">today</span></div> : null}
            {phases.map((phase) => (
              <div key={phase} className="border-t border-border py-2">
                <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted">{phase}</p>
                {ms.filter((m) => (m.phase || "Other") === phase).map((m) => {
                  const s = t(m.start_date ?? m.target_date);
                  const e = t(m.target_date);
                  const left = ((s - min) / span) * 100;
                  const width = Math.max(((e - s) / span) * 100, 1.5);
                  return (
                    <div key={m.id} className="mb-1.5">
                      <div className="relative h-6">
                        <div className={`absolute h-full rounded ${m.reached_at ? "bg-success" : m.overdue ? "bg-danger" : "bg-accent"}`} style={{ left: `${left}%`, width: `${width}%` }} title={`${m.name}: ${shortDate(m.start_date)} to ${shortDate(m.target_date)}`} />
                      </div>
                      <p className="text-xs text-ink">{m.name} <span className="text-muted">· {m.reached_at ? `reached ${shortDate(m.reached_at)}` : `target ${shortDate(m.target_date)}`}</span></p>
                    </div>
                  );
                })}
              </div>
            ))}
          </div>
        </div>
      </Card>
      <Card>
        <CardHeader title="Module dependencies" description="A module cannot finish until the modules it depends on have done their part." />
        <ul className="px-5 pb-5 text-sm">
          {data.modules.map((m) => (
            <li key={m.key} className="border-t border-border py-2 first:border-t-0">
              <span className="font-medium text-ink">{m.name}</span> <span className="text-muted">({m.percent}%)</span>
              <span className="block text-xs text-muted">{m.depends_on_modules.length ? `Depends on: ${m.depends_on_modules.join(", ")}` : "No dependencies on other modules"}</span>
            </li>
          ))}
        </ul>
      </Card>
      <Card>
        <CardHeader title="Outstanding launch requirements" />
        <ul className="px-5 pb-5 text-sm">
          {data.tasks.filter((x) => x.is_launch && x.status !== "completed").map((x) => (
            <li key={x.id} className="border-t border-border py-2 first:border-t-0 text-ink">{x.title}</li>
          ))}
          {launch.every((l) => !l.has_items || l.ready) ? <li className="text-muted">No outstanding launch requirements are tracked.</li> : null}
        </ul>
      </Card>
    </div>
  );
}
