"use client";

import { CircleCheck } from "lucide-react";
import Link from "next/link";
import { useEffect, useState, type FormEvent } from "react";
import { AuthFormLayout } from "@/features/auth/AuthFormLayout";
import { hasErrors, validateNewPassword, validatePasswordConfirmation } from "@/features/auth/validation";
import { Button } from "@/components/ui/Button";
import { FormError } from "@/components/ui/ErrorMessage";
import { PasswordInput } from "@/components/ui/Input";
import { ApiError } from "@/lib/api";
import { resetPasswordRequest } from "@/lib/auth";

const BACK = (
  <Link href="/login" className="font-medium text-accent-strong hover:underline">
    Back to sign in
  </Link>
);

/** The reset token arrives in the URL fragment (#token=...), is read once and removed from the address bar. */
export function ResetPasswordForm() {
  const [token, setToken] = useState<string | null | undefined>(undefined); // undefined: not read yet
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [errors, setErrors] = useState<Record<string, string | undefined>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [done, setDone] = useState(false);

  useEffect(() => {
    const found = new URLSearchParams(window.location.hash.replace(/^#/, "")).get("token");
    if (found) window.history.replaceState(null, "", window.location.pathname);
    Promise.resolve(found).then(setToken);
  }, []);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFormError(null);
    const next = { password: validateNewPassword(password), confirm: validatePasswordConfirmation(password, confirm) };
    setErrors(next);
    if (hasErrors(next) || !token) return;
    setSubmitting(true);
    try {
      await resetPasswordRequest({ token, password });
      setDone(true);
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) setToken(null);
      else setFormError(err instanceof ApiError ? err.message : "Something unexpected happened. Please try again.");
    } finally {
      setSubmitting(false);
    }
  }

  if (token === undefined) return <AuthFormLayout title="Choose a new password" description="One moment…" footer={BACK}>{null}</AuthFormLayout>;

  if (done) {
    return (
      <AuthFormLayout title="Password changed" description="You were signed out everywhere. Sign in with your new password." footer={BACK}>
        <div role="status" className="flex items-start gap-3 rounded-lg border border-success/30 bg-success-soft px-4 py-3.5 text-sm text-success">
          <CircleCheck aria-hidden="true" className="mt-0.5 size-5 shrink-0" />
          <p>Your password has been updated.</p>
        </div>
      </AuthFormLayout>
    );
  }

  if (token === null) {
    return (
      <AuthFormLayout
        title="This link can't be used"
        description="It may have expired or already been used. Reset links work once."
        footer={
          <Link href="/forgot-password" className="font-medium text-accent-strong hover:underline">
            Request a new link
          </Link>
        }
      >
        {null}
      </AuthFormLayout>
    );
  }

  return (
    <AuthFormLayout title="Choose a new password" description="Use at least 10 characters." footer={BACK}>
      <form onSubmit={onSubmit} noValidate className="space-y-5">
        {formError ? <FormError message={formError} /> : null}
        <PasswordInput label="New password" name="password" autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} error={errors.password} />
        <PasswordInput label="Confirm new password" name="confirm" autoComplete="new-password" value={confirm} onChange={(e) => setConfirm(e.target.value)} error={errors.confirm} />
        <Button type="submit" size="lg" className="w-full" loading={submitting} loadingLabel="Saving password">
          Change password
        </Button>
      </form>
    </AuthFormLayout>
  );
}
