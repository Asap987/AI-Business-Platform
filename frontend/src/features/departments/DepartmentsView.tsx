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
import { Textarea } from "@/components/ui/Select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/Table";
import { errorText } from "@/features/org/shared";
import { useApiResource } from "@/hooks/useApiResource";
import { usePermission } from "@/hooks/usePermission";
import { api, ApiError } from "@/lib/api";
import type { Paginated } from "@/types/api";
import type { Department } from "@/types/org";

function DepartmentForm({ department, onSaved, onCancel }: { department: Department | null; onSaved: () => void; onCancel: () => void }) {
  const [name, setName] = useState(department?.name ?? "");
  const [description, setDescription] = useState(department?.description ?? "");
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
    const body = { name: name.trim(), description: description.trim() || null };
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

      <Modal open={editing !== null} onClose={() => setEditing(null)} title={editing === "new" ? "Add department" : "Edit department"}>
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
