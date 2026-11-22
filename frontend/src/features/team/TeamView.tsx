"use client";

import { Check, Copy, Mail, UserPlus } from "lucide-react";
import { useState, type FormEvent } from "react";
import { PageHeader } from "@/components/layout/PageHeader";
import { StatusBadge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { FormError } from "@/components/ui/ErrorMessage";
import { Input } from "@/components/ui/Input";
import { Skeleton } from "@/components/ui/LoadingSpinner";
import { ConfirmDialog, Modal } from "@/components/ui/Modal";
import { ResourceView } from "@/components/ui/ResourceView";
import { Select } from "@/components/ui/Select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/Table";
import { errorText, useEmployeeOptions } from "@/features/org/shared";
import { useApiResource } from "@/hooks/useApiResource";
import { usePermission } from "@/hooks/usePermission";
import { api, ApiError } from "@/lib/api";
import { formatLongDate, formatRelativeTime } from "@/lib/utils";
import { useAuth } from "@/providers/AuthProvider";
import type { CreatedInvite, TeamInvite, TeamRole, TeamUser } from "@/types/org";

function InviteForm({ roles, onDone, onCancel }: { roles: TeamRole[]; onDone: () => void; onCancel: () => void }) {
  const employees = useEmployeeOptions(true);
  const [email, setEmail] = useState("");
  const [roleId, setRoleId] = useState(roles.find((r) => r.name === "Employee")?.id ?? roles[0]?.id ?? "");
  const [employeeId, setEmployeeId] = useState("");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [created, setCreated] = useState<CreatedInvite | null>(null);
  const [copied, setCopied] = useState(false);

  // The token goes in the fragment: browsers never send it to a server, so it stays out of logs.
  const link = created ? `${window.location.origin}/accept-invite#token=${created.token}` : "";

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFormError(null);
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email.trim())) {
      setErrors({ email: "Enter a valid email address." });
      return;
    }
    setErrors({});
    setSaving(true);
    try {
      setCreated(await api.post<CreatedInvite>("/users/invites", { email: email.trim(), role_id: roleId, employee_id: employeeId || null }));
    } catch (error) {
      if (error instanceof ApiError && error.kind === "validation") setErrors(error.fieldErrors);
      setFormError(errorText(error));
    } finally {
      setSaving(false);
    }
  }

  async function copy() {
    try {
      await navigator.clipboard.writeText(link);
      setCopied(true);
    } catch {
      setCopied(false); // the link stays selectable in the field below
    }
  }

  if (created) {
    return (
      <div className="space-y-4">
        <p className="text-sm text-ink">
          {created.email_sent ? (
            <>
              We emailed an invitation to <strong>{created.email}</strong>. It works once and expires in 7 days. You can also share this link yourself.
            </>
          ) : (
            <>
              The invitation email was not sent, so send this link to <strong>{created.email}</strong> yourself. It works once and expires in 7 days.
            </>
          )}
        </p>
        <Input label="Invitation link" name="invite_link" value={link} readOnly onFocus={(e) => e.currentTarget.select()} />
        <p className="text-sm text-muted">
          For security this link is shown only now and can&apos;t be retrieved later. If it&apos;s lost, withdraw the invitation and create a new one.
        </p>
        <div className="flex justify-end gap-2 pt-2">
          <Button variant="secondary" onClick={() => void copy()}>
            {copied ? <Check aria-hidden="true" className="size-4" /> : <Copy aria-hidden="true" className="size-4" />}
            {copied ? "Copied" : "Copy link"}
          </Button>
          <Button onClick={onDone}>Done</Button>
        </div>
      </div>
    );
  }

  return (
    <form onSubmit={onSubmit} noValidate className="space-y-4">
      {formError ? <FormError message={formError} /> : null}
      <Input label="Email address" type="email" name="email" inputMode="email" value={email} onChange={(e) => setEmail(e.target.value)} error={errors.email} />
      <Select label="Role" name="role_id" value={roleId} onChange={(e) => setRoleId(e.target.value)} error={errors.role_id}>
        {roles.map((r) => (
          <option key={r.id} value={r.id}>
            {r.name}
          </option>
        ))}
      </Select>
      {employees.allowed ? (
        <Select label="Link to an employee (optional)" name="employee_id" value={employeeId} onChange={(e) => setEmployeeId(e.target.value)} hint="So cases can be assigned to this person's login.">
          <option value="">Not linked</option>
          {employees.items.filter((e) => !e.has_login).map((e) => (
            <option key={e.id} value={e.id}>
              {e.full_name}
            </option>
          ))}
        </Select>
      ) : null}
      <div className="flex justify-end gap-2 pt-2">
        <Button variant="secondary" onClick={onCancel} disabled={saving}>
          Cancel
        </Button>
        <Button type="submit" loading={saving} loadingLabel="Creating">
          Create invitation
        </Button>
      </div>
    </form>
  );
}

export function TeamView() {
  const { user: me } = useAuth();
  const canRead = usePermission("users:read");
  const canWrite = usePermission("users:write");
  const users = useApiResource<{ items: TeamUser[] }>(canRead ? "/users" : null);
  const invites = useApiResource<{ items: TeamInvite[] }>(canRead ? "/users/invites" : null);
  const roles = useApiResource<{ items: TeamRole[] }>(canRead ? "/roles" : null);
  const [inviting, setInviting] = useState(false);
  const [revoking, setRevoking] = useState<TeamInvite | null>(null);
  const [disabling, setDisabling] = useState<TeamUser | null>(null);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  async function patchUser(u: TeamUser, body: { role_id?: string; status?: "active" | "disabled" }) {
    setActionError(null);
    try {
      await api.patch(`/users/${u.id}`, body);
    } catch (error) {
      setActionError(errorText(error));
    }
    users.reload();
  }

  async function confirmRevoke() {
    if (!revoking) return;
    setBusy(true);
    try {
      await api.delete(`/users/invites/${revoking.id}`);
      setRevoking(null);
    } catch (error) {
      setActionError(errorText(error));
      setRevoking(null);
    } finally {
      setBusy(false);
      invites.reload();
    }
  }

  if (!canRead) {
    return (
      <>
        <PageHeader title="Team" description="People who can sign in to your business." />
        <Card>
          <EmptyState icon={Mail} title="Permission denied" description="Your role can't view the team. Ask an administrator." />
        </Card>
      </>
    );
  }

  const roleList = roles.data?.items ?? [];
  return (
    <>
      <PageHeader
        title="Team"
        description="People who can sign in to your business, and what each role can do."
        actions={
          canWrite ? (
            <Button onClick={() => setInviting(true)} disabled={roleList.length === 0}>
              <UserPlus aria-hidden="true" className="size-4" />
              Invite person
            </Button>
          ) : null
        }
      />
      {actionError ? (
        <div className="mb-4">
          <FormError message={actionError} />
        </div>
      ) : null}

      <Card>
        <ResourceView
          resource={users}
          compact={false}
          isEmpty={(d) => d.items.length === 0}
          skeleton={<div className="space-y-3 p-5"><Skeleton className="h-10" /><Skeleton className="h-10" /></div>}
          empty={<EmptyState icon={Mail} title="No team members" description="Invite the people who will sign in." />}
        >
          {(data) => (
            <Table caption="Team members">
              <TableHead>
                <tr>
                  <TableHeader>Person</TableHeader>
                  <TableHeader>Role</TableHeader>
                  <TableHeader>Status</TableHeader>
                  <TableHeader>Last sign-in</TableHeader>
                  {canWrite ? <TableHeader><span className="sr-only">Actions</span></TableHeader> : null}
                </tr>
              </TableHead>
              <TableBody>
                {data.items.map((u) => {
                  const isMe = u.id === me?.id;
                  return (
                    <TableRow key={u.id}>
                      <TableCell>
                        <p className="font-medium">{u.full_name}{isMe ? " (you)" : ""}</p>
                        <p className="text-sm text-muted">{u.email}</p>
                      </TableCell>
                      <TableCell>
                        {canWrite && !isMe ? (
                          <Select label={`Role for ${u.full_name}`} hideLabel value={u.role.id} onChange={(e) => void patchUser(u, { role_id: e.target.value })}>
                            {roleList.map((r) => (
                              <option key={r.id} value={r.id}>{r.name}</option>
                            ))}
                          </Select>
                        ) : (
                          u.role.name
                        )}
                      </TableCell>
                      <TableCell><StatusBadge status={u.status === "disabled" ? "inactive" : u.status} label={u.status === "disabled" ? "Disabled" : undefined} /></TableCell>
                      <TableCell>{u.last_login_at ? formatRelativeTime(u.last_login_at) : "Never"}</TableCell>
                      {canWrite ? (
                        <TableCell className="text-right">
                          {isMe ? null : u.status === "disabled" ? (
                            <Button variant="ghost" size="sm" onClick={() => void patchUser(u, { status: "active" })} aria-label={`Enable ${u.full_name}`}>Enable</Button>
                          ) : (
                            <Button variant="ghost" size="sm" onClick={() => setDisabling(u)} aria-label={`Disable ${u.full_name}`}>Disable</Button>
                          )}
                        </TableCell>
                      ) : null}
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          )}
        </ResourceView>
      </Card>

      <h2 className="mb-3 mt-8 text-base font-semibold text-ink">Pending invitations</h2>
      <Card>
        <ResourceView
          resource={invites}
          compact={false}
          isEmpty={(d) => d.items.length === 0}
          skeleton={<div className="space-y-3 p-5"><Skeleton className="h-10" /></div>}
          empty={<EmptyState icon={Mail} title="No pending invitations" description="Invitations you create appear here until they're accepted or expire." />}
        >
          {(data) => (
            <Table caption="Pending invitations">
              <TableHead>
                <tr>
                  <TableHeader>Email</TableHeader>
                  <TableHeader>Role</TableHeader>
                  <TableHeader>Expires</TableHeader>
                  {canWrite ? <TableHeader><span className="sr-only">Actions</span></TableHeader> : null}
                </tr>
              </TableHead>
              <TableBody>
                {data.items.map((i) => (
                  <TableRow key={i.id}>
                    <TableCell>{i.email}</TableCell>
                    <TableCell>{i.role.name}</TableCell>
                    <TableCell>{i.expired ? "Expired" : formatLongDate(new Date(i.expires_at))}</TableCell>
                    {canWrite ? (
                      <TableCell className="text-right">
                        <Button variant="ghost" size="sm" onClick={() => setRevoking(i)} aria-label={`Withdraw invitation for ${i.email}`}>Withdraw</Button>
                      </TableCell>
                    ) : null}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </ResourceView>
      </Card>

      <Modal open={inviting} onClose={() => { setInviting(false); invites.reload(); }} title="Invite a person">
        {inviting ? <InviteForm roles={roleList} onCancel={() => setInviting(false)} onDone={() => { setInviting(false); invites.reload(); users.reload(); }} /> : null}
      </Modal>
      <ConfirmDialog
        open={revoking !== null}
        onCancel={() => setRevoking(null)}
        onConfirm={() => void confirmRevoke()}
        title="Withdraw this invitation?"
        description={`${revoking?.email ?? "This person"} will no longer be able to use their link.`}
        confirmLabel="Withdraw"
        destructive
        loading={busy}
      />
      <ConfirmDialog
        open={disabling !== null}
        onCancel={() => setDisabling(null)}
        onConfirm={() => {
          const u = disabling;
          setDisabling(null);
          if (u) void patchUser(u, { status: "disabled" });
        }}
        title={`Disable ${disabling?.full_name ?? "this person"}?`}
        description="They are signed out immediately and can't sign in until you enable them again."
        confirmLabel="Disable"
        destructive
      />
    </>
  );
}
