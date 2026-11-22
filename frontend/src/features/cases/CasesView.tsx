"use client";

import { LifeBuoy, Plus } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { SearchInput } from "@/components/ui/Input";
import { Skeleton } from "@/components/ui/LoadingSpinner";
import { Modal } from "@/components/ui/Modal";
import { Pagination } from "@/components/ui/Pagination";
import { ResourceView } from "@/components/ui/ResourceView";
import { Select } from "@/components/ui/Select";
import { StatusBadge } from "@/components/ui/Badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/Table";
import { CaseForm } from "@/features/cases/CaseForm";
import { CASE_PRIORITIES, CASE_STATUSES, PriorityBadge, pageCount, statusLabel, useDepartmentOptions, useEmployeeOptions } from "@/features/org/shared";
import { useApiResource } from "@/hooks/useApiResource";
import { useDebouncedValue } from "@/hooks/useDebouncedValue";
import { usePermission } from "@/hooks/usePermission";
import { formatRelativeTime } from "@/lib/utils";
import type { Paginated } from "@/types/api";
import type { CaseItem, Customer } from "@/types/org";

const PAGE_SIZE = 20;

/** Pass `customer` to show only that customer's cases inside their page (no page header, no customer column). */
export function CasesView({ customer }: { customer?: Customer } = {}) {
  const router = useRouter();
  const canWrite = usePermission("cases:write");
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState("");
  const [priority, setPriority] = useState("");
  const [search, setSearch] = useState("");
  const [creating, setCreating] = useState(false);
  const q = useDebouncedValue(search.trim(), 300);

  const departments = useDepartmentOptions();
  const employees = useEmployeeOptions();
  const resource = useApiResource<Paginated<CaseItem>>("/cases", {
    page, page_size: PAGE_SIZE, status: status || undefined, priority: priority || undefined, q: q || undefined,
    customer_id: customer?.id,
  });

  // Any filter change goes back to the first page.
  const filter = <T,>(set: (v: T) => void) => (v: T) => {
    set(v);
    setPage(1);
  };
  const filtered = Boolean(status || priority || q);
  const newCaseButton = canWrite ? (
    <Button onClick={() => setCreating(true)}>
      <Plus aria-hidden="true" className="size-4" />
      New case
    </Button>
  ) : null;

  return (
    <>
      {customer ? (
        <div className="mb-3 flex items-center justify-between gap-3">
          <h2 className="text-base font-semibold text-ink">Cases</h2>
          {newCaseButton}
        </div>
      ) : (
        <PageHeader title="Cases & Escalations" description="Customer problems that need resolution, and who is working on them." actions={newCaseButton} />
      )}

      <Card>
        <div className="grid gap-3 border-b border-border p-4 sm:grid-cols-[1fr_12rem_10rem]">
          <SearchInput label="Search cases" placeholder="Search cases…" value={search} onValueChange={filter(setSearch)} />
          <Select label="Status" hideLabel value={status} onChange={(e) => filter(setStatus)(e.target.value)}>
            <option value="">All statuses</option>
            {CASE_STATUSES.map((s) => (
              <option key={s} value={s}>
                {statusLabel(s)}
              </option>
            ))}
          </Select>
          <Select label="Priority" hideLabel value={priority} onChange={(e) => filter(setPriority)(e.target.value)}>
            <option value="">All priorities</option>
            {CASE_PRIORITIES.map((p) => (
              <option key={p} value={p}>
                {statusLabel(p)}
              </option>
            ))}
          </Select>
        </div>

        <ResourceView
          resource={resource}
          compact={false}
          isEmpty={(d) => d.items.length === 0}
          skeleton={
            <div className="space-y-3 p-5">
              <Skeleton className="h-10" />
              <Skeleton className="h-10" />
              <Skeleton className="h-10" />
            </div>
          }
          empty={
            <EmptyState
              icon={LifeBuoy}
              title={filtered ? "No cases match these filters" : "No cases yet"}
              description={filtered ? "Try a different search or clear the filters." : "Cases appear here when a customer problem is logged by you or by an AI agent."}
              action={!filtered && canWrite ? <Button onClick={() => setCreating(true)}>New case</Button> : undefined}
            />
          }
        >
          {(data) => (
            <>
              <Table caption="Cases">
                <TableHead>
                  <tr>
                    <TableHeader>Case</TableHeader>
                    {customer ? null : <TableHeader>Customer</TableHeader>}
                    <TableHeader>Priority</TableHeader>
                    <TableHeader>Status</TableHeader>
                    <TableHeader>Department</TableHeader>
                    <TableHeader>Assigned to</TableHeader>
                    <TableHeader>Opened</TableHeader>
                  </tr>
                </TableHead>
                <TableBody>
                  {data.items.map((c) => (
                    <TableRow key={c.id}>
                      <TableCell className="max-w-xs">
                        <Link href={`/cases/${c.id}`} className="font-medium text-accent-strong hover:underline">
                          {c.title}
                        </Link>
                      </TableCell>
                      {customer ? null : <TableCell>{c.customer_name ?? "—"}</TableCell>}
                      <TableCell>
                        <PriorityBadge priority={c.priority} />
                      </TableCell>
                      <TableCell>
                        <StatusBadge status={c.status} />
                      </TableCell>
                      <TableCell>{c.department_id ? (departments.names.get(c.department_id) ?? "—") : "—"}</TableCell>
                      <TableCell>
                        {c.assigned_employee_id ? (employees.allowed ? (employees.names.get(c.assigned_employee_id) ?? "—") : "Assigned") : "Unassigned"}
                      </TableCell>
                      <TableCell className="text-muted">{formatRelativeTime(c.opened_at)}</TableCell>
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

      <Modal open={creating} onClose={() => setCreating(false)} title="New case" description="Log a customer problem so the right team can resolve it." size="lg">
        {creating ? (
          <CaseForm
            initialCustomer={customer}
            onCancel={() => setCreating(false)}
            onCreated={(created) => {
              setCreating(false);
              router.push(`/cases/${created.id}`);
            }}
          />
        ) : null}
      </Modal>
    </>
  );
}
