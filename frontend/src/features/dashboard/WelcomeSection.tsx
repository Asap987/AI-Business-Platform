"use client";

import { formatLongDate } from "@/lib/utils";
import { useAuth } from "@/providers/AuthProvider";

export function WelcomeSection() {
  const { user, business } = useAuth();
  const firstName = user?.full_name.trim().split(/\s+/)[0];

  return (
    <header className="mb-6">
      <p className="text-sm text-muted">
        {business?.name ? <span className="font-medium text-secondary">{business.name}</span> : null}
        {business?.name ? " · " : null}
        <time dateTime={new Date().toISOString()}>{formatLongDate()}</time>
      </p>
      <h1 className="mt-1 text-2xl font-semibold tracking-tight text-ink">
        {firstName ? `Welcome back, ${firstName}` : "Welcome back"}
      </h1>
      <p className="mt-1 max-w-2xl text-sm text-muted">
        A live view of your customer calls and messages, open cases, departments and AI agents.
      </p>
    </header>
  );
}
