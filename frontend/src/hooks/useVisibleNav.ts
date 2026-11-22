"use client";

import { useMemo } from "react";
import { usePlatformAccess } from "@/hooks/usePlatformAccess";
import { NAV_GROUPS, PLATFORM_GROUP, type NavGroup } from "@/lib/constants";
import { filterNavGroups } from "@/lib/nav-access";
import { can } from "@/lib/utils";
import { useAuth } from "@/providers/AuthProvider";

/** The navigation the signed-in role may see. */
export function useVisibleNav(): NavGroup[] {
  const { user } = useAuth();
  const permissions = user?.role.permissions;
  const platformAdmin = usePlatformAccess();
  return useMemo(() => {
    const groups = filterNavGroups(NAV_GROUPS, (needed) => can(permissions, needed));
    return platformAdmin ? [...groups, PLATFORM_GROUP] : groups;
  }, [permissions, platformAdmin]);
}
