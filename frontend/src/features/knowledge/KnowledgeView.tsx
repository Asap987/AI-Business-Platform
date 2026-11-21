"use client";

import { BookOpen, FileUp, Pencil, Plus, Search, Trash2 } from "lucide-react";
import { useRef, useState, type FormEvent } from "react";
import { PageHeader } from "@/components/layout/PageHeader";
import { StatusBadge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorMessage, FormError } from "@/components/ui/ErrorMessage";
import { Input, SearchInput } from "@/components/ui/Input";
import { LoadingSpinner, Skeleton } from "@/components/ui/LoadingSpinner";
import { ConfirmDialog, Modal } from "@/components/ui/Modal";
import { Pagination } from "@/components/ui/Pagination";
import { ResourceView } from "@/components/ui/ResourceView";
import { Select, Textarea } from "@/components/ui/Select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/Table";
import { errorText, pageCount } from "@/features/org/shared";
import { useApiResource } from "@/hooks/useApiResource";
import { useDebouncedValue } from "@/hooks/useDebouncedValue";
import { usePermission } from "@/hooks/usePermission";
import { api, ApiError } from "@/lib/api";
import { formatRelativeTime } from "@/lib/utils";
import type { Paginated } from "@/types/api";
import type { KnowledgeDoc, KnowledgeHit } from "@/types/org";

const PAGE_SIZE = 20;
const MAX_CHARS = 50_000;
const MAX_FILE_BYTES = 200_000;

function DocForm({ doc, onSaved, onCancel }: { doc: KnowledgeDoc | null; onSaved: () => void; onCancel: () => void }) {
  const [title, setTitle] = useState(doc?.title ?? "");
  const [category, setCategory] = useState(doc?.category ?? "");
  const [content, setContent] = useState(doc?.content ?? "");
  const [status, setStatus] = useState<string>(doc?.status ?? "published");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  async function onFile(file: File | undefined) {
    if (!file) return;
    setFormError(null);
    if (file.size > MAX_FILE_BYTES) {
      setFormError("That file is too large. Plain-text files up to 200 KB are supported; split long documents.");
      return;
    }
    if (!/\.(txt|md|markdown)$/i.test(file.name) && !file.type.startsWith("text/")) {
      setFormError("Only plain-text (.txt) and Markdown (.md) files can be imported. Paste the text of other documents instead.");
      return;
    }
    setContent(await file.text()); // read in the browser; nothing is uploaded until you press Save
    if (!title.trim()) setTitle(file.name.replace(/\.[^.]+$/, ""));
  }

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFormError(null);
    const next: Record<string, string> = {};
    if (title.trim().length < 2) next.title = "Enter a title (at least 2 characters).";
    if (content.trim().length < 3) next.content = "Add the information the assistant may use.";
    if (content.length > MAX_CHARS) next.content = `Too long (${content.length.toLocaleString()} of ${MAX_CHARS.toLocaleString()} characters). Split it into several documents.`;
    setErrors(next);
    if (Object.keys(next).length) return;
    const body = { title: title.trim(), category: category.trim() || null, content: content.trim(), status };
    setSaving(true);
    try {
      if (doc) await api.patch(`/knowledge/${doc.id}`, body);
      else await api.post("/knowledge", body);
      onSaved();
    } catch (error) {
      if (error instanceof ApiError && error.kind === "validation") setErrors(error.fieldErrors);
      setFormError(errorText(error));
      setSaving(false);
    }
  }

  return (
    <form onSubmit={onSubmit} noValidate className="space-y-4">
      {formError ? <FormError message={formError} /> : null}
      <Input label="Title" name="title" value={title} onChange={(e) => setTitle(e.target.value)} error={errors.title} maxLength={200} />
      <div className="grid gap-4 sm:grid-cols-2">
        <Input label="Category (optional)" name="category" value={category} onChange={(e) => setCategory(e.target.value)} maxLength={60} hint="e.g. Policies, Opening hours" />
        <Select label="Status" name="status" value={status} onChange={(e) => setStatus(e.target.value)} hint="Archived documents are not used by the assistant.">
          <option value="published">Published</option>
          <option value="archived">Archived</option>
        </Select>
      </div>
      <Textarea label="Content" name="content" rows={10} value={content} onChange={(e) => setContent(e.target.value)} error={errors.content}
        hint="Write plainly, one topic per paragraph. Don't include passwords, card numbers or other secrets." />
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <input ref={fileRef} type="file" accept=".txt,.md,.markdown,text/plain,text/markdown" className="sr-only" aria-label="Import a text file" onChange={(e) => { void onFile(e.target.files?.[0]); e.target.value = ""; }} />
          <Button variant="secondary" size="sm" onClick={() => fileRef.current?.click()}>
            <FileUp aria-hidden="true" className="size-4" />
            Import .txt or .md
          </Button>
        </div>
        <p className="text-xs text-muted">{content.length.toLocaleString()} / {MAX_CHARS.toLocaleString()} characters</p>
      </div>
      <div className="flex justify-end gap-2 pt-2">
        <Button variant="secondary" onClick={onCancel} disabled={saving}>Cancel</Button>
        <Button type="submit" loading={saving} loadingLabel="Saving">{doc ? "Save changes" : "Add document"}</Button>
      </div>
    </form>
  );
}

function EditLoader({ id, onSaved, onCancel }: { id: string; onSaved: () => void; onCancel: () => void }) {
  const resource = useApiResource<KnowledgeDoc>(`/knowledge/${id}`);
  if (resource.status === "loading") return <div className="flex justify-center py-10"><LoadingSpinner label="Loading document" /></div>;
  if (resource.status === "error" || !resource.data) return <ErrorMessage error={resource.error!} onRetry={resource.reload} />;
  return <DocForm doc={resource.data} onSaved={onSaved} onCancel={onCancel} />;
}

function TryItPanel() {
  const [question, setQuestion] = useState("");
  const [state, setState] = useState<{ hits: KnowledgeHit[]; asked: string } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function ask(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const q = question.trim();
    if (q.length < 2) return;
    setBusy(true);
    setError(null);
    try {
      const res = await api.get<{ items: KnowledgeHit[] }>("/knowledge/search", { query: { q } });
      setState({ hits: res.items, asked: q });
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card className="mb-6 p-5">
      <h2 className="text-base font-semibold text-ink">Test a question</h2>
      <p className="mt-1 text-sm text-muted">See which passages the assistant would find for a customer&apos;s question. If nothing useful appears, it would hand over to a person instead of guessing.</p>
      <form onSubmit={ask} className="mt-4 flex gap-2" role="search">
        <div className="flex-1">
          <Input label="Customer question" hideLabel name="question" placeholder="e.g. What time do you open on Saturday?" value={question} onChange={(e) => setQuestion(e.target.value)} maxLength={300} />
        </div>
        <Button type="submit" loading={busy} loadingLabel="Searching"><Search aria-hidden="true" className="size-4" />Search</Button>
      </form>
      {error ? <div className="mt-3"><FormError message={error} /></div> : null}
      {state ? (
        <div className="mt-4 space-y-3" aria-live="polite">
          {state.hits.length === 0 ? (
            <p className="text-sm text-ink">No passage matches &ldquo;{state.asked}&rdquo;. The assistant would offer to connect a team member.</p>
          ) : (
            state.hits.map((h, i) => (
              <div key={`${h.document_id}-${i}`} className="rounded-lg border border-border p-3">
                <p className="text-sm font-medium text-ink">{h.title}{h.category ? <span className="font-normal text-muted"> · {h.category}</span> : null}</p>
                <p className="mt-1 whitespace-pre-line text-sm text-muted">{h.text}</p>
              </div>
            ))
          )}
        </div>
      ) : null}
    </Card>
  );
}

export function KnowledgeView() {
  const canRead = usePermission("knowledge:read");
  const canWrite = usePermission("knowledge:write");
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
  const [editing, setEditing] = useState<KnowledgeDoc | "new" | null>(null);
  const [deleting, setDeleting] = useState<KnowledgeDoc | null>(null);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const q = useDebouncedValue(search.trim(), 300);
  const resource = useApiResource<Paginated<KnowledgeDoc>>(canRead ? "/knowledge" : null, { page, page_size: PAGE_SIZE, q: q || undefined, status: status || undefined });
  const filtered = Boolean(q || status);

  async function confirmDelete() {
    if (!deleting) return;
    setBusy(true);
    try {
      await api.delete(`/knowledge/${deleting.id}`);
    } catch (error) {
      setActionError(errorText(error));
    } finally {
      setBusy(false);
      setDeleting(null);
      resource.reload();
    }
  }

  if (!canRead) {
    return (
      <>
        <PageHeader title="Knowledge Base" description="Approved information the assistant can use to answer customers." />
        <Card><EmptyState icon={BookOpen} title="Permission denied" description="Your role can't view the knowledge base. Ask an administrator." /></Card>
      </>
    );
  }

  return (
    <>
      <PageHeader
        title="Knowledge Base"
        description="Approved information the assistant can use to answer customers."
        actions={canWrite ? <Button onClick={() => setEditing("new")}><Plus aria-hidden="true" className="size-4" />Add document</Button> : null}
      />
      <TryItPanel />
      {actionError ? <div className="mb-4"><FormError message={actionError} /></div> : null}
      <Card>
        <div className="grid gap-3 border-b border-border p-4 sm:grid-cols-[1fr_12rem]">
          <SearchInput label="Search documents" placeholder="Search by title or category…" value={search} onValueChange={(v) => { setSearch(v); setPage(1); }} />
          <Select label="Status" hideLabel value={status} onChange={(e) => { setStatus(e.target.value); setPage(1); }}>
            <option value="">All statuses</option>
            <option value="published">Published</option>
            <option value="archived">Archived</option>
          </Select>
        </div>
        <ResourceView
          resource={resource}
          compact={false}
          isEmpty={(d) => d.items.length === 0}
          skeleton={<div className="space-y-3 p-5"><Skeleton className="h-10" /><Skeleton className="h-10" /></div>}
          empty={
            <EmptyState
              icon={BookOpen}
              title={filtered ? "No documents match" : "No documents yet"}
              description={filtered ? "Try a different search or clear the filter." : "Add your opening hours, policies and procedures. The assistant will answer only from what you publish here."}
              action={!filtered && canWrite ? <Button onClick={() => setEditing("new")}>Add document</Button> : undefined}
            />
          }
        >
          {(data) => (
            <>
              <Table caption="Knowledge base documents">
                <TableHead>
                  <tr>
                    <TableHeader>Title</TableHeader>
                    <TableHeader>Category</TableHeader>
                    <TableHeader>Status</TableHeader>
                    <TableHeader>Updated</TableHeader>
                    {canWrite ? <TableHeader><span className="sr-only">Actions</span></TableHeader> : null}
                  </tr>
                </TableHead>
                <TableBody>
                  {data.items.map((d) => (
                    <TableRow key={d.id}>
                      <TableCell className="font-medium">{d.title}</TableCell>
                      <TableCell>{d.category ?? "—"}</TableCell>
                      <TableCell><StatusBadge status={d.status === "archived" ? "inactive" : "active"} label={d.status === "archived" ? "Archived" : "Published"} /></TableCell>
                      <TableCell>{formatRelativeTime(d.updated_at)}</TableCell>
                      {canWrite ? (
                        <TableCell className="text-right">
                          <div className="flex justify-end gap-1">
                            <Button variant="ghost" size="sm" onClick={() => setEditing(d)} aria-label={`Edit ${d.title}`}><Pencil aria-hidden="true" className="size-4" />Edit</Button>
                            <Button variant="ghost" size="sm" onClick={() => { setActionError(null); setDeleting(d); }} aria-label={`Delete ${d.title}`}><Trash2 aria-hidden="true" className="size-4" />Delete</Button>
                          </div>
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

      <Modal open={editing !== null} onClose={() => setEditing(null)} title={editing === "new" ? "Add document" : "Edit document"} size="lg">
        {editing === "new" ? (
          <DocForm doc={null} onCancel={() => setEditing(null)} onSaved={() => { setEditing(null); resource.reload(); }} />
        ) : editing ? (
          <EditLoader id={editing.id} onCancel={() => setEditing(null)} onSaved={() => { setEditing(null); resource.reload(); }} />
        ) : null}
      </Modal>
      <ConfirmDialog
        open={deleting !== null}
        onCancel={() => setDeleting(null)}
        onConfirm={() => void confirmDelete()}
        title={`Delete ${deleting?.title ?? "document"}?`}
        description="The assistant will stop using it straight away. This can't be undone. To keep it but stop using it, archive it instead."
        confirmLabel="Delete document"
        destructive
        loading={busy}
      />
    </>
  );
}
