"use client";

import { useState, type FormEvent } from "react";
import { Check, Circle } from "lucide-react";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardHeader } from "@/components/ui/Card";
import { FormError } from "@/components/ui/ErrorMessage";
import { Input } from "@/components/ui/Input";
import { ConfirmDialog, Modal } from "@/components/ui/Modal";
import { Select, Textarea } from "@/components/ui/Select";
import { errorText } from "@/features/org/shared";
import { api } from "@/lib/api";
import { humanize } from "@/lib/utils";
import type { ExternalCategory, ExternalItem, FinanceCategory, FinanceKind, ProjectData } from "@/types/project";
import { EXTERNAL_LABEL, EXTERNAL_TONE, LAUNCH_LABEL, Stat, usd } from "./shared";

const CATEGORIES = Object.keys(EXTERNAL_LABEL) as ExternalCategory[];

function ExternalForm({ item, onDone, onCancel }: { item: ExternalItem | null; onDone: () => void; onCancel: () => void }) {
  const [f, setF] = useState({ name: item?.name ?? "", category: (item?.category ?? "awaiting_us") as ExternalCategory, owner: item?.owner ?? "", detail: item?.detail ?? "" });
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (f.name.trim().length < 3) return setError("Give it a name of at least 3 characters.");
    setSaving(true);
    setError(null);
    try {
      if (item) await api.patch(`/platform/project/external/${item.id}`, { ...f, name: f.name.trim() });
      else await api.post("/platform/project/external", { ...f, name: f.name.trim() });
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
      <Input label="What is needed" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} />
      <Select label="Status" value={f.category} onChange={(e) => setF({ ...f, category: e.target.value as ExternalCategory })}>
        {CATEGORIES.map((c) => <option key={c} value={c}>{EXTERNAL_LABEL[c]}</option>)}
      </Select>
      <Input label="Owner" value={f.owner} onChange={(e) => setF({ ...f, owner: e.target.value })} />
      <Textarea label="Detail" rows={2} value={f.detail} onChange={(e) => setF({ ...f, detail: e.target.value })} />
      <div className="flex justify-end gap-2 pt-2">
        <Button variant="secondary" onClick={onCancel} disabled={saving}>Cancel</Button>
        <Button type="submit" loading={saving} loadingLabel="Saving">{item ? "Save" : "Add"}</Button>
      </div>
    </form>
  );
}

export function ExternalTab({ data, reload }: { data: ProjectData; reload: () => void }) {
  const [edit, setEdit] = useState<{ item: ExternalItem | null } | null>(null);
  const [remove, setRemove] = useState<ExternalItem | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  async function doRemove() {
    if (!remove) return;
    setBusy(true);
    try {
      await api.delete(`/platform/project/external/${remove.id}`);
      reload();
    } catch (e) {
      setErr(errorText(e));
    } finally {
      setBusy(false);
      setRemove(null);
    }
  }
  return (
    <div className="space-y-6">
      {err ? <FormError message={err} /> : null}
      <div className="flex justify-end"><Button onClick={() => setEdit({ item: null })}>Add item</Button></div>
      <div className="grid gap-4 lg:grid-cols-2">
        {CATEGORIES.map((c) => {
          const items = data.external.filter((x) => x.category === c);
          return (
            <Card key={c}>
              <CardHeader title={EXTERNAL_LABEL[c]} action={<Badge tone={EXTERNAL_TONE[c]}>{items.length}</Badge>} />
              <ul className="pb-2">
                {items.length === 0 ? <li className="px-5 pb-3 text-sm text-muted">Nothing here.</li> : items.map((x) => (
                  <li key={x.id} className="border-t border-border px-5 py-3 text-sm">
                    <p className="text-ink">{x.name}</p>
                    <p className="text-xs text-muted">{x.owner ? `${x.owner}${x.detail ? " · " : ""}` : ""}{x.detail}</p>
                    <div className="mt-2 flex gap-2"><Button size="sm" variant="secondary" onClick={() => setEdit({ item: x })}>Edit</Button><Button size="sm" variant="ghost" onClick={() => setRemove(x)}>Delete</Button></div>
                  </li>
                ))}
              </ul>
            </Card>
          );
        })}
      </div>
      <Modal open={edit !== null} onClose={() => setEdit(null)} title={edit?.item ? "Edit item" : "Add item"}>
        {edit ? <ExternalForm key={edit.item?.id ?? "new"} item={edit.item} onDone={() => { setEdit(null); reload(); }} onCancel={() => setEdit(null)} /> : null}
      </Modal>
      <ConfirmDialog open={remove !== null} destructive loading={busy} title="Delete this item?" description={remove ? `“${remove.name}” will be removed.` : ""} confirmLabel="Delete" onCancel={() => setRemove(null)} onConfirm={doRemove} />
    </div>
  );
}

function FinanceForm({ onDone, onCancel }: { onDone: () => void; onCancel: () => void }) {
  const [f, setF] = useState({ label: "", category: "api" as FinanceCategory, kind: "estimate" as FinanceKind, amount_usd: "", period: "", state: "" as "" | "outstanding" | "settled", note: "" });
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (f.label.trim().length < 3) return setError("Give it a label of at least 3 characters.");
    if (!/^\d+(\.\d{1,6})?$/.test(f.amount_usd.trim())) return setError("Enter the amount in US dollars as a plain number, such as 12.50.");
    if (f.kind === "commitment" && !f.state) return setError("Say whether the commitment is outstanding or settled.");
    setSaving(true);
    setError(null);
    try {
      await api.post("/platform/project/finance", { ...f, label: f.label.trim(), amount_usd: f.amount_usd.trim(), state: f.kind === "commitment" ? f.state : "" });
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
      <Input label="Label" value={f.label} onChange={(e) => setF({ ...f, label: e.target.value })} />
      <div className="grid gap-3 sm:grid-cols-2">
        <Select label="Kind" value={f.kind} onChange={(e) => setF({ ...f, kind: e.target.value as FinanceKind })} hint="Only “actual” means a real charge was recorded.">
          <option value="estimate">Estimate</option><option value="actual">Actual recorded charge</option><option value="commitment">Financial commitment</option>
        </Select>
        <Select label="Category" value={f.category} onChange={(e) => setF({ ...f, category: e.target.value as FinanceCategory })}>
          {["api", "telephony", "email", "hosting", "other"].map((c) => <option key={c} value={c}>{humanize(c)}</option>)}
        </Select>
        <Input label="Amount (USD)" inputMode="decimal" value={f.amount_usd} onChange={(e) => setF({ ...f, amount_usd: e.target.value })} />
        <Input label="Period" value={f.period} onChange={(e) => setF({ ...f, period: e.target.value })} placeholder="per month, one run…" />
      </div>
      {f.kind === "commitment" ? <Select label="State" value={f.state} onChange={(e) => setF({ ...f, state: e.target.value as typeof f.state })}><option value="">Choose…</option><option value="outstanding">Outstanding</option><option value="settled">Settled</option></Select> : null}
      <Textarea label="Note" rows={2} value={f.note} onChange={(e) => setF({ ...f, note: e.target.value })} />
      <div className="flex justify-end gap-2 pt-2"><Button variant="secondary" onClick={onCancel} disabled={saving}>Cancel</Button><Button type="submit" loading={saving} loadingLabel="Saving">Add</Button></div>
    </form>
  );
}

const KIND_LABEL: Record<FinanceKind, string> = { estimate: "Estimate", actual: "Actual charge", commitment: "Commitment" };

export function FinanceTab({ data, reload }: { data: ProjectData; reload: () => void }) {
  const [adding, setAdding] = useState(false);
  const [remove, setRemove] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const f = data.finance;
  const done = async () => {
    if (!remove) return;
    try {
      await api.delete(`/platform/project/finance/${remove}`);
      reload();
    } catch (e) {
      setErr(errorText(e));
    } finally {
      setRemove(null);
    }
  };
  return (
    <div className="space-y-6">
      {err ? <FormError message={err} /> : null}
      <p className="rounded-lg bg-surface-muted p-3 text-sm text-muted">{f.note}</p>
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Stat label="Estimated costs entered" value={usd(f.totals.estimate)} note="Estimates, not charges" />
        <Stat label="Actual recorded charges" value={usd(f.totals.actual)} note="Only what has been entered as actual" />
        <Stat label="Outstanding commitments" value={usd(f.totals.commitment)} />
        <Stat label="API usage this month" value={`${usd(f.api_usage_this_month.estimated_cost_usd)}${f.api_usage_this_month.complete ? "" : "+"} (estimate)`} note={f.api_usage_this_month.complete ? f.api_usage_this_month.basis : "Some prices are missing, so this is a lower bound"} />
      </div>
      <Card>
        <CardHeader title="Costs and commitments" action={<Button size="sm" onClick={() => setAdding(true)}>Add entry</Button>} />
        <ul className="pb-2">
          {f.rows.length === 0 ? <li className="px-5 pb-3 text-sm text-muted">No entries. Telephony and email spending is zero until one is entered.</li> : f.rows.map((r) => (
            <li key={r.id} className="flex flex-col gap-2 border-t border-border px-5 py-3 text-sm sm:flex-row sm:items-center sm:justify-between">
              <span className="text-ink">{r.label}<span className="block text-xs text-muted">{humanize(r.category)} · {KIND_LABEL[r.kind]}{r.state ? ` (${r.state})` : ""}{r.period ? ` · ${r.period}` : ""}{r.note ? ` · ${r.note}` : ""}</span></span>
              <span className="flex items-center gap-3"><span className="font-medium text-ink">{usd(r.amount_usd)}</span><Button size="sm" variant="ghost" onClick={() => setRemove(r.id)}>Delete</Button></span>
            </li>
          ))}
        </ul>
      </Card>
      <Card>
        <CardHeader title="Launch readiness" description="An area is ready only when every tracked requirement in it is completed with evidence." />
        <ul className="pb-2">
          {data.launch.map((l) => (
            <li key={l.area} className="flex items-center justify-between gap-3 border-t border-border px-5 py-3 text-sm">
              <span className="flex items-center gap-2 text-ink">{l.ready ? <Check aria-hidden="true" className="size-4 text-success" /> : <Circle aria-hidden="true" className="size-4 text-muted" />}{LAUNCH_LABEL[l.area]}</span>
              <span className="text-muted">{l.has_items ? `${l.done} of ${l.total} done` : "Nothing tracked yet"}</span>
            </li>
          ))}
        </ul>
        <p className="px-5 pb-4 text-xs text-muted">Deployment: {data.deployment.note}</p>
      </Card>
      <Modal open={adding} onClose={() => setAdding(false)} title="Add a cost or commitment">{adding ? <FinanceForm onDone={() => { setAdding(false); reload(); }} onCancel={() => setAdding(false)} /> : null}</Modal>
      <ConfirmDialog open={remove !== null} destructive title="Delete this entry?" description="The entry will be removed from the totals." confirmLabel="Delete" onCancel={() => setRemove(null)} onConfirm={done} />
    </div>
  );
}
