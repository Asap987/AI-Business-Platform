"use client";

import { useState, type FormEvent } from "react";
import { Button } from "@/components/ui/Button";
import { FormError } from "@/components/ui/ErrorMessage";
import { Input } from "@/components/ui/Input";
import { errorText } from "@/features/org/shared";
import { api, ApiError } from "@/lib/api";
import type { Customer } from "@/types/org";

export function CustomerForm({ customer, onSaved, onCancel }: { customer: Customer | null; onSaved: () => void; onCancel: () => void }) {
  const [fullName, setFullName] = useState(customer?.full_name ?? "");
  const [email, setEmail] = useState(customer?.email ?? "");
  const [phone, setPhone] = useState(customer?.phone ?? "");
  const [reference, setReference] = useState(customer?.external_ref ?? "");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFormError(null);
    if (!fullName.trim()) {
      setErrors({ full_name: "Enter the customer's name." });
      return;
    }
    setErrors({});
    const body = {
      full_name: fullName.trim(),
      email: email.trim() || null,
      phone: phone.trim() || null,
      external_ref: reference.trim() || null,
    };
    setSaving(true);
    try {
      if (customer) await api.patch(`/customers/${customer.id}`, body);
      else await api.post("/customers", body);
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
      <Input label="Full name" name="full_name" value={fullName} onChange={(e) => setFullName(e.target.value)} error={errors.full_name} maxLength={200} />
      <div className="grid gap-4 sm:grid-cols-2">
        <Input label="Phone (optional)" name="phone" type="tel" value={phone} onChange={(e) => setPhone(e.target.value)} error={errors.phone} maxLength={40} />
        <Input label="Email (optional)" name="email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} error={errors.email} maxLength={254} />
      </div>
      <Input
        label="Your reference (optional)"
        hint="An account or customer number from your own records."
        name="external_ref"
        value={reference}
        onChange={(e) => setReference(e.target.value)}
        error={errors.external_ref}
        maxLength={100}
      />
      <div className="flex justify-end gap-2 pt-2">
        <Button variant="secondary" onClick={onCancel} disabled={saving}>
          Cancel
        </Button>
        <Button type="submit" loading={saving} loadingLabel="Saving">
          {customer ? "Save changes" : "Add customer"}
        </Button>
      </div>
    </form>
  );
}
