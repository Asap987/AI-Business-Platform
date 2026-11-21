"use client";

import { ShieldCheck } from "lucide-react";
import { useState } from "react";
import { PageHeader } from "@/components/layout/PageHeader";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { FormError } from "@/components/ui/ErrorMessage";
import { Skeleton } from "@/components/ui/LoadingSpinner";
import { Pagination } from "@/components/ui/Pagination";
import { ResourceView } from "@/components/ui/ResourceView";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/Table";
import { errorText, pageCount } from "@/features/org/shared";
import { useApiResource } from "@/hooks/useApiResource";
import { usePermission } from "@/hooks/usePermission";
import { api } from "@/lib/api";
import { cn, formatRelativeTime } from "@/lib/utils";
import type { Paginated } from "@/types/api";
import type { AuditEntry, PrivacySettings } from "@/types/org";

const PAGE_SIZE = 20;

const ACTIONS: Record<string, string> = {
  "privacy.updated": "Changed privacy settings",
  "invite.created": "Invited a team member",
  "invite.revoked": "Withdrew an invitation",
  "invite.accepted": "Accepted an invitation",
  "user.updated": "Changed a team member",
};

function describe(entry: AuditEntry): string {
  const d = entry.detail;
  if (entry.action === "privacy.updated" && d.changed && typeof d.changed === "object") {
    return Object.entries(d.changed as Record<string, boolean>)
      .map(([k, v]) => `${k === "ai_providers_enabled" ? "AI providers" : "Mask contact details"}: ${v ? "on" : "off"}`)
      .join(", ");
  }
  const parts = [typeof d.email === "string" ? d.email : null, typeof d.role === "string" ? `role ${d.role}` : null, typeof d.status === "string" ? `status ${d.status}` : null];
  return parts.filter(Boolean).join(" · ") || "—";
}

function Toggle({ id, label, description, checked, disabled, onChange }: { id: string; label: string; description: string; checked: boolean; disabled: boolean; onChange: (v: boolean) => void }) {
  return (
    <div className="flex items-start justify-between gap-4 py-4">
      <div>
        <label htmlFor={id} className="text-sm font-medium text-ink">{label}</label>
        <p id={`${id}-d`} className="mt-1 max-w-xl text-sm text-muted">{description}</p>
      </div>
      <button
        id={id}
        type="button"
        role="switch"
        aria-checked={checked}
        aria-describedby={`${id}-d`}
        disabled={disabled}
        onClick={() => onChange(!checked)}
        className={cn(
          "relative mt-1 inline-flex h-6 w-11 shrink-0 items-center rounded-full border border-border transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent disabled:opacity-50",
          checked ? "bg-accent" : "bg-surface-muted",
        )}
      >
        <span className={cn("inline-block size-4 rounded-full bg-white shadow transition-transform", checked ? "translate-x-6" : "translate-x-1")} />
      </button>
    </div>
  );
}

function AuditLog() {
  const [page, setPage] = useState(1);
  const resource = useApiResource<Paginated<AuditEntry>>("/audit", { page, page_size: PAGE_SIZE });
  return (
    <ResourceView
      resource={resource}
      compact={false}
      isEmpty={(d) => d.items.length === 0}
      skeleton={<div className="space-y-3 p-5"><Skeleton className="h-10" /><Skeleton className="h-10" /></div>}
      empty={<EmptyState icon={ShieldCheck} title="No activity yet" description="Changes to privacy settings and team access will be listed here." />}
    >
      {(data) => (
        <>
          <Table caption="Activity log">
            <TableHead>
              <tr>
                <TableHeader>What</TableHeader>
                <TableHeader>Details</TableHeader>
                <TableHeader>Who</TableHeader>
                <TableHeader>When</TableHeader>
              </tr>
            </TableHead>
            <TableBody>
              {data.items.map((e) => (
                <TableRow key={e.id}>
                  <TableCell className="font-medium">{ACTIONS[e.action] ?? e.action}</TableCell>
                  <TableCell>{describe(e)}</TableCell>
                  <TableCell>{e.actor_name ?? "System"}</TableCell>
                  <TableCell>{formatRelativeTime(e.created_at)}</TableCell>
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
  );
}

export function PrivacyView() {
  const canRead = usePermission("privacy:read");
  const canWrite = usePermission("privacy:write");
  const canAudit = usePermission("audit:read");
  const resource = useApiResource<PrivacySettings>(canRead ? "/privacy" : null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [logKey, setLogKey] = useState(0);

  async function change(body: Partial<PrivacySettings>) {
    setSaving(true);
    setError(null);
    try {
      await api.patch("/privacy", body);
      resource.reload();
      setLogKey((k) => k + 1);
    } catch (e) {
      setError(errorText(e));
    } finally {
      setSaving(false);
    }
  }

  if (!canRead) {
    return (
      <>
        <PageHeader title="Privacy & AI" description="Control what customer information AI providers may receive." />
        <Card><EmptyState icon={ShieldCheck} title="Permission denied" description="Your role can't view privacy settings. Ask an administrator." /></Card>
      </>
    );
  }

  return (
    <>
      <PageHeader title="Privacy & AI" description="Control what customer information AI providers may receive." />
      {error ? <div className="mb-4"><FormError message={error} /></div> : null}
      <Card className="mb-8 px-5">
        <ResourceView resource={resource} compact={false} skeleton={<div className="space-y-3 py-5"><Skeleton className="h-12" /><Skeleton className="h-12" /></div>}>
          {(s) => (
            <div className="divide-y divide-border">
              <Toggle
                id="ai-enabled" label="Allow AI providers" checked={s.ai_providers_enabled} disabled={!canWrite || saving}
                description="When off, voice calls are refused and no customer speech or text is sent to OpenAI or ElevenLabs for this business. Turn off to stop AI immediately."
                onChange={(v) => void change({ ai_providers_enabled: v })}
              />
              <Toggle
                id="mask-contact" label="Mask contact details before they reach the AI" checked={s.redact_contact_details} disabled={!canWrite || saving}
                description="Replaces email addresses and phone numbers in what the customer says with a placeholder before it is sent to the AI. The assistant then can't read them back or log them in a case by voice."
                onChange={(v) => void change({ redact_contact_details: v })}
              />
              <div className="py-4">
                <p className="text-sm font-medium text-ink">Secrets are always masked</p>
                <p className="mt-1 max-w-xl text-sm text-muted">
                  {s.redact_secrets ? "Card numbers, passwords, PINs, one-time codes and CVVs are masked before text reaches the AI. " : "Secret masking is switched off on this server. "}
                  Masking is a safety net, not a guarantee: ask customers not to read out secrets. Nothing from calls is stored by this platform yet.
                </p>
              </div>
            </div>
          )}
        </ResourceView>
      </Card>
      {canAudit ? (
        <>
          <h2 className="mb-3 text-base font-semibold text-ink">Activity log</h2>
          <Card key={logKey}><AuditLog /></Card>
        </>
      ) : null}
    </>
  );
}
