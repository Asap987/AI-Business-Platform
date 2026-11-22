"use client";

import { useMemo } from "react";
import { NAV_GROUPS, type NavGroup } from "@/lib/constants";
import { filterNavGroups } from "@/lib/nav-access";
import { can } from "@/lib/utils";
import { useAuth } from "@/providers/AuthProvider";

/** The navigation the signed-in role may see. */
export function useVisibleNav(): NavGroup[] {
  const { user } = useAuth();
  const permissions = user?.role.permissions;
  return useMemo(() => filterNavGroups(NAV_GROUPS, (needed) => can(permissions, needed)), [permissions]);
}
