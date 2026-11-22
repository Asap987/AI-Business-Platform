"use client";

import Link from "next/link";
import { useEffect, useState, type FormEvent } from "react";
import { AuthFormLayout } from "@/features/auth/AuthFormLayout";
import { hasErrors, MIN_PASSWORD_LENGTH, validateNewPassword, validatePasswordConfirmation } from "@/features/auth/validation";
import { Button } from "@/components/ui/Button";
import { FormError } from "@/components/ui/ErrorMessage";
import { Input, PasswordInput } from "@/components/ui/Input";
import { LoadingSpinner } from "@/components/ui/LoadingSpinner";
import { ApiError } from "@/lib/api";
import { inviteInfoRequest, type InviteInfo } from "@/lib/auth";
import { useAuth } from "@/providers/AuthProvider";

type Load = { state: "loading" } | { state: "invalid" } | { state: "error"; message: string } | { state: "ready"; info: InviteInfo };

/**
 * The invitation token travels in the URL fragment (#token=...). Browsers never send the fragment to a
 * server, so it stays out of server logs and Referer headers. It is read once and removed from the address bar.
 */
export function AcceptInviteForm() {
  const { acceptInvite } = useAuth();
  const [token, setToken] = useState<string | null>(null);
  const [load, setLoad] = useState<Load>({ state: "loading" });
  const [fullName, setFullName] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [errors, setErrors] = useState<Record<string, string | undefined>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    const found = new URLSearchParams(window.location.hash.replace(/^#/, "")).get("token");
    if (found) window.history.replaceState(null, "", window.location.pathname);
    // Setting state only inside the promise callbacks keeps the effect itself free of synchronous updates.
    const lookup = found ? inviteInfoRequest(found) : Promise.reject(new ApiError({ status: 404, kind: "not_found", message: "No token" }));
    lookup
      .then((info) => {
        setToken(found);
        setFullName(info.suggested_name ?? "");
        setLoad({ state: "ready", info });
      })
      .catch((error: unknown) => {
        if (error instanceof ApiError && error.status === 404) setLoad({ state: "invalid" });
        else setLoad({ state: "error", message: error instanceof ApiError ? error.message : "Something went wrong. Please try again." });
      });
  }, []);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFormError(null);
    const next = {
      full_name: fullName.trim().length < 2 ? "Enter your full name." : undefined,
      password: validateNewPassword(password),
      confirm: validatePasswordConfirmation(password, confirm),
    };
    setErrors(next);
    if (hasErrors(next) || !token) return;
    setSubmitting(true);
    try {
      await acceptInvite({ token, password, full_name: fullName.trim() });
    } catch (error) {
      if (error instanceof ApiError && error.kind === "validation") {
        setErrors({ full_name: error.fieldErrors.full_name, password: error.fieldErrors.password });
        if (!error.fieldErrors.full_name && !error.fieldErrors.password) setFormError(error.message);
      } else if (error instanceof ApiError && error.status === 404) {
        setLoad({ state: "invalid" });
      } else {
        setFormError(error instanceof ApiError ? error.message : "Something unexpected happened. Please try again.");
      }
      setSubmitting(false);
    }
  }

  if (load.state === "loading") {
    return (
      <div className="flex justify-center py-12">
        <LoadingSpinner label="Checking your invitation" />
      </div>
    );
  }
  if (load.state === "invalid" || load.state === "error") {
    return (
      <AuthFormLayout
        title={load.state === "invalid" ? "This invitation can't be used" : "We couldn't check your invitation"}
        description={
          load.state === "invalid"
            ? "The link may have expired, been used already, or been withdrawn. Ask your administrator to send a new one."
            : load.message
        }
        footer={
          <Link href="/login" className="font-medium text-accent-strong hover:underline">
            Go to sign in
          </Link>
        }
      >
        {null}
      </AuthFormLayout>
    );
  }

  const { info } = load;
  return (
    <AuthFormLayout
      title={`Join ${info.business_name}`}
      description={`You've been invited as ${info.role_name}. Choose a password to finish creating your account.`}
      footer={
        <>
          Already have an account?{" "}
          <Link href="/login" className="font-medium text-accent-strong hover:underline">
            Sign in
          </Link>
        </>
      }
    >
      <form onSubmit={onSubmit} noValidate className="space-y-5">
        {formError ? <FormError message={formError} /> : null}
        <Input label="Email address" name="email" value={info.email} readOnly disabled />
        <Input label="Your full name" name="full_name" autoComplete="name" value={fullName} onChange={(e) => setFullName(e.target.value)} error={errors.full_name} />
        <PasswordInput label="Password" name="password" autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} hint={`At least ${MIN_PASSWORD_LENGTH} characters.`} error={errors.password} />
        <PasswordInput label="Confirm password" name="confirm_password" autoComplete="new-password" value={confirm} onChange={(e) => setConfirm(e.target.value)} error={errors.confirm} />
        <Button type="submit" size="lg" className="w-full" loading={submitting} loadingLabel="Creating account">
          Create account
        </Button>
      </form>
    </AuthFormLayout>
  );
}
