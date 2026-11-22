"use client";

import { useId, type SelectHTMLAttributes, type TextareaHTMLAttributes } from "react";
import { FIELD_BASE, FieldShell, describedBy } from "@/components/ui/Input";
import { cn } from "@/lib/utils";

interface SharedProps {
  label: string;
  hint?: string;
  error?: string;
  hideLabel?: boolean;
  id?: string;
}

export function Select({
  label, hint, error, hideLabel, id, className, children, ...rest
}: SharedProps & Omit<SelectHTMLAttributes<HTMLSelectElement>, "id">) {
  const generated = useId();
  const selectId = id ?? generated;
  return (
    <FieldShell id={selectId} label={label} hint={hint} error={error} hideLabel={hideLabel}>
      <select
        id={selectId}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy(selectId, error, hint)}
        className={cn(FIELD_BASE, "h-10", error ? "border-danger" : "border-border-strong", className)}
        {...rest}
      >
        {children}
      </select>
    </FieldShell>
  );
}

export function Textarea({
  label, hint, error, hideLabel, id, className, rows = 4, ...rest
}: SharedProps & Omit<TextareaHTMLAttributes<HTMLTextAreaElement>, "id">) {
  const generated = useId();
  const areaId = id ?? generated;
  return (
    <FieldShell id={areaId} label={label} hint={hint} error={error} hideLabel={hideLabel}>
      <textarea
        id={areaId}
        rows={rows}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy(areaId, error, hint)}
        className={cn(FIELD_BASE, "py-2", error ? "border-danger" : "border-border-strong", className)}
        {...rest}
      />
    </FieldShell>
  );
}
