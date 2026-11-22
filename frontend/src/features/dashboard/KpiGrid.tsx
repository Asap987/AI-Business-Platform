"use client";

import {
  Gauge,
  Inbox,
  LifeBuoy,
  MessageSquareText,
  PhoneCall,
  Timer,
  TrendingDown,
  TrendingUp,
  type LucideIcon,
} from "lucide-react";
import { useDashboardKpis } from "@/features/dashboard/api";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Skeleton } from "@/components/ui/LoadingSpinner";
import type { DashboardKpis, KpiMetric, Trend } from "@/types/api";
import { cn, formatDuration, formatNumber } from "@/lib/utils";

interface KpiDefinition {
  key: keyof DashboardKpis;
  label: string;
  icon: LucideIcon;
  format: (value: number) => string;
  /** False for metrics where a rise is bad (e.g. response time). */
  higherIsBetter: boolean;
}

const KPIS: KpiDefinition[] = [
  { key: "total_calls", label: "Total Calls", icon: PhoneCall, format: formatNumber, higherIsBetter: true },
  { key: "total_sms_conversations", label: "SMS Conversations", icon: MessageSquareText, format: formatNumber, higherIsBetter: true },
  { key: "active_cases", label: "Active Cases", icon: LifeBuoy, format: formatNumber, higherIsBetter: false },
  { key: "pending_department_requests", label: "Pending Department Requests", icon: Inbox, format: formatNumber, higherIsBetter: false },
  { key: "ai_resolution_rate", label: "AI Resolution Rate", icon: Gauge, format: (v) => `${Math.round(v * 10) / 10}%`, higherIsBetter: true },
  { key: "average_response_seconds", label: "Average Response Time", icon: Timer, format: formatDuration, higherIsBetter: false },
];

type CardState = "loading" | "unavailable" | "empty" | "value";

function TrendIndicator({ trend, higherIsBetter }: { trend: Trend; higherIsBetter: boolean }) {
  const up = trend.change_pct > 0;
  const flat = trend.change_pct === 0;
  const good = flat ? null : up === higherIsBetter;
  const Icon = up ? TrendingUp : TrendingDown;
  const pct = `${up ? "+" : ""}${Math.round(trend.change_pct * 10) / 10}%`;

  return (
    <p className="mt-2 flex items-center gap-1.5 text-xs text-muted">
      {flat ? null : (
        <Icon aria-hidden="true" className={cn("size-3.5", good ? "text-success" : "text-danger")} />
      )}
      <span className={cn("font-medium", flat ? "text-muted" : good ? "text-success" : "text-danger")}>{pct}</span>
      <span>{trend.period_label}</span>
    </p>
  );
}

function KpiCard({
  definition,
  state,
  metric,
}: {
  definition: KpiDefinition;
  state: CardState;
  metric?: KpiMetric;
}) {
  const Icon = definition.icon;

  return (
    <Card className="p-5">
      <div className="flex items-start justify-between gap-3">
        <p className="text-sm font-medium text-muted">{definition.label}</p>
        <span aria-hidden="true" className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-accent-soft text-accent-strong">
          <Icon className="size-[18px]" />
        </span>
      </div>

      <div className="mt-3 min-h-9">
        {state === "loading" ? (
          <Skeleton className="h-8 w-24" />
        ) : state === "value" && metric?.value != null ? (
          <p className="text-3xl font-semibold tracking-tight text-ink">{definition.format(metric.value)}</p>
        ) : state === "empty" ? (
          <p className="text-sm text-muted">No data yet</p>
        ) : (
          <p className="text-sm text-muted">Unavailable</p>
        )}
      </div>

      {state === "value" && metric?.trend ? (
        <TrendIndicator trend={metric.trend} higherIsBetter={definition.higherIsBetter} />
      ) : null}
    </Card>
  );
}

export function KpiGrid() {
  const kpis = useDashboardKpis();
  const failed = kpis.status === "error";

  return (
    <section aria-labelledby="kpi-heading" className="mb-6">
      <h2 id="kpi-heading" className="sr-only">
        Key metrics
      </h2>
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {KPIS.map((definition) => {
          const metric = kpis.data?.[definition.key];
          const state: CardState =
            kpis.status === "loading" ? "loading" : failed ? "unavailable" : metric?.value == null ? "empty" : "value";
          return <KpiCard key={definition.key} definition={definition} state={state} metric={metric} />;
        })}
      </div>

      {failed && kpis.error ? (
        <div role="alert" className="mt-3 flex flex-wrap items-center justify-between gap-3 rounded-lg border border-border bg-surface px-4 py-3 text-sm">
          <p className="text-muted">
            {kpis.error.kind === "not_found"
              ? "Metrics aren't available yet because the backend doesn't provide them."
              : kpis.error.kind === "forbidden"
                ? "You don't have permission to view these metrics."
                : kpis.error.message}
          </p>
          {kpis.error.kind === "forbidden" ? null : (
            <Button variant="secondary" size="sm" onClick={kpis.reload}>
              Try again
            </Button>
          )}
        </div>
      ) : null}
    </section>
  );
}
