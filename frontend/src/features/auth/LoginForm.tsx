"use client";

import { Info } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useState, type FormEvent } from "react";
import { AuthFormLayout } from "@/features/auth/AuthFormLayout";
import { hasErrors, validateEmail, validateRequired } from "@/features/auth/validation";
import { Button } from "@/components/ui/Button";
import { FormError } from "@/components/ui/ErrorMessage";
import { Input, PasswordInput } from "@/components/ui/Input";
import { ApiError } from "@/lib/api";
import { useAuth } from "@/providers/AuthProvider";

interface FieldErrors {
  email?: string;
  password?: string;
}

export function LoginForm() {
  const { login, sessionExpired } = useAuth();
  const params = useSearchParams();
  const showExpired = sessionExpired || params.get("expired") === "1";

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFormError(null);

    const errors: FieldErrors = {
      email: validateEmail(email),
      password: validateRequired(password, "Enter your password."),
    };
    setFieldErrors(errors);
    if (hasErrors(errors as Record<string, string | undefined>)) return;

    setSubmitting(true);
    try {
      // On success the guard around this page redirects into the app.
      await login({ email: email.trim(), password });
    } catch (error) {
      if (error instanceof ApiError) {
        if (error.kind === "unauthorized") {
          // Deliberately vague: don't reveal whether the email exists.
          setFormError("That email and password don't match. Check them and try again.");
        } else if (error.kind === "validation") {
          setFieldErrors({ email: error.fieldErrors.email, password: error.fieldErrors.password });
          if (!error.fieldErrors.email && !error.fieldErrors.password) setFormError(error.message);
        } else if (error.kind === "not_found") {
          setFormError("Sign-in isn't available yet because the backend login endpoint hasn't been built.");
        } else {
          setFormError(error.message);
        }
      } else {
        setFormError("Something unexpected happened. Please try again.");
      }
      setSubmitting(false);
    }
  }

  return (
    <AuthFormLayout
      title="Sign in"
      description="Welcome back. Sign in to manage your customer communication."
      footer={
        <>
          New to the platform?{" "}
          <Link href="/register" className="font-medium text-accent-strong hover:underline">
            Register your business
          </Link>
        </>
      }
    >
      <form onSubmit={onSubmit} noValidate className="space-y-5">
        {showExpired ? (
          <div role="status" className="flex gap-2.5 rounded-lg border border-info/30 bg-info-soft px-3.5 py-3 text-sm text-info">
            <Info aria-hidden="true" className="mt-0.5 size-4 shrink-0" />
            <p>Your session has expired. Please sign in again.</p>
          </div>
        ) : null}
        {formError ? <FormError message={formError} /> : null}

        <Input
          label="Email address"
          type="email"
          name="email"
          autoComplete="email"
          inputMode="email"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          error={fieldErrors.email}
        />
        <div>
          <PasswordInput
            label="Password"
            name="password"
            autoComplete="current-password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            error={fieldErrors.password}
          />
          <div className="mt-2 text-right">
            <Link href="/forgot-password" className="text-sm font-medium text-accent-strong hover:underline">
              Forgot password?
            </Link>
          </div>
        </div>

        <Button type="submit" size="lg" className="w-full" loading={submitting} loadingLabel="Signing in">
          Sign in
        </Button>
      </form>
    </AuthFormLayout>
  );
}
