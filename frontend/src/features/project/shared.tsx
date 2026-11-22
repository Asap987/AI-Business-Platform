"use client";

import { Badge, type BadgeTone } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import { cn, humanize } from "@/lib/utils";
import type { ExternalCategory, LaunchArea, TaskPriority, TaskStatus } from "@/types/project";

export const STATUS_ORDER: TaskStatus[] = ["not_started", "in_progress", "testing", "awaiting_external", "awaiting_approval", "blocked", "completed"];
export const STATUS_LABEL: Record<TaskStatus, string> = {
  not_started: "Not started",
  in_progress: "In progress",
  awaiting_external: "Awaiting external dependency",
  awaiting_approval: "Awaiting approval",
  testing: "Testing",
  completed: "Completed",
  blocked: "Blocked",
};
export const STATUS_TONE: Record<TaskStatus, BadgeTone> = {
  not_started: "neutral",
  in_progress: "accent",
  awaiting_external: "warning",
  awaiting_approval: "warning",
  testing: "info",
  completed: "success",
  blocked: "danger",
};
export const STATUS_BAR: Record<TaskStatus, string> = {
  not_started: "bg-border-strong",
  in_progress: "bg-accent",
  awaiting_external: "bg-warning",
  awaiting_approval: "bg-warning/60",
  testing: "bg-info",
  completed: "bg-success",
  blocked: "bg-danger",
};
export const PRIORITIES: TaskPriority[] = ["low", "medium", "high", "critical"];
export const PRIORITY_TONE: Record<TaskPriority, BadgeTone> = { low: "neutral", medium: "info", high: "warning", critical: "danger" };
export const EVIDENCE_LABEL = {
  merged_commit: "Merged commit",
  passing_test: "Passing test",
  integration: "Successful integration",
  documented_verification: "Documented verification",
} as const;
export const LAUNCH_LABEL: Record<LaunchArea, string> = {
  security: "Security",
  data_isolation: "Data isolation",
  voice_quality: "Voice quality",
  call_transfers: "Real call transfers",
  email_delivery: "Email delivery",
  monitoring: "Monitoring",
  backup: "Backup procedures",
};
export const EXTERNAL_LABEL: Record<ExternalCategory, string> = {
  awaiting_us: "Awaiting us",
  awaiting_provider: "Awaiting an external provider",
  awaiting_approval: "Awaiting approval",
  completed: "Completed",
};
export const EXTERNAL_TONE: Record<ExternalCategory, BadgeTone> = { awaiting_us: "info", awaiting_provider: "warning", awaiting_approval: "accent", completed: "success" };

export function StatusPill({ status }: { status: TaskStatus }) {
  return <Badge tone={STATUS_TONE[status]}>{STATUS_LABEL[status]}</Badge>;
}

export function PriorityPill({ priority }: { priority: TaskPriority }) {
  return <Badge tone={PRIORITY_TONE[priority]}>{humanize(priority)}</Badge>;
}

/** A labelled bar; the percentage is always computed by the server from task weights. */
export function ProgressBar({ percent, label, tone = "bg-accent" }: { percent: number; label: string; tone?: string }) {
  const value = Math.max(0, Math.min(100, percent));
  return (
    <div
      role="progressbar"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={Math.round(value)}
      className="h-2 w-full overflow-hidden rounded-full bg-surface-muted"
    >
      <div className={cn("h-full rounded-full", tone)} style={{ width: `${value}%` }} />
    </div>
  );
}

export function Stat({ label, value, note, tone }: { label: string; value: string; note?: string; tone?: string }) {
  return (
    <Card className="p-4">
      <p className="text-xs text-muted">{label}</p>
      <p className={cn("mt-1 text-xl font-semibold text-ink", tone)}>{value}</p>
      {note ? <p className="mt-1 text-xs text-muted">{note}</p> : null}
    </Card>
  );
}

export function usd(text: string): string {
  const n = Number(text);
  return `$${n < 1 && n > 0 ? n.toFixed(4) : n.toFixed(2)}`;
}

/** 2026-11-22 -> 22 Nov 2026 (dates come from the server as plain ISO dates). */
export function shortDate(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso.length === 10 ? `${iso}T00:00:00` : iso);
  return Number.isNaN(d.getTime()) ? "—" : d.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
}
