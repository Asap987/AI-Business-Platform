import type { ReactNode } from "react";
import { cn, humanize } from "@/lib/utils";

export type BadgeTone = "neutral" | "info" | "success" | "warning" | "danger" | "accent";

const TONES: Record<BadgeTone, string> = {
  neutral: "bg-surface-muted text-ink",
  info: "bg-info-soft text-info",
  success: "bg-success-soft text-success",
  warning: "bg-warning-soft text-warning",
  danger: "bg-danger-soft text-danger",
  accent: "bg-accent-soft text-accent-strong",
};

interface BadgeProps {
  tone?: BadgeTone;
  children: ReactNode;
  className?: string;
}

export function Badge({ tone = "neutral", children, className }: BadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium",
        TONES[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}

/** Known status values across conversations, cases, agents and employees. */
const STATUS_TONES: Record<string, BadgeTone> = {
  open: "info",
  in_progress: "accent",
  waiting: "warning",
  waiting_customer: "warning",
  waiting_department: "warning",
  resolved: "success",
  closed: "neutral",
  active: "success",
  paused: "warning",
  draft: "neutral",
  retired: "neutral",
  invited: "info",
  disabled: "danger",
  on_leave: "warning",
  inactive: "neutral",
};

/** Colour-codes a raw status string; unknown values render neutrally. */
export function StatusBadge({ status, label }: { status: string; label?: string }) {
  return <Badge tone={STATUS_TONES[status] ?? "neutral"}>{label ?? humanize(status)}</Badge>;
}
