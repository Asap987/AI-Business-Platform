"use client";

import { Card, CardHeader } from "@/components/ui/Card";
import { formatRelativeTime } from "@/lib/utils";
import type { ProjectData } from "@/types/project";
import { Stat } from "./shared";

export function TestsTab({ data }: { data: ProjectData }) {
  const { latest, history, coverage_note } = data.tests;
  if (!latest) {
    return <Card className="p-5 text-sm text-muted">No test run has been recorded. From <code>backend/</code> run <code>python scripts/record_test_run.py</code>; nothing here is guessed.</Card>;
  }
  const max = Math.max(...history.map((h) => h.total), 1);
  return (
    <div className="space-y-6">
      {latest.stale ? (
        <p role="alert" className="rounded-lg bg-warning-soft p-3 text-sm text-warning">
          Not current: this run is {Math.round(latest.age_hours)} hours old{latest.matches_head === false ? " and was made for a different commit than the code now checked out" : ""}. Do not read it as the result of the latest code.
        </p>
      ) : null}
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-5">
        <Stat label="Total" value={String(latest.total)} />
        <Stat label="Passing" value={String(latest.passed)} tone="text-success" />
        <Stat label="Failed" value={String(latest.failed)} tone={latest.failed ? "text-danger" : undefined} />
        <Stat label="Skipped" value={String(latest.skipped)} />
        <Stat label="Coverage" value={latest.coverage_pct === null ? "Not measured" : `${latest.coverage_pct}%`} note={coverage_note ?? undefined} />
      </div>
      <p className="text-sm text-muted">Latest execution: {formatRelativeTime(latest.ran_at)} · commit {latest.commit} · source {latest.source}{latest.duration_s ? ` · ${latest.duration_s}s` : ""}</p>
      {latest.failures.length > 0 ? (
        <Card><CardHeader title="Failing tests" /><ul className="px-5 pb-5 font-mono text-xs text-danger">{latest.failures.map((f) => <li key={f}>{f}</li>)}</ul></Card>
      ) : null}
      <Card>
        <CardHeader title="History" description="Each bar is one recorded run: green passed, red failed, grey skipped." />
        <div className="flex h-32 items-end gap-1 overflow-x-auto px-5 pb-5" role="img" aria-label={`Test history, ${history.length} runs`}>
          {history.map((h) => (
            <div key={`${h.ran_at}`} className="flex w-4 shrink-0 flex-col-reverse overflow-hidden rounded-sm" style={{ height: `${(h.total / max) * 100}%` }} title={`${h.passed} passed, ${h.failed} failed, ${h.skipped} skipped (${h.commit})`}>
              <div className="bg-success" style={{ height: `${(h.passed / h.total) * 100}%` }} />
              <div className="bg-danger" style={{ height: `${(h.failed / h.total) * 100}%` }} />
              <div className="bg-border-strong" style={{ height: `${(h.skipped / h.total) * 100}%` }} />
            </div>
          ))}
        </div>
      </Card>
      <Card>
        <CardHeader title="By module" />
        <ul className="px-5 pb-5 text-sm">
          {data.modules.map((m) => (
            <li key={m.key} className="flex justify-between gap-3 border-t border-border py-2 first:border-t-0">
              <span className="text-ink">{m.name}</span>
              <span className={m.thin_test_coverage ? "text-warning" : "text-muted"}>{m.tests ? `${m.tests.passed} passed${m.tests.failed ? `, ${m.tests.failed} failed` : ""}` : m.thin_test_coverage ? "No automated tests" : "—"}</span>
            </li>
          ))}
        </ul>
      </Card>
    </div>
  );
}
