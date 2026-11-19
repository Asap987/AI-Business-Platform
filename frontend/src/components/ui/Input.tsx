"use client";

import { Eye, EyeOff, Search, X } from "lucide-react";
import { useId, useState, type InputHTMLAttributes, type ReactNode } from "react";
import { cn } from "@/lib/utils";

const FIELD_BASE =
  "block w-full rounded-lg border bg-surface px-3 text-sm text-ink placeholder:text-muted " +
  "transition-colors disabled:cursor-not-allowed disabled:bg-surface-muted";

interface FieldShellProps {
  id: string;
  label: string;
  hint?: string;
  error?: string;
  hideLabel?: boolean;
  children: ReactNode;
}

/** Label + control + hint/error, wired together for screen readers. */
function FieldShell({ id, label, hint, error, hideLabel, children }: FieldShellProps) {
  return (
    <div>
      <label htmlFor={id} className={cn("mb-1.5 block text-sm font-medium text-ink", hideLabel && "sr-only")}>
        {label}
      </label>
      {children}
      {error ? (
        <p id={`${id}-error`} role="alert" className="mt-1.5 text-sm text-danger">
          {error}
        </p>
      ) : hint ? (
        <p id={`${id}-hint`} className="mt-1.5 text-sm text-muted">
          {hint}
        </p>
      ) : null}
    </div>
  );
}

function describedBy(id: string, error?: string, hint?: string): string | undefined {
  if (error) return `${id}-error`;
  if (hint) return `${id}-hint`;
  return undefined;
}

export interface InputProps extends Omit<InputHTMLAttributes<HTMLInputElement>, "id"> {
  label: string;
  hint?: string;
  error?: string;
  hideLabel?: boolean;
  id?: string;
}

export function Input({ label, hint, error, hideLabel, id, className, ...rest }: InputProps) {
  const generated = useId();
  const inputId = id ?? generated;
  return (
    <FieldShell id={inputId} label={label} hint={hint} error={error} hideLabel={hideLabel}>
      <input
        id={inputId}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy(inputId, error, hint)}
        className={cn(FIELD_BASE, "h-10", error ? "border-danger" : "border-border-strong", className)}
        {...rest}
      />
    </FieldShell>
  );
}

export function PasswordInput({ label, hint, error, hideLabel, id, className, ...rest }: InputProps) {
  const generated = useId();
  const inputId = id ?? generated;
  const [visible, setVisible] = useState(false);

  return (
    <FieldShell id={inputId} label={label} hint={hint} error={error} hideLabel={hideLabel}>
      <div className="relative">
        <input
          id={inputId}
          type={visible ? "text" : "password"}
          aria-invalid={error ? true : undefined}
          aria-describedby={describedBy(inputId, error, hint)}
          className={cn(FIELD_BASE, "h-10 pr-11", error ? "border-danger" : "border-border-strong", className)}
          {...rest}
        />
        <button
          type="button"
          onClick={() => setVisible((v) => !v)}
          aria-pressed={visible}
          aria-label={visible ? "Hide password" : "Show password"}
          className="absolute inset-y-0 right-0 flex w-10 items-center justify-center rounded-r-lg text-muted hover:text-ink"
        >
          {visible ? <EyeOff aria-hidden="true" className="size-4" /> : <Eye aria-hidden="true" className="size-4" />}
        </button>
      </div>
    </FieldShell>
  );
}

interface SearchInputProps extends Omit<InputHTMLAttributes<HTMLInputElement>, "id" | "type" | "value" | "onChange"> {
  label: string;
  value: string;
  onValueChange: (value: string) => void;
  id?: string;
}

export function SearchInput({ label, value, onValueChange, id, className, ...rest }: SearchInputProps) {
  const generated = useId();
  const inputId = id ?? generated;
  return (
    <div className="relative">
      <label htmlFor={inputId} className="sr-only">
        {label}
      </label>
      <Search aria-hidden="true" className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted" />
      <input
        id={inputId}
        type="search"
        value={value}
        onChange={(event) => onValueChange(event.target.value)}
        className={cn(FIELD_BASE, "h-10 border-border-strong pl-9 pr-9 [&::-webkit-search-cancel-button]:hidden", className)}
        {...rest}
      />
      {value ? (
        <button
          type="button"
          onClick={() => onValueChange("")}
          aria-label="Clear search"
          className="absolute inset-y-0 right-0 flex w-9 items-center justify-center rounded-r-lg text-muted hover:text-ink"
        >
          <X aria-hidden="true" className="size-4" />
        </button>
      ) : null}
    </div>
  );
}
