"use client";

import Link from "next/link";
import { useCaseOverview } from "@/features/dashboard/api";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { Skeleton } from "@/components/ui/LoadingSpinner";
import { ResourceView } from "@/components/ui/ResourceView";
import { cn, formatNumber } from "@/lib/utils";
import type { CaseOverview } from "@/types/api";

const TILES: Array<{ key: keyof CaseOverview; label: string; dot: string }> = [
  { key: "open", label: "Open", dot: "bg-info" },
  { key: "in_progress", label: "In progress", dot: "bg-accent" },
  { key: "waiting_department", label: "Waiting for department", dot: "bg-warning" },
  { key: "resolved", label: "Resolved", dot: "bg-success" },
];

export function CaseOverviewCard() {
  const resource = useCaseOverview();

  return (
    <Card>
      <CardHeader
        title="Case overview"
        description="Where customer problems stand right now."
        action={
          <Link href="/cases" className="text-sm font-medium text-accent-strong hover:underline">
            View cases
          </Link>
        }
      />
      <CardBody>
        <ResourceView
          resource={resource}
          skeleton={
            <div className="grid grid-cols-2 gap-3">
              {TILES.map((tile) => (
                <Skeleton key={tile.key} className="h-20" />
              ))}
            </div>
          }
        >
          {(data) => (
            <dl className="grid grid-cols-2 gap-3">
              {TILES.map((tile) => (
                <div key={tile.key} className="rounded-lg border border-border bg-surface-muted/50 p-4">
                  <dt className="flex items-center gap-2 text-sm text-muted">
                    <span aria-hidden="true" className={cn("size-2 rounded-full", tile.dot)} />
                    {tile.label}
                  </dt>
                  <dd className="mt-1.5 text-2xl font-semibold tracking-tight text-ink">{formatNumber(data[tile.key])}</dd>
                </div>
              ))}
            </dl>
          )}
        </ResourceView>
      </CardBody>
    </Card>
  );
}
