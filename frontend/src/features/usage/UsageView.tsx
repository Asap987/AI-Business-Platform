"use client";

import { useState } from "react";
import { PageHeader } from "@/components/layout/PageHeader";
import { Card } from "@/components/ui/Card";
import { Skeleton } from "@/components/ui/LoadingSpinner";
import { Pagination } from "@/components/ui/Pagination";
import { ResourceView } from "@/components/ui/ResourceView";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/Table";
import { pageCount } from "@/features/org/shared";
import { useApiResource } from "@/hooks/useApiResource";
import { formatNumber, formatRelativeTime } from "@/lib/utils";
import type { Paginated } from "@/types/api";
import type { UsageCall, UsageSummary } from "@/types/org";

const PAGE_SIZE = 10;

function money(usd: string, complete: boolean): string {
  const n = Number(usd);
  const text = `$${n < 1 ? n.toFixed(4) : n.toFixed(2)}`;
  return complete ? `${text} (estimate)` : `${text}+ (estimate, some prices missing)`;
}

function Stat({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <Card className="p-4">
      <p className="text-xs text-muted">{label}</p>
      <p className="mt-1 text-xl font-semibold text-ink">{value}</p>
      {note ? <p className="mt-1 text-xs text-muted">{note}</p> : null}
    </Card>
  );
}

export function UsageView() {
  const summary = useApiResource<UsageSummary>("/usage/summary");
  const [page, setPage] = useState(1);
  const calls = useApiResource<Paginated<UsageCall>>("/usage/calls", { page, page_size: PAGE_SIZE });

  return (
    <>
      <PageHeader title="Usage & costs" description="What your AI calls used in the last 30 days. Costs are estimates from current provider price lists, not invoices." />
      <ResourceView resource={summary} compact={false} skeleton={<Skeleton className="h-40" />}>
        {(s) => (
          <>
            <div className="mb-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
              <Stat label="Estimated cost" value={money(s.total.estimated_cost_usd, s.total.cost_complete)} note={s.total.cost_complete ? undefined : `${s.total.calls_missing_prices} call(s) used something with no price set`} />
              <Stat label="Calls" value={formatNumber(s.total.calls)} />
              <Stat label="Average reply time" value={s.total.latency_avg_ms === null ? "—" : `${(s.total.latency_avg_ms / 1000).toFixed(1)} s`} note="Customer finishes speaking to first sound" />
              <Stat label="Failed requests / retries" value={`${s.total.failed_requests} / ${s.total.retries}`} />
            </div>
            <Card className="mb-6 overflow-hidden">
              <Table caption="Usage by day">
                <TableHead>
                  <TableRow>
                    <TableHeader>Day</TableHeader>
                    <TableHeader>Calls</TableHeader>
                    <TableHeader>Speech in (min)</TableHeader>
                    <TableHeader>Speech out (characters)</TableHeader>
                    <TableHeader>Estimated cost</TableHeader>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {s.by_day.length === 0 ? (
                    <TableRow><TableCell colSpan={5} className="text-muted">No calls in this period.</TableCell></TableRow>
                  ) : (
                    s.by_day.map((d) => (
                      <TableRow key={d.date}>
                        <TableCell>{d.date}</TableCell>
                        <TableCell>{d.calls}</TableCell>
                        <TableCell>{(d.stt_seconds / 60).toFixed(1)}</TableCell>
                        <TableCell>{formatNumber(d.tts_characters)}</TableCell>
                        <TableCell>{money(d.estimated_cost_usd, d.cost_complete)}</TableCell>
                      </TableRow>
                    ))
                  )}
                </TableBody>
              </Table>
            </Card>
            {s.by_model.length > 0 ? (
              <Card className="mb-6 overflow-hidden">
                <Table caption="AI model usage">
                  <TableHead>
                    <TableRow><TableHeader>Model</TableHeader><TableHeader>Requests</TableHeader><TableHeader>Input tokens</TableHeader><TableHeader>Output tokens</TableHeader></TableRow>
                  </TableHead>
                  <TableBody>
                    {s.by_model.map((m) => (
                      <TableRow key={m.model}><TableCell>{m.model}</TableCell><TableCell>{m.calls}</TableCell><TableCell>{formatNumber(m.input_tokens)}</TableCell><TableCell>{formatNumber(m.output_tokens)}</TableCell></TableRow>
                    ))}
                  </TableBody>
                </Table>
              </Card>
            ) : null}
          </>
        )}
      </ResourceView>
      <h2 className="mb-3 text-base font-semibold text-ink">Recent calls</h2>
      <Card className="overflow-hidden">
        <ResourceView resource={calls} compact skeleton={<Skeleton className="h-32" />}>
          {(data) => (
            <>
              <Table caption="Recent calls">
                <TableHead>
                  <TableRow><TableHeader>Ended</TableHeader><TableHeader>Type</TableHeader><TableHeader>Replies</TableHeader><TableHeader>Failed</TableHeader><TableHeader>Estimated cost</TableHeader></TableRow>
                </TableHead>
                <TableBody>
                  {data.items.length === 0 ? (
                    <TableRow><TableCell colSpan={5} className="text-muted">No calls recorded yet.</TableCell></TableRow>
                  ) : (
                    data.items.map((c) => (
                      <TableRow key={c.id}>
                        <TableCell>{formatRelativeTime(c.ended_at)}</TableCell>
                        <TableCell>{c.source === "test_call" ? "Test call" : c.source}</TableCell>
                        <TableCell>{c.turns}</TableCell>
                        <TableCell>{c.failed_requests}</TableCell>
                        <TableCell>{money(c.estimated_cost_usd, c.cost_complete)}</TableCell>
                      </TableRow>
                    ))
                  )}
                </TableBody>
              </Table>
              <div className="border-t border-border px-4">
                <Pagination page={page} pageCount={pageCount(data.total, PAGE_SIZE)} onPageChange={setPage} totalItems={data.total} />
              </div>
            </>
          )}
        </ResourceView>
      </Card>
    </>
  );
}
