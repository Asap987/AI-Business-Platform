"use client";

import { useAuth } from "@/providers/AuthProvider";
import { can } from "@/lib/utils";

/** True when the signed-in role may do `needed`, e.g. usePermission("cases:write"). */
export function usePermission(needed: string): boolean {
  const { user } = useAuth();
  return can(user?.role.permissions, needed);
}
