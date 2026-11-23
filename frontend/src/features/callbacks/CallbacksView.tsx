"use client";

import { PhoneCall } from "lucide-react";
import { useState } from "react";
import { PageHeader } from "@/components/layout/PageHeader";
import { Badge, type BadgeTone } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { FormError } from "@/components/ui/ErrorMessage";
import { Skeleton } from "@/components/ui/LoadingSpinner";
import { Pagination } from "@/components/ui/Pagination";
import { ResourceView } from "@/components/ui/ResourceView";
import { Select } from "@/components/ui/Select";
import { errorText, pageCount, useDepartmentOptions } from "@/features/org/shared";
import { useApiResource } from "@/hooks/useApiResource";
import { usePermission } from "@/hooks/usePermission";
import { api } from "@/lib/api";
import { formatRelativeTime, humanize } from "@/lib/utils";
import type { Paginated } from "@/types/api";
import type { CallbackRequest, CallbackStatus } from "@/types/org";

const PAGE_SIZE = 20;
const TONE: Record<CallbackStatus, BadgeTone> = { pending: "warning", contacted: "info", done: "success", cancelled: "neutral" };
const NEXT: Record<CallbackStatus, { to: CallbackStatus; label: string }[]> = {
  pending: [{ to: "contacted", label: "Mark contacted" }, { to: "done", label: "Mark done" }, { to: "cancelled", label: "Cancel" }],
  contacted: [{ to: "done", label: "Mark done" }, { to: "pending", label: "Back to waiting" }, { to: "cancelled", label: "Cancel" }],
  done: [],
  cancelled: [],
};

export function CallbacksView() {
  const canWrite = usePermission("cases:write");
  const departments = useDepartmentOptions();
  const [status, setStatus] = useState("pending");
  const [page, setPage] = useState(1);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const resource = useApiResource<Paginated<CallbackRequest>>("/callbacks", { page, page_size: PAGE_SIZE, status: status || undefined });

  async function move(c: CallbackRequest, to: CallbackStatus) {
    setBusy(c.id);
    setError(null);
    try {
      await api.patch(`/callbacks/${c.id}`, { status: to });
      resource.reload();
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(null);
    }
  }

  return (
    <>
      <PageHeader title="Callback requests" description="Callers nobody could reach. A request is not a booked time: phone the caller, then record it here." />
      {error ? <div className="mb-4"><FormError message={error} /></div> : null}
      <Card>
        <div className="border-b border-border p-4 sm:w-60">
          <Select label="Status" hideLabel value={status} onChange={(e) => { setStatus(e.target.value); setPage(1); }}>
            <option value="">All requests</option>
            {(["pending", "contacted", "done", "cancelled"] as const).map((s) => <option key={s} value={s}>{humanize(s)}</option>)}
          </Select>
        </div>
        <ResourceView
          resource={resource}
          compact={false}
          isEmpty={(d) => d.items.length === 0}
          skeleton={<div className="space-y-3 p-5"><Skeleton className="h-16" /><Skeleton className="h-16" /></div>}
          empty={<EmptyState icon={PhoneCall} title="No callback requests" description="When the assistant cannot connect a caller to a team, their request appears here." />}
        >
          {(data) => (
            <>
              <ul>
                {data.items.map((c) => {
                  const known = Object.entries(c.context.collected ?? {});
                  return (
                    <li key={c.id} className="space-y-1.5 border-t border-border px-4 py-4 first:border-t-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="font-medium text-ink">{c.caller_name ?? "Caller"}</span>
                        <a href={`tel:${c.phone.replace(/[^+\d]/g, "")}`} className="text-accent-strong underline">{c.phone}</a>
                        <Badge tone={TONE[c.status]}>{humanize(c.status)}</Badge>
                        <span className="text-xs text-muted">{c.source === "ai" ? "Taken by the assistant" : "Added by staff"} · {formatRelativeTime(c.created_at)}</span>
                      </div>
                      <p className="text-sm text-ink">{c.reason}</p>
                      <p className="text-xs text-muted">
                        {c.department_id ? `For ${departments.names.get(c.department_id) ?? "a team"}` : "No team chosen"}
                        {c.preferred_time ? ` · Caller prefers: ${c.preferred_time}` : ""}
                      </p>
                      {c.context.summary || known.length || c.context.open_questions?.length ? (
                        <details className="text-sm">
                          <summary className="cursor-pointer text-accent-strong">What the caller already told us</summary>
                          <div className="mt-1 space-y-1 text-muted">
                            {c.context.summary ? <p>{c.context.summary}</p> : null}
                            {known.length ? <p>{known.map(([k, v]) => `${k}: ${v}`).join("; ")}</p> : null}
                            {c.context.open_questions?.length ? <p>Still open: {c.context.open_questions.join("; ")}</p> : null}
                          </div>
                        </details>
                      ) : null}
                      {c.note ? <p className="text-sm text-muted">Note: {c.note}</p> : null}
                      {canWrite && NEXT[c.status].length ? (
                        <div className="flex flex-wrap gap-2 pt-1">
                          {NEXT[c.status].map((n) => (
                            <Button key={n.to} size="sm" variant={n.to === "done" ? "accent" : "secondary"} disabled={busy === c.id} onClick={() => void move(c, n.to)}>{n.label}</Button>
                          ))}
                        </div>
                      ) : null}
                    </li>
                  );
                })}
              </ul>
              <div className="border-t border-border px-4"><Pagination page={page} pageCount={pageCount(data.total, PAGE_SIZE)} onPageChange={setPage} totalItems={data.total} /></div>
            </>
          )}
        </ResourceView>
      </Card>
    </>
  );
}
