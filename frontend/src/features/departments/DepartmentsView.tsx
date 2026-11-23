"use client";

import { Building2, Pencil, Plus, Trash2 } from "lucide-react";
import { useState, type FormEvent } from "react";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { FormError } from "@/components/ui/ErrorMessage";
import { Input } from "@/components/ui/Input";
import { Skeleton } from "@/components/ui/LoadingSpinner";
import { ConfirmDialog, Modal } from "@/components/ui/Modal";
import { ResourceView } from "@/components/ui/ResourceView";
import { Select, Textarea } from "@/components/ui/Select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/Table";
import { errorText, useDepartmentOptions } from "@/features/org/shared";
import { fromWeek, HoursEditor, summariseHours, toWeek } from "./HoursEditor";
import { useApiResource } from "@/hooks/useApiResource";
import { usePermission } from "@/hooks/usePermission";
import { api, ApiError } from "@/lib/api";
import type { Paginated } from "@/types/api";
import type { Department } from "@/types/org";

function DepartmentForm({ department, onSaved, onCancel }: { department: Department | null; onSaved: () => void; onCancel: () => void }) {
  const [name, setName] = useState(department?.name ?? "");
  const [description, setDescription] = useState(department?.description ?? "");
  const [alwaysOpen, setAlwaysOpen] = useState(department ? department.hours === null : true);
  const [week, setWeek] = useState(() => toWeek(department?.hours ?? null));
  const [timezone, setTimezone] = useState(department?.timezone ?? "");
  const [fallbackId, setFallbackId] = useState(department?.fallback_department_id ?? "");
  const [accepts, setAccepts] = useState(department?.accepts_transfers ?? true);
  const others = useDepartmentOptions().items.filter((d) => d.id !== department?.id);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFormError(null);
    if (name.trim().length < 2) {
      setErrors({ name: "Enter a department name (at least 2 characters)." });
      return;
    }
    setErrors({});
    const hours = alwaysOpen ? null : fromWeek(week);
    for (const spans of Object.values(hours ?? {})) {
      if (spans[0][0] >= spans[0][1]) {
        setErrors({ hours: "Each day must close after it opens." });
        return;
      }
    }
    const body = {
      name: name.trim(), description: description.trim() || null, hours, timezone: timezone.trim() || null,
      fallback_department_id: fallbackId || null, accepts_transfers: accepts,
    };
    setSaving(true);
    try {
      if (department) await api.patch(`/departments/${department.id}`, body);
      else await api.post("/departments", body);
      onSaved();
    } catch (error) {
      if (error instanceof ApiError && error.kind === "validation") setErrors(error.fieldErrors);
      setFormError(errorText(error));
      setSaving(false);
    }
  }

  return (
    <form onSubmit={onSubmit} noValidate className="space-y-4">
      {formError ? <FormError message={formError} /> : null}
      <Input label="Department name" name="name" value={name} onChange={(e) => setName(e.target.value)} error={errors.name} maxLength={100} />
      <Textarea label="What does this team handle? (optional)" name="description" rows={3} value={description} onChange={(e) => setDescription(e.target.value)} error={errors.description} maxLength={500} />
      <fieldset className="space-y-3 rounded-lg border border-border p-3">
        <legend className="px-1 text-sm font-medium text-ink">Calls and transfers</legend>
        <label className="flex items-center gap-2 text-sm text-ink">
          <input type="checkbox" checked={accepts} onChange={(e) => setAccepts(e.target.checked)} /> This team accepts transferred calls
        </label>
        <label className="flex items-center gap-2 text-sm text-ink">
          <input type="checkbox" checked={alwaysOpen} onChange={(e) => setAlwaysOpen(e.target.checked)} /> Always open (no opening hours)
        </label>
        {!alwaysOpen ? <HoursEditor week={week} onChange={setWeek} /> : null}
        {errors.hours ? <p role="alert" className="text-sm text-danger">{errors.hours}</p> : null}
        <Input label="Time zone (optional)" name="timezone" value={timezone} onChange={(e) => setTimezone(e.target.value)} error={errors.timezone} placeholder="Africa/Accra" hint="Leave empty to use the business time zone." />
        <Select label="If this team is closed or nobody answers, try" name="fallback" value={fallbackId} onChange={(e) => setFallbackId(e.target.value)} error={errors.fallback_department_id}>
          <option value="">No other team (offer a callback)</option>
          {others.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
        </Select>
      </fieldset>
      <div className="flex justify-end gap-2 pt-2">
        <Button variant="secondary" onClick={onCancel} disabled={saving}>
          Cancel
        </Button>
        <Button type="submit" loading={saving} loadingLabel="Saving">
          {department ? "Save changes" : "Add department"}
        </Button>
      </div>
    </form>
  );
}

export function DepartmentsView() {
  const canWrite = usePermission("departments:write");
  const resource = useApiResource<Paginated<Department>>("/departments", { page_size: 100 });
  const [editing, setEditing] = useState<Department | "new" | null>(null);
  const [deleting, setDeleting] = useState<Department | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function confirmDelete() {
    if (!deleting) return;
    setBusy(true);
    try {
      await api.delete(`/departments/${deleting.id}`);
      setDeleting(null);
      resource.reload();
    } catch (error) {
      setDeleteError(errorText(error));
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <PageHeader
        title="Departments"
        description="The teams that receive and resolve customer cases."
        actions={
          canWrite ? (
            <Button onClick={() => setEditing("new")}>
              <Plus aria-hidden="true" className="size-4" />
              Add department
            </Button>
          ) : null
        }
      />
      {deleteError ? (
        <div className="mb-4">
          <FormError message={deleteError} />
        </div>
      ) : null}
      <Card>
        <ResourceView
          resource={resource}
          compact={false}
          isEmpty={(d) => d.items.length === 0}
          skeleton={
            <div className="space-y-3 p-5">
              <Skeleton className="h-10" />
              <Skeleton className="h-10" />
            </div>
          }
          empty={
            <EmptyState
              icon={Building2}
              title="No departments yet"
              description="Create the teams in your business, such as Customer Service or Delivery, so cases can be routed to them."
              action={canWrite ? <Button onClick={() => setEditing("new")}>Add department</Button> : undefined}
            />
          }
        >
          {(data) => (
            <Table caption="Departments">
              <TableHead>
                <tr>
                  <TableHeader>Department</TableHeader>
                  <TableHeader>Call routing</TableHeader>
                  <TableHeader>Employees</TableHeader>
                  <TableHeader>Open cases</TableHeader>
                  {canWrite ? <TableHeader>
                    <span className="sr-only">Actions</span>
                  </TableHeader> : null}
                </tr>
              </TableHead>
              <TableBody>
                {data.items.map((d) => (
                  <TableRow key={d.id}>
                    <TableCell>
                      <p className="font-medium">{d.name}</p>
                      {d.description ? <p className="text-sm text-muted">{d.description}</p> : null}
                    </TableCell>
                    <TableCell>
                      <p>{d.accepts_transfers ? summariseHours(d.hours) : "Not taking transfers"}</p>
                      {d.fallback_department_id ? <p className="text-sm text-muted">Then {data.items.find((x) => x.id === d.fallback_department_id)?.name ?? "another team"}</p> : null}
                    </TableCell>
                    <TableCell>{d.employee_count ?? 0}</TableCell>
                    <TableCell>{d.open_cases ?? 0}</TableCell>
                    {canWrite ? (
                      <TableCell className="text-right">
                        <div className="flex justify-end gap-1">
                          <Button variant="ghost" size="sm" onClick={() => setEditing(d)} aria-label={`Edit ${d.name}`}>
                            <Pencil aria-hidden="true" className="size-4" />
                            Edit
                          </Button>
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => {
                              setDeleteError(null);
                              setDeleting(d);
                            }}
                            aria-label={`Delete ${d.name}`}
                          >
                            <Trash2 aria-hidden="true" className="size-4" />
                            Delete
                          </Button>
                        </div>
                      </TableCell>
                    ) : null}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </ResourceView>
      </Card>

      <Modal open={editing !== null} onClose={() => setEditing(null)} title={editing === "new" ? "Add department" : "Edit department"} size="lg">
        {editing !== null ? (
          <DepartmentForm
            department={editing === "new" ? null : editing}
            onCancel={() => setEditing(null)}
            onSaved={() => {
              setEditing(null);
              resource.reload();
            }}
          />
        ) : null}
      </Modal>
      <ConfirmDialog
        open={deleting !== null}
        onCancel={() => setDeleting(null)}
        onConfirm={() => void confirmDelete()}
        title={`Delete ${deleting?.name ?? "department"}?`}
        description="This can't be undone. A department that still has employees or cases can't be deleted."
        confirmLabel="Delete department"
        destructive
        loading={busy}
      />
    </>
  );
}
