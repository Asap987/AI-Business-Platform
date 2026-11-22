"use client";

import { useApiResource } from "@/hooks/useApiResource";

/** True only when the server says this user is a platform administrator. Menu convenience only: the API enforces it. */
export function usePlatformAccess(): boolean {
  const resource = useApiResource<{ platform_admin: boolean }>("/platform/access");
  return resource.data?.platform_admin === true;
}
