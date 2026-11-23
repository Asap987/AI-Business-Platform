"use client";

import { useState } from "react";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { FormError } from "@/components/ui/ErrorMessage";
import { Input } from "@/components/ui/Input";
import { errorText } from "@/features/org/shared";
import { api } from "@/lib/api";
import { useAuth } from "@/providers/AuthProvider";

export function MyProfileView() {
  const { user, business, refreshSession } = useAuth();
  const [name, setName] = useState(user?.full_name ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setError(null); setSaved(false);
    try {
      await api.patch("/profile", { full_name: name.trim() });
      await refreshSession();
      setSaved(true);
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <PageHeader title="My profile" description="Your own details. Other people in your business see your name." />
      <Card className="max-w-xl p-5">
        <form onSubmit={save} className="space-y-4">
          <Input label="Your name" value={name} onChange={(e) => { setName(e.target.value); setSaved(false); }} required minLength={2} maxLength={120} />
          <Input label="Email" value={user?.email ?? ""} readOnly disabled hint="Your email is your sign-in. Ask an administrator if it needs to change." />
          <Input label="Role" value={user?.role.name ?? ""} readOnly disabled />
          <Input label="Business" value={business?.name ?? ""} readOnly disabled />
          {error ? <FormError message={error} /> : null}
          <div className="flex items-center gap-3">
            <Button type="submit" disabled={busy || name.trim().length < 2 || name.trim() === user?.full_name}>{busy ? "Saving…" : "Save"}</Button>
            {saved ? <p role="status" className="text-sm text-success">Saved.</p> : null}
          </div>
        </form>
      </Card>
    </>
  );
}
