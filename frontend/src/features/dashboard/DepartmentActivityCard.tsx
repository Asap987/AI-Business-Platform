"use client";

import { Building2 } from "lucide-react";
import Link from "next/link";
import { useDepartmentActivity } from "@/features/dashboard/api";
import { Card, CardHeader } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { Skeleton } from "@/components/ui/LoadingSpinner";
import { ResourceView } from "@/components/ui/ResourceView";
import { ButtonLink } from "@/components/ui/Button";
import { formatNumber } from "@/lib/utils";

export function DepartmentActivityCard() {
  const resource = useDepartmentActivity();

  return (
    <Card>
      <CardHeader
        title="Department activity"
        description="Workload and pending requests by department."
        action={
          <Link href="/departments" className="text-sm font-medium text-accent-strong hover:underline">
            View departments
          </Link>
        }
      />
      <ResourceView
        resource={resource}
        isEmpty={(data) => data.items.length === 0}
        skeleton={
          <div className="space-y-3 p-5">
            <Skeleton className="h-10" />
            <Skeleton className="h-10" />
            <Skeleton className="h-10" />
          </div>
        }
        empty={
          <EmptyState
            compact
            icon={Building2}
            title="No departments yet"
            description="Add departments such as Technical, Finance or Delivery to see their workload here."
            action={
              <ButtonLink href="/departments" size="sm">
                Go to departments
              </ButtonLink>
            }
          />
        }
      >
        {(data) => (
          <ul className="divide-y divide-border">
            {data.items.map((department) => (
              <li key={department.id} className="flex items-center justify-between gap-4 px-5 py-3.5">
                <span className="min-w-0 truncate text-sm font-medium text-ink">{department.name}</span>
                <span className="flex shrink-0 gap-5 text-right text-sm">
                  <span>
                    <span className="block font-semibold text-ink">{formatNumber(department.open_cases)}</span>
                    <span className="block text-xs text-muted">Open cases</span>
                  </span>
                  <span>
                    <span className="block font-semibold text-ink">{formatNumber(department.pending_requests)}</span>
                    <span className="block text-xs text-muted">Pending</span>
                  </span>
                </span>
              </li>
            ))}
          </ul>
        )}
      </ResourceView>
    </Card>
  );
}
