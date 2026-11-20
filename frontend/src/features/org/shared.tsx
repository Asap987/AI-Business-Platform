"use client";

import { Badge, type BadgeTone } from "@/components/ui/Badge";
import { useApiResource } from "@/hooks/useApiResource";
import { usePermission } from "@/hooks/usePermission";
import { ApiError } from "@/lib/api";
import { humanize } from "@/lib/utils";
import type { CasePriority, CaseStatus, Department, Employee } from "@/types/org";
import type { Paginated } from "@/types/api";

export const CASE_STATUSES: CaseStatus[] = ["open", "in_progress", "waiting_customer", "waiting_department", "resolved", "closed"];
export const CASE_PRIORITIES: CasePriority[] = ["low", "medium", "high", "urgent"];

/**
 * Where a case may go next. This mirrors the backend rule only to offer sensible
 * choices; the backend still validates every change and answers 409 if it disagrees.
 */
export const NEXT_STATUSES: Record<CaseStatus, CaseStatus[]> = {
  open: ["in_progress", "waiting_customer", "waiting_department", "resolved"],
  in_progress: ["open", "waiting_customer", "waiting_department", "resolved"],
  waiting_customer: ["open", "in_progress", "waiting_department", "resolved"],
  waiting_department: ["open", "in_progress", "waiting_customer", "resolved"],
  resolved: ["in_progress", "closed"],
  closed: [],
};

const PRIORITY_TONES: Record<CasePriority, BadgeTone> = { low: "neutral", medium: "info", high: "warning", urgent: "danger" };

export function PriorityBadge({ priority }: { priority: string }) {
  return <Badge tone={PRIORITY_TONES[priority as CasePriority] ?? "neutral"}>{humanize(priority)}</Badge>;
}

export function statusLabel(status: string): string {
  return humanize(status);
}

/** Departments for pickers and name lookups; skipped (null path) when the role cannot read them. */
export function useDepartmentOptions() {
  const allowed = usePermission("departments:read");
  const resource = useApiResource<Paginated<Department>>(allowed ? "/departments" : null, { page_size: 100 });
  const names = new Map((resource.data?.items ?? []).map((d) => [d.id, d.name]));
  return { allowed, resource, items: resource.data?.items ?? [], names };
}

/** Employees for pickers and name lookups; skipped when the role cannot read them. */
export function useEmployeeOptions(activeOnly = false) {
  const allowed = usePermission("employees:read");
  const resource = useApiResource<Paginated<Employee>>(allowed ? "/employees" : null, {
    page_size: 100,
    status: activeOnly ? "active" : undefined,
  });
  const names = new Map((resource.data?.items ?? []).map((e) => [e.id, e.full_name]));
  return { allowed, resource, items: resource.data?.items ?? [], names };
}

/** Turns a failed request into text for a form banner, preferring the server's own message. */
export function errorText(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.kind === "forbidden") return "You don't have permission to do that.";
    return error.message;
  }
  return "Something unexpected happened. Please try again.";
}

export function pageCount(total: number, pageSize: number): number {
  return Math.max(1, Math.ceil(total / pageSize));
}
