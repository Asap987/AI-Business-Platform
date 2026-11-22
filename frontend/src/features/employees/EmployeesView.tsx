"use client";

import { Pencil, Plus, Users } from "lucide-react";
import { useState, type FormEvent } from "react";
import { PageHeader } from "@/components/layout/PageHeader";
import { StatusBadge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { FormError } from "@/components/ui/ErrorMessage";
import { Input, SearchInput } from "@/components/ui/Input";
import { Skeleton } from "@/components/ui/LoadingSpinner";
import { Modal } from "@/components/ui/Modal";
import { Pagination } from "@/components/ui/Pagination";
import { ResourceView } from "@/components/ui/ResourceView";
import { Select } from "@/components/ui/Select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/Table";
import { errorText, pageCount, statusLabel, useDepartmentOptions } from "@/features/org/shared";
import { useApiResource } from "@/hooks/useApiResource";
import { useDebouncedValue } from "@/hooks/useDebouncedValue";
import { usePermission } from "@/hooks/usePermission";
import { api, ApiError } from "@/lib/api";
import type { Paginated } from "@/types/api";
import type { Employee, EmployeeStatus } from "@/types/org";

const PAGE_SIZE = 20;
const EMPLOYEE_STATUSES: EmployeeStatus[] = ["active", "on_leave", "inactive"];

function EmployeeForm({ employee, onSaved, onCancel }: { employee: Employee | null; onSaved: () => void; onCancel: () => void }) {
  const departments = useDepartmentOptions();
  const [fullName, setFullName] = useState(employee?.full_name ?? "");
  const [email, setEmail] = useState(employee?.email ?? "");
  const [phone, setPhone] = useState(employee?.phone ?? "");
  const [jobTitle, setJobTitle] = useState(employee?.job_title ?? "");
  const [departmentId, setDepartmentId] = useState(employee?.department_id ?? "");
  const [status, setStatus] = useState<EmployeeStatus>(employee?.status ?? "active");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFormError(null);
    if (fullName.trim().length < 2) {
      setErrors({ full_name: "Enter the employee's name." });
      return;
    }
    setErrors({});
    const body = {
      full_name: fullName.trim(),
      email: email.trim() || null,
      phone: phone.trim() || null,
      job_title: jobTitle.trim() || null,
      department_id: departmentId || null,
      status,
    };
    setSaving(true);
    try {
      if (employee) await api.patch(`/employees/${employee.id}`, body);
      else await api.post("/employees", body);
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
      <Input label="Full name" name="full_name" value={fullName} onChange={(e) => setFullName(e.target.value)} error={errors.full_name} maxLength={200} />
      <div className="grid gap-4 sm:grid-cols-2">
        <Input label="Email (optional)" name="email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} error={errors.email} maxLength={254} />
        <Input label="Phone (optional)" name="phone" type="tel" value={phone} onChange={(e) => setPhone(e.target.value)} error={errors.phone} maxLength={40} />
        <Input label="Job title (optional)" name="job_title" value={jobTitle} onChange={(e) => setJobTitle(e.target.value)} error={errors.job_title} maxLength={100} />
        <Select label="Status" name="status" value={status} onChange={(e) => setStatus(e.target.value as EmployeeStatus)} error={errors.status}>
          {EMPLOYEE_STATUSES.map((s) => (
            <option key={s} value={s}>
              {statusLabel(s)}
            </option>
          ))}
        </Select>
      </div>
      {departments.allowed ? (
        <Select label="Department" name="department" value={departmentId} onChange={(e) => setDepartmentId(e.target.value)} error={errors.department_id}>
          <option value="">No department</option>
          {departments.items.map((d) => (
            <option key={d.id} value={d.id}>
              {d.name}
            </option>
          ))}
        </Select>
      ) : null}
      <div className="flex justify-end gap-2 pt-2">
        <Button variant="secondary" onClick={onCancel} disabled={saving}>
          Cancel
        </Button>
        <Button type="submit" loading={saving} loadingLabel="Saving">
          {employee ? "Save changes" : "Add employee"}
        </Button>
      </div>
    </form>
  );
}

export function EmployeesView() {
  const canWrite = usePermission("employees:write");
  const departments = useDepartmentOptions();
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
  const [departmentId, setDepartmentId] = useState("");
  const [editing, setEditing] = useState<Employee | "new" | null>(null);
  const q = useDebouncedValue(search.trim(), 300);
  const resource = useApiResource<Paginated<Employee>>("/employees", {
    page, page_size: PAGE_SIZE, q: q || undefined, status: status || undefined, department_id: departmentId || undefined,
  });
  const filtered = Boolean(q || status || departmentId);
  const reset = <T,>(set: (v: T) => void) => (v: T) => {
    set(v);
    setPage(1);
  };

  return (
    <>
      <PageHeader
        title="Employees"
        description="The people who work cases and answer customers."
        actions={
          canWrite ? (
            <Button onClick={() => setEditing("new")}>
              <Plus aria-hidden="true" className="size-4" />
              Add employee
            </Button>
          ) : null
        }
      />
      <Card>
        <div className="grid gap-3 border-b border-border p-4 sm:grid-cols-[1fr_12rem_12rem]">
          <SearchInput label="Search employees" placeholder="Search by name, email or job title…" value={search} onValueChange={reset(setSearch)} />
          <Select label="Status" hideLabel value={status} onChange={(e) => reset(setStatus)(e.target.value)}>
            <option value="">All statuses</option>
            {EMPLOYEE_STATUSES.map((s) => (
              <option key={s} value={s}>
                {statusLabel(s)}
              </option>
            ))}
          </Select>
          {departments.allowed ? (
            <Select label="Department" hideLabel value={departmentId} onChange={(e) => reset(setDepartmentId)(e.target.value)}>
              <option value="">All departments</option>
              {departments.items.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.name}
                </option>
              ))}
            </Select>
          ) : null}
        </div>
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
              icon={Users}
              title={filtered ? "No employees match these filters" : "No employees yet"}
              description={filtered ? "Try a different search or clear the filters." : "Add your staff so cases can be assigned to them."}
              action={!filtered && canWrite ? <Button onClick={() => setEditing("new")}>Add employee</Button> : undefined}
            />
          }
        >
          {(data) => (
            <>
              <Table caption="Employees">
                <TableHead>
                  <tr>
                    <TableHeader>Name</TableHeader>
                    <TableHeader>Job title</TableHeader>
                    <TableHeader>Department</TableHeader>
                    <TableHeader>Contact</TableHeader>
                    <TableHeader>Status</TableHeader>
                    {canWrite ? <TableHeader>
                      <span className="sr-only">Actions</span>
                    </TableHeader> : null}
                  </tr>
                </TableHead>
                <TableBody>
                  {data.items.map((e) => (
                    <TableRow key={e.id}>
                      <TableCell className="font-medium">{e.full_name}</TableCell>
                      <TableCell>{e.job_title ?? "—"}</TableCell>
                      <TableCell>{e.department_id ? (departments.names.get(e.department_id) ?? "—") : "—"}</TableCell>
                      <TableCell>
                        <p>{e.email ?? "—"}</p>
                        {e.phone ? <p className="text-sm text-muted">{e.phone}</p> : null}
                      </TableCell>
                      <TableCell>
                        <StatusBadge status={e.status} />
                      </TableCell>
                      {canWrite ? (
                        <TableCell className="text-right">
                          <Button variant="ghost" size="sm" onClick={() => setEditing(e)} aria-label={`Edit ${e.full_name}`}>
                            <Pencil aria-hidden="true" className="size-4" />
                            Edit
                          </Button>
                        </TableCell>
                      ) : null}
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
              <div className="border-t border-border px-4">
                <Pagination page={page} pageCount={pageCount(data.total, PAGE_SIZE)} onPageChange={setPage} totalItems={data.total} />
              </div>
            </>
          )}
        </ResourceView>
      </Card>

      <Modal open={editing !== null} onClose={() => setEditing(null)} title={editing === "new" ? "Add employee" : "Edit employee"} size="lg">
        {editing !== null ? (
          <EmployeeForm
            employee={editing === "new" ? null : editing}
            onCancel={() => setEditing(null)}
            onSaved={() => {
              setEditing(null);
              resource.reload();
            }}
          />
        ) : null}
      </Modal>
    </>
  );
}
