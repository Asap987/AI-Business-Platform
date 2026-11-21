"use client";

import { ArrowLeft } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState, type FormEvent } from "react";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/Button";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { StatusBadge } from "@/components/ui/Badge";
import { ConfirmDialog } from "@/components/ui/Modal";
import { FormError } from "@/components/ui/ErrorMessage";
import { Skeleton } from "@/components/ui/LoadingSpinner";
import { ResourceView } from "@/components/ui/ResourceView";
import { Select, Textarea } from "@/components/ui/Select";
import { CASE_PRIORITIES, NEXT_STATUSES, PriorityBadge, errorText, statusLabel, useDepartmentOptions, useEmployeeOptions } from "@/features/org/shared";
import { useApiResource } from "@/hooks/useApiResource";
import { usePermission } from "@/hooks/usePermission";
import { api } from "@/lib/api";
import { formatRelativeTime, humanize } from "@/lib/utils";
import type { CaseEvent, CaseItem, CasePriority, CaseStatus } from "@/types/org";

type NameMap = Map<string, string>;

function describeEvent(e: CaseEvent, departments: NameMap, employees: NameMap): string[] {
  const d = e.detail as Record<string, unknown>;
  const pair = (key: string): [string | null, string | null] | null => {
    const v = d[key];
    return Array.isArray(v) && v.length === 2 ? [v[0] as string | null, v[1] as string | null] : null;
  };
  const lines: string[] = [];
  if (e.kind === "created") lines.push("Case opened");
  const status = pair("status");
  if (status) lines.push(`Status changed from ${statusLabel(String(status[0]))} to ${statusLabel(String(status[1]))}`);
  const priority = pair("priority");
  if (priority) lines.push(`Priority changed from ${statusLabel(String(priority[0]))} to ${statusLabel(String(priority[1]))}`);
  const dept = pair("department_id");
  if (dept) lines.push(`Department: ${dept[1] ? (departments.get(dept[1]) ?? "changed") : "removed"}`);
  const emp = pair("assigned_employee_id");
  if (emp) lines.push(emp[1] ? `Assigned to ${employees.get(emp[1]) ?? "a team member"}` : "Unassigned");
  if (Array.isArray(d.fields_changed)) lines.push(`Edited ${(d.fields_changed as string[]).map((f) => humanize(f).toLowerCase()).join(", ")}`);
  return lines.length > 0 ? lines : [humanize(e.kind)];
}

function actorLabel(kind: CaseEvent["actor_kind"]): string {
  return kind === "ai" ? "AI assistant" : kind === "system" ? "System" : "Team member";
}

function UpdateForm({ item, onSaved }: { item: CaseItem; onSaved: () => void }) {
  const departments = useDepartmentOptions();
  const employees = useEmployeeOptions(true);
  const [status, setStatus] = useState<CaseStatus>(item.status);
  const [priority, setPriority] = useState<CasePriority>(item.priority);
  const [departmentId, setDepartmentId] = useState(item.department_id ?? "");
  const [assigneeId, setAssigneeId] = useState(item.assigned_employee_id ?? "");
  const [notes, setNotes] = useState(item.resolution_notes ?? "");
  const [error, setError] = useState<string | null>(null);
  const [notesError, setNotesError] = useState<string | undefined>();
  const [saving, setSaving] = useState(false);
  const [confirmClose, setConfirmClose] = useState(false);

  async function save() {
    setError(null);
    setNotesError(undefined);
    const changes: Record<string, unknown> = {};
    if (status !== item.status) changes.status = status;
    if (priority !== item.priority) changes.priority = priority;
    if (departments.allowed && departmentId !== (item.department_id ?? "")) changes.department_id = departmentId || null;
    if (employees.allowed && assigneeId !== (item.assigned_employee_id ?? "")) changes.assigned_employee_id = assigneeId || null;
    if (notes.trim() !== (item.resolution_notes ?? "").trim()) changes.resolution_notes = notes.trim() || null;
    if (Object.keys(changes).length === 0) {
      setError("Nothing has changed.");
      return;
    }
    if (status === "resolved" && item.status !== "resolved" && !notes.trim()) {
      setNotesError("Describe how the problem was resolved before resolving the case.");
      return;
    }
    setSaving(true);
    try {
      await api.patch<CaseItem>(`/cases/${item.id}`, changes);
      onSaved();
    } catch (e) {
      setError(errorText(e));
      setSaving(false);
    }
  }

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (status === "closed" && item.status !== "closed") setConfirmClose(true);
    else void save();
  }

  const statusOptions = [item.status, ...NEXT_STATUSES[item.status]];
  const assigneeKnown = employees.items.some((e) => e.id === assigneeId);

  return (
    <form onSubmit={onSubmit} noValidate className="space-y-4">
      {error ? <FormError message={error} /> : null}
      <div className="grid gap-4 sm:grid-cols-2">
        <Select label="Status" value={status} onChange={(e) => setStatus(e.target.value as CaseStatus)}>
          {statusOptions.map((s) => (
            <option key={s} value={s}>
              {statusLabel(s)}
            </option>
          ))}
        </Select>
        <Select label="Priority" value={priority} onChange={(e) => setPriority(e.target.value as CasePriority)}>
          {CASE_PRIORITIES.map((p) => (
            <option key={p} value={p}>
              {statusLabel(p)}
            </option>
          ))}
        </Select>
        {departments.allowed ? (
          <Select label="Department" value={departmentId} onChange={(e) => setDepartmentId(e.target.value)}>
            <option value="">No department</option>
            {departments.items.map((d) => (
              <option key={d.id} value={d.id}>
                {d.name}
              </option>
            ))}
          </Select>
        ) : null}
        {employees.allowed ? (
          <Select label="Assigned to" value={assigneeId} onChange={(e) => setAssigneeId(e.target.value)}>
            <option value="">Unassigned</option>
            {assigneeId && !assigneeKnown ? <option value={assigneeId}>Current assignee (not available)</option> : null}
            {employees.items.map((e) => (
              <option key={e.id} value={e.id}>
                {e.full_name}
              </option>
            ))}
          </Select>
        ) : null}
      </div>
      <Textarea
        label="Resolution notes"
        hint="Required when resolving a case."
        value={notes}
        onChange={(e) => setNotes(e.target.value)}
        error={notesError}
        maxLength={5000}
      />
      <div className="flex justify-end">
        <Button type="submit" loading={saving} loadingLabel="Saving">
          Save changes
        </Button>
      </div>
      <ConfirmDialog
        open={confirmClose}
        onCancel={() => setConfirmClose(false)}
        onConfirm={() => {
          setConfirmClose(false);
          void save();
        }}
        title="Close this case?"
        description="A closed case is final: it can no longer be changed or reopened."
        confirmLabel="Close case"
        destructive
      />
    </form>
  );
}

export function CaseDetailView() {
  const params = useParams<{ id: string }>();
  const id = params.id;
  const canWrite = usePermission("cases:write");
  const item = useApiResource<CaseItem>(`/cases/${encodeURIComponent(id)}`);
  const events = useApiResource<{ items: CaseEvent[] }>(`/cases/${encodeURIComponent(id)}/events`);
  const departments = useDepartmentOptions();
  const employees = useEmployeeOptions();

  const reloadAll = () => {
    item.reload();
    events.reload();
  };

  return (
    <>
      <Link href="/cases" className="mb-4 inline-flex items-center gap-1.5 text-sm font-medium text-muted hover:text-ink">
        <ArrowLeft aria-hidden="true" className="size-4" />
        Back to cases
      </Link>
      <ResourceView
        resource={item}
        compact={false}
        skeleton={
          <div className="space-y-3">
            <Skeleton className="h-10 w-2/3" />
            <Skeleton className="h-40" />
          </div>
        }
      >
        {(c) => (
          <>
            <PageHeader
              title={c.title}
              description={`For ${c.customer_name ?? "customer"} · opened ${formatRelativeTime(c.opened_at)}`}
              actions={
                <>
                  <PriorityBadge priority={c.priority} />
                  <StatusBadge status={c.status} />
                </>
              }
            />
            <div className="grid gap-6 lg:grid-cols-[1fr_22rem]">
              <div className="space-y-6">
                <Card>
                  <CardHeader title="Problem description" />
                  <CardBody>
                    <p className="whitespace-pre-wrap text-sm text-ink">{c.description || "No details were given."}</p>
                    {c.status === "resolved" || c.status === "closed" ? (
                      <div className="mt-4 rounded-lg bg-success-soft p-3 text-sm text-success">
                        <p className="font-medium">Resolution</p>
                        <p className="mt-1 whitespace-pre-wrap">{c.resolution_notes}</p>
                      </div>
                    ) : null}
                  </CardBody>
                </Card>
                <Card>
                  <CardHeader title="Update case" description={canWrite ? undefined : "You can view this case but not change it."} />
                  <CardBody>
                    {!canWrite ? (
                      <p className="text-sm text-muted">Your role has read-only access to cases.</p>
                    ) : c.status === "closed" ? (
                      <p className="text-sm text-muted">This case is closed and can no longer be changed.</p>
                    ) : (
                      // Remounts with fresh values after every save.
                      <UpdateForm key={c.updated_at} item={c} onSaved={reloadAll} />
                    )}
                  </CardBody>
                </Card>
              </div>
              <Card className="h-fit">
                <CardHeader title="History" description="Everything that happened to this case." />
                <ResourceView
                  resource={events}
                  skeleton={
                    <div className="space-y-3 p-5">
                      <Skeleton className="h-8" />
                      <Skeleton className="h-8" />
                    </div>
                  }
                >
                  {(data) => (
                    <ol className="space-y-4 p-5">
                      {[...data.items].reverse().map((e) => (
                        <li key={e.id} className="text-sm">
                          {describeEvent(e, departments.names, employees.names).map((line) => (
                            <p key={line} className="text-ink">
                              {line}
                            </p>
                          ))}
                          <p className="mt-0.5 text-xs text-muted">
                            {actorLabel(e.actor_kind)} · {formatRelativeTime(e.created_at)}
                          </p>
                        </li>
                      ))}
                    </ol>
                  )}
                </ResourceView>
              </Card>
            </div>
          </>
        )}
      </ResourceView>
    </>
  );
}
