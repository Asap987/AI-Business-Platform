"use client";

import { useApiResource } from "@/hooks/useApiResource";
import type {
  AgentSummary,
  CaseOverview,
  ConversationSummary,
  DashboardKpis,
  DepartmentActivityItem,
  Paginated,
} from "@/types/api";

/**
 * Dashboard data hooks. Every endpoint here is part of the contract in
 * documentation/frontend-api-contract.md; none exist in the backend yet, so
 * today each section shows its "not available" state rather than fake data.
 */
export const DASHBOARD_ENDPOINTS = {
  kpis: "/dashboard/kpis",
  caseOverview: "/dashboard/case-overview",
  departmentActivity: "/dashboard/department-activity",
  conversations: "/conversations",
  agents: "/agents",
} as const;

export function useDashboardKpis() {
  return useApiResource<DashboardKpis>(DASHBOARD_ENDPOINTS.kpis);
}

export function useCaseOverview() {
  return useApiResource<CaseOverview>(DASHBOARD_ENDPOINTS.caseOverview);
}

export function useDepartmentActivity() {
  return useApiResource<Paginated<DepartmentActivityItem>>(DASHBOARD_ENDPOINTS.departmentActivity);
}

export function useRecentConversations() {
  return useApiResource<Paginated<ConversationSummary>>(DASHBOARD_ENDPOINTS.conversations, {
    page_size: 20,
    sort: "-started_at",
  });
}

export function useAgents() {
  return useApiResource<Paginated<AgentSummary>>(DASHBOARD_ENDPOINTS.agents, { page_size: 10 });
}
