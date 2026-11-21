"use client";

import { Contact, Pencil, Plus } from "lucide-react";
import Link from "next/link";
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
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/Table";
import { CustomerForm } from "@/features/customers/CustomerForm";
import { pageCount } from "@/features/org/shared";
import { useApiResource } from "@/hooks/useApiResource";
import { useDebouncedValue } from "@/hooks/useDebouncedValue";
import { usePermission } from "@/hooks/usePermission";
import { formatRelativeTime } from "@/lib/utils";
import type { Paginated } from "@/types/api";
import type { Customer } from "@/types/org";

const PAGE_SIZE = 20;

export function CustomersView() {
  const canWrite = usePermission("customers:write");
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [editing, setEditing] = useState<Customer | "new" | null>(null);
  const q = useDebouncedValue(search.trim(), 300);
  const resource = useApiResource<Paginated<Customer>>("/customers", { page, page_size: PAGE_SIZE, q: q || undefined });

  return (
    <>
      <PageHeader
        title="Customers"
        description="The people and companies your business talks to."
        actions={
          canWrite ? (
            <Button onClick={() => setEditing("new")}>
              <Plus aria-hidden="true" className="size-4" />
              Add customer
            </Button>
          ) : null
        }
      />
      <Card>
        <div className="border-b border-border p-4">
          <SearchInput
            label="Search customers"
            placeholder="Search by name, phone, email or reference…"
            value={search}
            onValueChange={(v) => {
              setSearch(v);
              setPage(1);
            }}
          />
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
              icon={Contact}
              title={q ? "No customers match your search" : "No customers yet"}
              description={q ? "Check the spelling or try a phone number." : "Add the people you serve so cases can be linked to them."}
              action={!q && canWrite ? <Button onClick={() => setEditing("new")}>Add customer</Button> : undefined}
            />
          }
        >
          {(data) => (
            <>
              <Table caption="Customers">
                <TableHead>
                  <tr>
                    <TableHeader>Name</TableHeader>
                    <TableHeader>Phone</TableHeader>
                    <TableHeader>Email</TableHeader>
                    <TableHeader>Reference</TableHeader>
                    <TableHeader>Added</TableHeader>
                    {canWrite ? <TableHeader>
                      <span className="sr-only">Actions</span>
                    </TableHeader> : null}
                  </tr>
                </TableHead>
                <TableBody>
                  {data.items.map((c) => (
                    <TableRow key={c.id}>
                      <TableCell className="font-medium">
                        <Link href={`/customers/${c.id}`} className="text-accent-strong hover:underline">
                          {c.full_name}
                        </Link>
                      </TableCell>
                      <TableCell>{c.phone ?? "—"}</TableCell>
                      <TableCell>{c.email ?? "—"}</TableCell>
                      <TableCell>{c.external_ref ?? "—"}</TableCell>
                      <TableCell className="text-muted">{formatRelativeTime(c.created_at)}</TableCell>
                      {canWrite ? (
                        <TableCell className="text-right">
                          <Button variant="ghost" size="sm" onClick={() => setEditing(c)} aria-label={`Edit ${c.full_name}`}>
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

      <Modal open={editing !== null} onClose={() => setEditing(null)} title={editing === "new" ? "Add customer" : "Edit customer"}>
        {editing !== null ? (
          <CustomerForm
            customer={editing === "new" ? null : editing}
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
