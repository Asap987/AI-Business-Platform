"use client";

import { ArrowLeft, Mail, Pencil, Phone, Hash } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Skeleton } from "@/components/ui/LoadingSpinner";
import { Modal } from "@/components/ui/Modal";
import { ResourceView } from "@/components/ui/ResourceView";
import { CasesView } from "@/features/cases/CasesView";
import { CustomerForm } from "@/features/customers/CustomerForm";
import { useApiResource } from "@/hooks/useApiResource";
import { usePermission } from "@/hooks/usePermission";
import { formatRelativeTime } from "@/lib/utils";
import type { Customer } from "@/types/org";

function Detail({ icon: Icon, label, value }: { icon: typeof Mail; label: string; value: string | null }) {
  return (
    <div className="flex items-start gap-3">
      <Icon aria-hidden="true" className="mt-0.5 size-4 shrink-0 text-muted" />
      <div className="min-w-0">
        <dt className="text-xs text-muted">{label}</dt>
        <dd className="break-words text-sm text-ink">{value ?? "—"}</dd>
      </div>
    </div>
  );
}

export function CustomerDetailView() {
  const { id } = useParams<{ id: string }>();
  const canWrite = usePermission("customers:write");
  const canReadCases = usePermission("cases:read");
  const resource = useApiResource<Customer>(`/customers/${id}`);
  const [editing, setEditing] = useState(false);

  return (
    <>
      <Link href="/customers" className="mb-4 inline-flex items-center gap-1.5 text-sm font-medium text-muted hover:text-ink">
        <ArrowLeft aria-hidden="true" className="size-4" />
        Back to customers
      </Link>
      <ResourceView
        resource={resource}
        compact={false}
        skeleton={
          <div className="space-y-3">
            <Skeleton className="h-10 w-2/3" />
            <Skeleton className="h-32" />
          </div>
        }
      >
        {(c) => (
          <>
            <PageHeader
              title={c.full_name}
              description={`Customer since ${formatRelativeTime(c.created_at)}`}
              actions={
                canWrite ? (
                  <Button variant="secondary" onClick={() => setEditing(true)}>
                    <Pencil aria-hidden="true" className="size-4" />
                    Edit customer
                  </Button>
                ) : null
              }
            />
            <Card className="mb-8 p-5">
              <dl className="grid gap-5 sm:grid-cols-3">
                <Detail icon={Phone} label="Phone" value={c.phone} />
                <Detail icon={Mail} label="Email" value={c.email} />
                <Detail icon={Hash} label="Your reference" value={c.external_ref} />
              </dl>
            </Card>
            {canReadCases ? <CasesView customer={c} /> : null}
            <Modal open={editing} onClose={() => setEditing(false)} title="Edit customer">
              {editing ? (
                <CustomerForm
                  customer={c}
                  onCancel={() => setEditing(false)}
                  onSaved={() => {
                    setEditing(false);
                    resource.reload();
                  }}
                />
              ) : null}
            </Modal>
          </>
        )}
      </ResourceView>
    </>
  );
}
