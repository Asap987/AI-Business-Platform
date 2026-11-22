"use client";

import { Plus } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Button } from "@/components/ui/Button";
import { Card, CardHeader } from "@/components/ui/Card";
import { FormError } from "@/components/ui/ErrorMessage";
import { Input, SearchInput } from "@/components/ui/Input";
import { ConfirmDialog, Modal } from "@/components/ui/Modal";
import { Select, Textarea } from "@/components/ui/Select";
import { errorText } from "@/features/org/shared";
import { api, ApiError } from "@/lib/api";
import { humanize } from "@/lib/utils";
import type { EvidenceKind, LaunchArea, Milestone, ProjectData, ProjectTask, TaskPriority, TaskStatus } from "@/types/project";
import { EVIDENCE_LABEL, LAUNCH_LABEL, PRIORITIES, PriorityPill, STATUS_LABEL, STATUS_ORDER, StatusPill, shortDate } from "./shared";

interface Draft {
  module: string; title: string; description: string; status: TaskStatus; priority: TaskPriority; weight: string;
  start_date: string; deadline: string; blocker: string; notes: string; depends_on: string[];
  evidence_kind: "" | EvidenceKind; evidence: string; is_launch: boolean; launch_area: "" | LaunchArea;
}

function toDraft(t: ProjectTask | null, module: string, status: TaskStatus): Draft {
  return {
    module: t?.module ?? module, title: t?.title ?? "", description: t?.description ?? "", status, priority: t?.priority ?? "medium",
    weight: String(t?.weight ?? 1), start_date: t?.start_date ?? "", deadline: t?.deadline ?? "", blocker: t?.blocker ?? "", notes: t?.notes ?? "",
    depends_on: t?.depends_on.map((d) => d.id) ?? [], evidence_kind: t?.evidence_kind ?? "", evidence: t?.evidence ?? "", is_launch: t?.is_launch ?? false, launch_area: t?.launch_area ?? "",
  };
}

function TaskForm({ data, task, initial, onDone, onCancel }: { data: ProjectData; task: ProjectTask | null; initial: Draft; onDone: () => void; onCancel: () => void }) {
  const [d, setD] = useState<Draft>(initial);
  const [pick, setPick] = useState("");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const set = <K extends keyof Draft>(k: K, v: Draft[K]) => setD((p) => ({ ...p, [k]: v }));
  const titles = new Map(data.tasks.map((t) => [t.id, t.title]));

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setFormError(null);
    const weight = Number(d.weight);
    if (d.title.trim().length < 3) return setErrors({ title: "Give the task a title of at least 3 characters." });
    if (!Number.isInteger(weight) || weight < 1 || weight > 10) return setErrors({ weight: "Weight is a whole number from 1 to 10." });
    setErrors({});
    const body = {
      module: d.module, title: d.title.trim(), description: d.description, status: d.status, priority: d.priority, weight,
      start_date: d.start_date || null, deadline: d.deadline || null, blocker: d.blocker, notes: d.notes, depends_on: d.depends_on,
      evidence_kind: d.evidence_kind || null, evidence: d.evidence, is_launch: d.is_launch, launch_area: d.is_launch ? d.launch_area || null : null,
    };
    setSaving(true);
    try {
      if (task) await api.patch(`/platform/project/tasks/${task.id}`, body);
      else await api.post("/platform/project/tasks", body);
      onDone();
    } catch (error) {
      if (error instanceof ApiError && error.kind === "validation") setErrors(error.fieldErrors);
      setFormError(errorText(error));
    } finally {
      setSaving(false);
    }
  }

  return (
    <form onSubmit={submit} className="space-y-3" noValidate>
      <Input label="Title" value={d.title} onChange={(e) => set("title", e.target.value)} error={errors.title} maxLength={200} />
      <Textarea label="Description" rows={2} value={d.description} onChange={(e) => set("description", e.target.value)} />
      <div className="grid gap-3 sm:grid-cols-2">
        <Select label="Module" value={d.module} onChange={(e) => set("module", e.target.value)}>
          {data.modules.map((m) => <option key={m.key} value={m.key}>{m.name}</option>)}
        </Select>
        <Select label="Stage" value={d.status} onChange={(e) => set("status", e.target.value as TaskStatus)}>
          {STATUS_ORDER.map((s) => <option key={s} value={s}>{STATUS_LABEL[s]}</option>)}
        </Select>
        <Select label="Priority" value={d.priority} onChange={(e) => set("priority", e.target.value as TaskPriority)}>
          {PRIORITIES.map((p) => <option key={p} value={p}>{humanize(p)}</option>)}
        </Select>
        <Input label="Weight (1 to 10)" inputMode="numeric" value={d.weight} onChange={(e) => set("weight", e.target.value)} error={errors.weight} hint="How much of the project this task is worth." />
        <Input label="Start date" type="date" value={d.start_date} onChange={(e) => set("start_date", e.target.value)} />
        <Input label="Deadline" type="date" value={d.deadline} onChange={(e) => set("deadline", e.target.value)} />
      </div>
      <Textarea label="Blocker" rows={2} value={d.blocker} onChange={(e) => set("blocker", e.target.value)} hint={d.status === "blocked" ? "Required when the task is blocked." : "What is stopping it, if anything."} />
      <Textarea label="Technical notes" rows={2} value={d.notes} onChange={(e) => set("notes", e.target.value)} />
      <fieldset className="rounded-lg border border-border p-3">
        <legend className="px-1 text-sm font-medium text-ink">Evidence {d.status === "completed" ? "(required to complete)" : ""}</legend>
        <div className="grid gap-3 sm:grid-cols-2">
          <Select label="Kind" value={d.evidence_kind} onChange={(e) => set("evidence_kind", e.target.value as Draft["evidence_kind"])}>
            <option value="">None</option>
            {(Object.keys(EVIDENCE_LABEL) as EvidenceKind[]).map((k) => <option key={k} value={k}>{EVIDENCE_LABEL[k]}</option>)}
          </Select>
        </div>
        <div className="mt-3"><Textarea label="What was verified" rows={2} value={d.evidence} onChange={(e) => set("evidence", e.target.value)} hint="Name the merged commit, test file, integration run or written check that can be re-checked." /></div>
      </fieldset>
      <div>
        <p className="mb-1.5 text-sm font-medium text-ink">Depends on</p>
        <ul className="mb-2 flex flex-wrap gap-2">
          {d.depends_on.map((id) => (
            <li key={id} className="flex items-center gap-1 rounded-full bg-surface-muted px-2.5 py-1 text-xs text-ink">
              {titles.get(id) ?? "Unknown task"}
              <button type="button" aria-label={`Remove dependency ${titles.get(id) ?? ""}`} onClick={() => set("depends_on", d.depends_on.filter((x) => x !== id))} className="text-muted hover:text-ink">×</button>
            </li>
          ))}
        </ul>
        <Select label="Add a dependency" hideLabel value={pick} onChange={(e) => { if (e.target.value) set("depends_on", [...d.depends_on, e.target.value]); setPick(""); }}>
          <option value="">Add a dependency…</option>
          {data.tasks.filter((t) => t.id !== task?.id && !d.depends_on.includes(t.id)).map((t) => <option key={t.id} value={t.id}>{t.title}</option>)}
        </Select>
      </div>
      <label className="flex items-center gap-2 text-sm text-ink">
        <input type="checkbox" checked={d.is_launch} onChange={(e) => set("is_launch", e.target.checked)} /> Production launch requirement
      </label>
      {d.is_launch ? (
        <Select label="Launch area" value={d.launch_area} onChange={(e) => set("launch_area", e.target.value as Draft["launch_area"])}>
          <option value="">Choose…</option>
          {(Object.keys(LAUNCH_LABEL) as LaunchArea[]).map((k) => <option key={k} value={k}>{LAUNCH_LABEL[k]}</option>)}
        </Select>
      ) : null}
      {formError ? <FormError message={formError} /> : null}
      <div className="flex justify-end gap-2 pt-2">
        <Button variant="secondary" onClick={onCancel} disabled={saving}>Cancel</Button>
        <Button type="submit" loading={saving} loadingLabel="Saving">{task ? "Save task" : "Add task"}</Button>
      </div>
    </form>
  );
}

function MilestoneForm({ m, onDone, onCancel }: { m: Milestone | null; onDone: () => void; onCancel: () => void }) {
  const [f, setF] = useState({ name: m?.name ?? "", phase: m?.phase ?? "", description: m?.description ?? "", start_date: m?.start_date ?? "", target_date: m?.target_date ?? "", reached: Boolean(m?.reached_at) });
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (f.name.trim().length < 3 || !f.target_date) return setError("A milestone needs a name and a target date.");
    setSaving(true);
    setError(null);
    try {
      const body = { ...f, name: f.name.trim(), start_date: f.start_date || null };
      if (m) await api.patch(`/platform/project/milestones/${m.id}`, body);
      else await api.post("/platform/project/milestones", body);
      onDone();
    } catch (err) {
      setError(errorText(err));
    } finally {
      setSaving(false);
    }
  }
  return (
    <form onSubmit={submit} className="space-y-3" noValidate>
      {error ? <FormError message={error} /> : null}
      <Input label="Name" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} />
      <Input label="Phase" value={f.phase} onChange={(e) => setF({ ...f, phase: e.target.value })} />
      <Textarea label="Description" rows={2} value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} />
      <div className="grid gap-3 sm:grid-cols-2">
        <Input label="Start date" type="date" value={f.start_date} onChange={(e) => setF({ ...f, start_date: e.target.value })} />
        <Input label="Target date" type="date" value={f.target_date} onChange={(e) => setF({ ...f, target_date: e.target.value })} />
      </div>
      <label className="flex items-center gap-2 text-sm text-ink"><input type="checkbox" checked={f.reached} onChange={(e) => setF({ ...f, reached: e.target.checked })} /> Reached</label>
      <div className="flex justify-end gap-2 pt-2">
        <Button variant="secondary" onClick={onCancel} disabled={saving}>Cancel</Button>
        <Button type="submit" loading={saving} loadingLabel="Saving">{m ? "Save milestone" : "Add milestone"}</Button>
      </div>
    </form>
  );
}

export function TasksTab({ data, reload, initialModule }: { data: ProjectData; reload: () => void; initialModule: string }) {
  const [module, setModule] = useState(initialModule);
  const [status, setStatus] = useState("");
  const [q, setQ] = useState("");
  const [open, setOpen] = useState<string | null>(null);
  const [editing, setEditing] = useState<{ task: ProjectTask | null; status: TaskStatus } | null>(null);
  const [removing, setRemoving] = useState<ProjectTask | null>(null);
  const [msEdit, setMsEdit] = useState<{ m: Milestone | null } | null>(null);
  const [msRemove, setMsRemove] = useState<Milestone | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const names = new Map(data.modules.map((m) => [m.key, m.name]));
  const shown = data.tasks.filter((t) => (!module || t.module === module) && (!status || t.status === status) && (!q || t.title.toLowerCase().includes(q.toLowerCase())));

  async function remove(path: string, done: () => void) {
    setBusy(true);
    setErr(null);
    try {
      await api.delete(path);
      done();
      reload();
    } catch (e) {
      setErr(errorText(e));
      done();
    } finally {
      setBusy(false);
    }
  }
  const finished = () => { setEditing(null); setMsEdit(null); reload(); };

  return (
    <div className="space-y-6">
      {err ? <FormError message={err} /> : null}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
        <div className="sm:w-64"><SearchInput label="Search tasks" placeholder="Search tasks" value={q} onValueChange={setQ} /></div>
        <div className="sm:w-60"><Select label="Module" hideLabel value={module} onChange={(e) => setModule(e.target.value)}><option value="">All modules</option>{data.modules.map((m) => <option key={m.key} value={m.key}>{m.name}</option>)}</Select></div>
        <div className="sm:w-56"><Select label="Stage" hideLabel value={status} onChange={(e) => setStatus(e.target.value)}><option value="">All stages</option>{STATUS_ORDER.map((s) => <option key={s} value={s}>{STATUS_LABEL[s]}</option>)}</Select></div>
        <div className="sm:ml-auto"><Button onClick={() => setEditing({ task: null, status: "not_started" })}><Plus aria-hidden="true" className="size-4" />Add task</Button></div>
      </div>
      <Card>
        <ul>
          {shown.length === 0 ? <li className="p-5 text-sm text-muted">No tasks match.</li> : shown.map((t) => {
            const expanded = open === t.id;
            return (
              <li key={t.id} className="border-t border-border first:border-t-0">
                <button type="button" aria-expanded={expanded} onClick={() => setOpen(expanded ? null : t.id)} className="flex w-full flex-col gap-2 px-4 py-3 text-left hover:bg-surface-muted/40 sm:flex-row sm:items-center sm:justify-between">
                  <span className="min-w-0 text-sm text-ink">{t.title}<span className="block text-xs text-muted">{names.get(t.module)} · weight {t.weight}{t.deadline ? ` · due ${shortDate(t.deadline)}` : ""}{t.overdue ? " · overdue" : ""}</span></span>
                  <span className="flex shrink-0 flex-wrap gap-2"><PriorityPill priority={t.priority} /><StatusPill status={t.status} /></span>
                </button>
                {expanded ? (
                  <div className="space-y-2 bg-surface-muted/30 px-4 pb-4 pt-2 text-sm">
                    {t.description ? <p className="text-ink">{t.description}</p> : null}
                    {t.blocker ? <p><span className="font-medium text-ink">Blocker: </span><span className="text-danger">{t.blocker}</span></p> : null}
                    {t.evidence ? <p><span className="font-medium text-ink">Evidence ({t.evidence_kind ? EVIDENCE_LABEL[t.evidence_kind] : "unspecified"}): </span><span className="text-muted">{t.evidence}</span></p> : t.status === "completed" ? null : <p className="text-muted">No evidence recorded yet.</p>}
                    {t.notes ? <p><span className="font-medium text-ink">Notes: </span><span className="text-muted">{t.notes}</span></p> : null}
                    {t.depends_on.length ? <p><span className="font-medium text-ink">Depends on: </span><span className="text-muted">{t.depends_on.map((d) => `${d.title} (${STATUS_LABEL[d.status].toLowerCase()})`).join("; ")}</span></p> : null}
                    {t.is_launch ? <p className="text-muted">Launch requirement: {t.launch_area ? LAUNCH_LABEL[t.launch_area] : ""}</p> : null}
                    <div className="flex flex-wrap gap-2 pt-1">
                      <Button size="sm" variant="secondary" onClick={() => setEditing({ task: t, status: t.status })}>Edit</Button>
                      {t.status !== "completed" ? <Button size="sm" variant="accent" onClick={() => setEditing({ task: t, status: "completed" })}>Mark completed</Button> : null}
                      <Button size="sm" variant="ghost" onClick={() => setRemoving(t)}>Delete</Button>
                    </div>
                  </div>
                ) : null}
              </li>
            );
          })}
        </ul>
      </Card>

      <Card>
        <CardHeader title="Milestones" action={<Button size="sm" variant="secondary" onClick={() => setMsEdit({ m: null })}>Add milestone</Button>} />
        <ul className="pb-2">
          {data.milestones.map((m) => (
            <li key={m.id} className="flex flex-col gap-2 border-t border-border px-5 py-3 text-sm sm:flex-row sm:items-center sm:justify-between">
              <span className="text-ink">{m.name}<span className="block text-xs text-muted">{m.phase} · target {shortDate(m.target_date)}{m.reached_at ? " · reached" : m.overdue ? " · overdue" : ""}</span></span>
              <span className="flex gap-2"><Button size="sm" variant="secondary" onClick={() => setMsEdit({ m })}>Edit</Button><Button size="sm" variant="ghost" onClick={() => setMsRemove(m)}>Delete</Button></span>
            </li>
          ))}
        </ul>
      </Card>

      <Modal open={editing !== null} onClose={() => setEditing(null)} title={editing?.task ? "Edit task" : "Add task"} size="lg">
        {editing ? <TaskForm key={editing.task?.id ?? "new"} data={data} task={editing.task} initial={toDraft(editing.task, module || "core", editing.status)} onDone={finished} onCancel={() => setEditing(null)} /> : null}
      </Modal>
      <Modal open={msEdit !== null} onClose={() => setMsEdit(null)} title={msEdit?.m ? "Edit milestone" : "Add milestone"}>
        {msEdit ? <MilestoneForm key={msEdit.m?.id ?? "new"} m={msEdit.m} onDone={finished} onCancel={() => setMsEdit(null)} /> : null}
      </Modal>
      <ConfirmDialog open={removing !== null} destructive loading={busy} title="Delete this task?" description={removing ? `“${removing.title}” will be removed from the tracker. Tasks that depend on it block the deletion.` : ""} confirmLabel="Delete task" onCancel={() => setRemoving(null)} onConfirm={() => removing && remove(`/platform/project/tasks/${removing.id}`, () => setRemoving(null))} />
      <ConfirmDialog open={msRemove !== null} destructive loading={busy} title="Delete this milestone?" description={msRemove ? `“${msRemove.name}” will be removed.` : ""} confirmLabel="Delete milestone" onCancel={() => setMsRemove(null)} onConfirm={() => msRemove && remove(`/platform/project/milestones/${msRemove.id}`, () => setMsRemove(null))} />
    </div>
  );
}
