"use client";

import { useApiResource } from "@/hooks/useApiResource";
import type { NotificationSummary } from "@/types/api";

/**
 * Single integration point for notifications. When the backend endpoint
 * doesn't exist yet this resolves to a "not available" error, which the bell
 * menu shows honestly instead of inventing counts.
 */
export const NOTIFICATIONS_ENDPOINT = "/notifications/summary";

export function useNotifications() {
  return useApiResource<NotificationSummary>(NOTIFICATIONS_ENDPOINT);
}
