"use client";

import Link from "next/link";
import { useState, type FormEvent } from "react";
import { AuthFormLayout } from "@/features/auth/AuthFormLayout";
import {
  hasErrors,
  MIN_PASSWORD_LENGTH,
  validateEmail,
  validateNewPassword,
  validatePasswordConfirmation,
  validateRequired,
} from "@/features/auth/validation";
import { Button } from "@/components/ui/Button";
import { FormError } from "@/components/ui/ErrorMessage";
import { Input, PasswordInput } from "@/components/ui/Input";
import { ApiError } from "@/lib/api";
import { useAuth } from "@/providers/AuthProvider";

type FieldName = "business_name" | "full_name" | "email" | "password" | "confirm";
type FieldErrors = Partial<Record<FieldName, string>>;

/**
 * Creates a business and its first administrator. Only the fields the
 * database can store are collected: the schema has no phone column on
 * businesses or users, so no phone field is shown or sent.
 */
export function RegisterForm() {
  const { register } = useAuth();

  const [businessName, setBusinessName] = useState("");
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFormError(null);

    const errors: FieldErrors = {
      business_name: validateRequired(businessName, "Enter your business name."),
      full_name: validateRequired(fullName, "Enter your full name."),
      email: validateEmail(email),
      password: validateNewPassword(password),
      confirm: validatePasswordConfirmation(password, confirm),
    };
    setFieldErrors(errors);
    if (hasErrors(errors)) return;

    setSubmitting(true);
    try {
      // On success the guard around this page redirects into the app.
      await register({
        business_name: businessName.trim(),
        full_name: fullName.trim(),
        email: email.trim(),
        password,
      });
    } catch (error) {
      if (error instanceof ApiError) {
        if (error.kind === "validation") {
          const mapped: FieldErrors = {
            business_name: error.fieldErrors.business_name,
            full_name: error.fieldErrors.full_name,
            email: error.fieldErrors.email,
            password: error.fieldErrors.password,
          };
          setFieldErrors(mapped);
          if (!hasErrors(mapped)) setFormError(error.message);
        } else if (error.status === 409) {
          setFieldErrors({ email: "An account with this email already exists. Try signing in instead." });
        } else if (error.kind === "not_found") {
          setFormError("Registration isn't available yet because the backend registration endpoint hasn't been built.");
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
      title="Register your business"
      description="Create your business account. You'll be its first administrator."
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

        <Input
          label="Business name"
          name="business_name"
          autoComplete="organization"
          value={businessName}
          onChange={(event) => setBusinessName(event.target.value)}
          error={fieldErrors.business_name}
        />
        <Input
          label="Your full name"
          name="full_name"
          autoComplete="name"
          value={fullName}
          onChange={(event) => setFullName(event.target.value)}
          error={fieldErrors.full_name}
        />
        <Input
          label="Work email address"
          type="email"
          name="email"
          autoComplete="email"
          inputMode="email"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          error={fieldErrors.email}
        />
        <PasswordInput
          label="Password"
          name="password"
          autoComplete="new-password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          hint={`At least ${MIN_PASSWORD_LENGTH} characters.`}
          error={fieldErrors.password}
        />
        <PasswordInput
          label="Confirm password"
          name="confirm_password"
          autoComplete="new-password"
          value={confirm}
          onChange={(event) => setConfirm(event.target.value)}
          error={fieldErrors.confirm}
        />

        <Button type="submit" size="lg" className="w-full" loading={submitting} loadingLabel="Creating account">
          Create account
        </Button>
      </form>
    </AuthFormLayout>
  );
}
