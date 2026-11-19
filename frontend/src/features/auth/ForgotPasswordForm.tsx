"use client";

import { MailCheck } from "lucide-react";
import Link from "next/link";
import { useState, type FormEvent } from "react";
import { AuthFormLayout } from "@/features/auth/AuthFormLayout";
import { validateEmail } from "@/features/auth/validation";
import { Button } from "@/components/ui/Button";
import { FormError } from "@/components/ui/ErrorMessage";
import { Input } from "@/components/ui/Input";
import { ApiError } from "@/lib/api";
import { forgotPasswordRequest } from "@/lib/auth";

export function ForgotPasswordForm() {
  const [email, setEmail] = useState("");
  const [emailError, setEmailError] = useState<string | undefined>();
  const [formError, setFormError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [sentTo, setSentTo] = useState<string | null>(null);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFormError(null);

    const error = validateEmail(email);
    setEmailError(error);
    if (error) return;

    setSubmitting(true);
    try {
      await forgotPasswordRequest({ email: email.trim() });
      setSentTo(email.trim());
    } catch (err) {
      if (err instanceof ApiError && err.kind === "not_found") {
        setFormError("Password reset isn't available yet because the backend recovery endpoint hasn't been built.");
      } else if (err instanceof ApiError && err.kind === "validation") {
        setEmailError(err.fieldErrors.email);
        if (!err.fieldErrors.email) setFormError(err.message);
      } else if (err instanceof ApiError) {
        setFormError(err.message);
      } else {
        setFormError("Something unexpected happened. Please try again.");
      }
    } finally {
      setSubmitting(false);
    }
  }

  if (sentTo) {
    return (
      <AuthFormLayout
        title="Check your email"
        description="If an account exists for that address, we've sent instructions for resetting your password."
        footer={
          <Link href="/login" className="font-medium text-accent-strong hover:underline">
            Back to sign in
          </Link>
        }
      >
        <div role="status" className="flex items-start gap-3 rounded-lg border border-success/30 bg-success-soft px-4 py-3.5 text-sm text-success">
          <MailCheck aria-hidden="true" className="mt-0.5 size-5 shrink-0" />
          <p>
            Reset instructions requested for <span className="font-medium">{sentTo}</span>. It can take a few minutes to
            arrive.
          </p>
        </div>
      </AuthFormLayout>
    );
  }

  return (
    <AuthFormLayout
      title="Reset your password"
      description="Enter the email address for your account and we'll send you reset instructions."
      footer={
        <Link href="/login" className="font-medium text-accent-strong hover:underline">
          Back to sign in
        </Link>
      }
    >
      <form onSubmit={onSubmit} noValidate className="space-y-5">
        {formError ? <FormError message={formError} /> : null}
        <Input
          label="Email address"
          type="email"
          name="email"
          autoComplete="email"
          inputMode="email"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          error={emailError}
        />
        <Button type="submit" size="lg" className="w-full" loading={submitting} loadingLabel="Sending instructions">
          Send reset instructions
        </Button>
      </form>
    </AuthFormLayout>
  );
}
