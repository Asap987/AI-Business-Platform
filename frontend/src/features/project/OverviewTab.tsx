"use client";

import { Card, CardHeader } from "@/components/ui/Card";
import { formatRelativeTime } from "@/lib/utils";
import type { ProjectData, TaskStatus } from "@/types/project";
import { ProgressBar, STATUS_BAR, STATUS_LABEL, STATUS_ORDER, Stat, StatusPill, shortDate } from "./shared";

export function OverviewTab({ data, goto }: { data: ProjectData; goto: (tab: string) => void }) {
  const o = data.overall;
  const run = data.tests.latest;
  const upcoming = data.milestones.filter((m) => !m.reached_at).slice(0, 4);
  const attention = data.tasks.filter((t) => t.status === "blocked" || t.overdue);
  return (
    <div className="space-y-6">
      <Card className="p-5">
        <div className="flex flex-wrap items-end justify-between gap-2">
          <div>
            <p className="text-xs text-muted">Overall completion (weight of completed tasks ÷ weight of all tasks)</p>
            <p className="text-4xl font-semibold text-ink">{o.percent}%</p>
          </div>
          <p className="text-sm text-muted">{o.weight_done} of {o.weight_total} weight · {o.tasks} tasks</p>
        </div>
        <div className="mt-3"><ProgressBar percent={o.percent} label="Overall completion" tone="bg-success" /></div>
        <div className="mt-3 flex h-2 overflow-hidden rounded-full bg-surface-muted" aria-hidden="true">
          {STATUS_ORDER.map((s) => (o.counts[s] ? <div key={s} className={STATUS_BAR[s]} style={{ width: `${(100 * o.counts[s]) / o.tasks}%` }} /> : null))}
        </div>
        <ul className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted">
          {STATUS_ORDER.map((s: TaskStatus) => (
            <li key={s} className="flex items-center gap-1.5"><span className={`size-2 rounded-full ${STATUS_BAR[s]}`} aria-hidden="true" />{STATUS_LABEL[s]}: {o.counts[s]}</li>
          ))}
        </ul>
      </Card>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Stat label="Completed" value={String(o.counts.completed)} />
        <Stat label="In progress / testing" value={String(o.counts.in_progress + o.counts.testing)} />
        <Stat label="Pending (not started)" value={String(o.counts.not_started)} />
        <Stat label="Blocked" value={String(o.counts.blocked)} tone={o.counts.blocked ? "text-danger" : undefined} note={`Waiting on others: ${o.counts.awaiting_external + o.counts.awaiting_approval}`} />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader title="Tests" description={run ? `Run ${formatRelativeTime(run.ran_at)} on commit ${run.commit}` : undefined} />
          <div className="px-5 pb-5 text-sm">
            {run ? (
              <>
                <p className="text-ink"><strong>{run.passed}</strong> passed · <strong className={run.failed ? "text-danger" : ""}>{run.failed}</strong> failed · {run.skipped} skipped (of {run.total})</p>
                {run.stale ? <p className="mt-2 rounded-lg bg-warning-soft p-2 text-warning">This result is {run.matches_head === false ? "for a different commit than the code now checked out" : `${Math.round(run.age_hours)} hours old`}. Run the tests again to refresh it.</p> : null}
              </>
            ) : <p className="text-muted">No test run has been recorded yet.</p>}
            <button type="button" onClick={() => goto("tests")} className="mt-3 text-accent-strong underline">Open the testing view</button>
          </div>
        </Card>
        <Card>
          <CardHeader title="Needs attention" />
          <ul className="px-5 pb-5 text-sm">
            {attention.length === 0 ? <li className="text-muted">Nothing is blocked or overdue.</li> : attention.slice(0, 6).map((t) => (
              <li key={t.id} className="flex items-start justify-between gap-3 border-t border-border py-2 first:border-t-0">
                <span className="text-ink">{t.title}<span className="block text-xs text-muted">{t.blocker || (t.overdue ? `Overdue since ${shortDate(t.deadline)}` : "")}</span></span>
                <StatusPill status={t.status} />
              </li>
            ))}
          </ul>
        </Card>
        <Card>
          <CardHeader title="Upcoming milestones" description="Dates are proposed targets, not promises." />
          <ul className="px-5 pb-5 text-sm">
            {upcoming.length === 0 ? <li className="text-muted">No upcoming milestones.</li> : upcoming.map((m) => (
              <li key={m.id} className="flex items-start justify-between gap-3 border-t border-border py-2 first:border-t-0">
                <span className="text-ink">{m.name}<span className="block text-xs text-muted">{m.phase}</span></span>
                <span className={m.overdue ? "text-danger" : "text-muted"}>{shortDate(m.target_date)}</span>
              </li>
            ))}
          </ul>
        </Card>
        <Card>
          <CardHeader title="Latest development activity" description={data.git_head ? `Checked-out commit ${data.git_head}` : "Git history is not available to the server"} />
          <ul className="px-5 pb-5 text-sm">
            {data.git_log.length === 0 ? <li className="text-muted">No commits to show.</li> : data.git_log.slice(0, 5).map((c) => (
              <li key={c.commit} className="border-t border-border py-2 first:border-t-0"><span className="font-mono text-xs text-muted">{c.commit}</span> <span className="text-ink">{c.subject}</span><span className="block text-xs text-muted">{formatRelativeTime(c.date)}</span></li>
            ))}
          </ul>
        </Card>
      </div>
    </div>
  );
}

export function ModulesTab({ data, openModule }: { data: ProjectData; openModule: (key: string) => void }) {
  return (
    <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
      {data.modules.map((m) => (
        <Card key={m.key} className="p-5">
          <div className="flex items-start justify-between gap-2">
            <h3 className="text-sm font-semibold text-ink">{m.name}</h3>
            <span className="text-lg font-semibold text-ink">{m.percent}%</span>
          </div>
          <div className="mt-2"><ProgressBar percent={m.percent} label={`${m.name} completion`} tone="bg-success" /></div>
          <p className="mt-2 text-xs text-muted">{m.status} · {m.counts.completed} done · {m.remaining} remaining</p>
          {m.tests ? <p className="mt-1 text-xs text-muted">Tests: {m.tests.passed} passed{m.tests.failed ? `, ${m.tests.failed} failed` : ""}</p> : m.thin_test_coverage ? <p className="mt-1 text-xs text-warning">No automated tests recorded for this module.</p> : null}
          <dl className="mt-3 space-y-2 text-xs">
            <div><dt className="font-medium text-ink">Next action</dt><dd className="text-muted">{m.next_action ?? "Nothing ready to start"}</dd></div>
            <div><dt className="font-medium text-ink">Depends on</dt><dd className="text-muted">{m.depends_on_modules.length ? m.depends_on_modules.join(", ") : "No other module"}</dd></div>
            <div><dt className="font-medium text-ink">Known issues</dt><dd className="text-muted">{m.known_issues.length ? <ul className="list-disc pl-4">{m.known_issues.slice(0, 3).map((i) => <li key={i}>{i}</li>)}</ul> : "None recorded"}</dd></div>
            <div><dt className="font-medium text-ink">Last updated</dt><dd className="text-muted">{m.last_updated ? shortDate(m.last_updated) : "—"}</dd></div>
          </dl>
          <button type="button" onClick={() => openModule(m.key)} className="mt-3 text-sm text-accent-strong underline">See its {m.tasks} tasks</button>
        </Card>
      ))}
    </div>
  );
}
