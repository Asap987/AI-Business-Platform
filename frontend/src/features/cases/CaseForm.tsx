"use client";

import { useState, type FormEvent } from "react";
import { Button } from "@/components/ui/Button";
import { FormError } from "@/components/ui/ErrorMessage";
import { Input, SearchInput } from "@/components/ui/Input";
import { Select, Textarea } from "@/components/ui/Select";
import { useApiResource } from "@/hooks/useApiResource";
import { useDebouncedValue } from "@/hooks/useDebouncedValue";
import { api, ApiError } from "@/lib/api";
import { CASE_PRIORITIES, errorText, statusLabel, useDepartmentOptions } from "@/features/org/shared";
import type { Paginated } from "@/types/api";
import type { CaseItem, CasePriority, Customer } from "@/types/org";

function CustomerPicker({ selected, onSelect, error }: { selected: Customer | null; onSelect: (c: Customer | null) => void; error?: string }) {
  const [term, setTerm] = useState("");
  const debounced = useDebouncedValue(term.trim(), 300);
  const resource = useApiResource<Paginated<Customer>>(selected ? null : "/customers", { q: debounced || undefined, page_size: 5 });

  if (selected) {
    return (
      <div>
        <p className="mb-1.5 text-sm font-medium text-ink">Customer</p>
        <div className="flex items-center justify-between rounded-lg border border-border-strong bg-surface-muted px-3 py-2 text-sm">
          <span>
            <span className="font-medium text-ink">{selected.full_name}</span>
            {selected.phone ? <span className="ml-2 text-muted">{selected.phone}</span> : null}
          </span>
          <Button variant="ghost" size="sm" onClick={() => onSelect(null)}>
            Change
          </Button>
        </div>
      </div>
    );
  }

  const items = resource.data?.items ?? [];
  return (
    <div>
      <p className="mb-1.5 text-sm font-medium text-ink">Customer</p>
      <SearchInput label="Search customers by name, phone or email" placeholder="Search customers…" value={term} onValueChange={setTerm} />
      <ul aria-label="Matching customers" className="mt-2 divide-y divide-border rounded-lg border border-border">
        {resource.status === "loading" ? <li className="px-3 py-2 text-sm text-muted">Searching…</li> : null}
        {resource.status === "error" ? <li className="px-3 py-2 text-sm text-danger">Couldn’t load customers.</li> : null}
        {resource.status === "success" && items.length === 0 ? (
          <li className="px-3 py-2 text-sm text-muted">No customers found. Add the customer on the Customers page first.</li>
        ) : null}
        {items.map((c) => (
          <li key={c.id}>
            <button type="button" onClick={() => onSelect(c)} className="flex w-full items-center justify-between px-3 py-2 text-left text-sm hover:bg-surface-muted">
              <span className="font-medium text-ink">{c.full_name}</span>
              <span className="text-muted">{c.phone ?? c.email ?? ""}</span>
            </button>
          </li>
        ))}
      </ul>
      {error ? (
        <p role="alert" className="mt-1.5 text-sm text-danger">
          {error}
        </p>
      ) : null}
    </div>
  );
}

export function CaseForm({ onCreated, onCancel }: { onCreated: (created: CaseItem) => void; onCancel: () => void }) {
  const departments = useDepartmentOptions();
  const [customer, setCustomer] = useState<Customer | null>(null);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [priority, setPriority] = useState<CasePriority>("medium");
  const [departmentId, setDepartmentId] = useState("");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFormError(null);
    const found: Record<string, string> = {};
    if (!customer) found.customer_id = "Choose the customer this case is for.";
    if (title.trim().length < 3) found.title = "Describe the problem in at least 3 characters.";
    setErrors(found);
    if (Object.keys(found).length > 0 || !customer) return;

    setSubmitting(true);
    try {
      const created = await api.post<CaseItem>("/cases", {
        customer_id: customer.id,
        title: title.trim(),
        description: description.trim() || null,
        priority,
        department_id: departmentId || null,
      });
      onCreated({ ...created, customer_name: customer.full_name });
    } catch (error) {
      if (error instanceof ApiError && error.kind === "validation" && Object.keys(error.fieldErrors).length > 0) {
        setErrors(error.fieldErrors);
      }
      setFormError(errorText(error));
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={onSubmit} noValidate className="space-y-4">
      {formError ? <FormError message={formError} /> : null}
      <CustomerPicker selected={customer} onSelect={setCustomer} error={errors.customer_id} />
      <Input label="What is the problem?" name="title" value={title} onChange={(e) => setTitle(e.target.value)} error={errors.title} maxLength={200} />
      <Textarea label="Details (optional)" name="description" value={description} onChange={(e) => setDescription(e.target.value)} error={errors.description} maxLength={5000} />
      <div className="grid gap-4 sm:grid-cols-2">
        <Select label="Priority" name="priority" value={priority} onChange={(e) => setPriority(e.target.value as CasePriority)}>
          {CASE_PRIORITIES.map((p) => (
            <option key={p} value={p}>
              {statusLabel(p)}
            </option>
          ))}
        </Select>
        {departments.allowed ? (
          <Select label="Department (optional)" name="department" value={departmentId} onChange={(e) => setDepartmentId(e.target.value)} error={errors.department_id}>
            <option value="">Not assigned yet</option>
            {departments.items.map((d) => (
              <option key={d.id} value={d.id}>
                {d.name}
              </option>
            ))}
          </Select>
        ) : null}
      </div>
      <div className="flex justify-end gap-2 pt-2">
        <Button variant="secondary" onClick={onCancel} disabled={submitting}>
          Cancel
        </Button>
        <Button type="submit" loading={submitting} loadingLabel="Creating case">
          Create case
        </Button>
      </div>
    </form>
  );
}
