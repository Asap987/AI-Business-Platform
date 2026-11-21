"use client";

import type { ReactNode } from "react";
import { AppShell } from "@/components/layout/AppShell";
import { AuthGuard } from "@/components/layout/AuthGuard";
import { useAuth } from "@/providers/AuthProvider";

/**
 * Re-creates the whole shell whenever the active business changes. The key
 * discards every piece of business-specific client state (loaded lists,
 * notification counts, open menus), so one business's data can't linger on
 * screen after switching to another.
 */
function TenantBoundary({ children }: { children: ReactNode }) {
  const { tenantKey } = useAuth();
  return <AppShell key={tenantKey}>{children}</AppShell>;
}

export function AuthenticatedLayout({ children }: { children: ReactNode }) {
  return (
    <AuthGuard>
      <TenantBoundary>{children}</TenantBoundary>
    </AuthGuard>
  );
}
