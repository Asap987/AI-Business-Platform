/**
 * Response shapes the dashboard expects from the backend. These follow the
 * database schema (schema.sql) where it has the data, and are marked where a
 * field must be derived by the backend.
 */

export type ConversationChannel =
  | "whatsapp"
  | "sms"
  | "email"
  | "phone"
  | "web_chat"
  | "other";

export type ConversationStatus = "open" | "waiting" | "closed";

export interface Paginated<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export interface Trend {
  /** Percentage change versus the previous period, e.g. 12.5 or -3. */
  change_pct: number;
  /** Human label for the comparison window, e.g. "vs last 7 days". */
  period_label: string;
}

/** A null value means "no data yet"; the UI must never substitute a number. */
export interface KpiMetric {
  value: number | null;
  trend?: Trend | null;
}

export interface DashboardKpis {
  total_calls: KpiMetric;
  total_sms_conversations: KpiMetric;
  active_cases: KpiMetric;
  pending_department_requests: KpiMetric;
  /** Percentage 0-100. */
  ai_resolution_rate: KpiMetric;
  /** Seconds. */
  average_response_seconds: KpiMetric;
}

export interface ConversationSummary {
  id: string;
  channel: ConversationChannel;
  status: ConversationStatus;
  customer_name: string;
  summary: string | null;
  started_at: string;
}

/**
 * The schema's cases.status has no "waiting for department" state, only
 * waiting_customer. The backend must either add one or define how the
 * "waiting_department" count is derived. See the contract document.
 */
export interface CaseOverview {
  open: number;
  in_progress: number;
  waiting_department: number;
  resolved: number;
}

export interface DepartmentActivityItem {
  id: string;
  name: string;
  open_cases: number;
  pending_requests: number;
}

export type AgentStatusValue = "draft" | "active" | "paused" | "retired";

export interface AgentSummary {
  id: string;
  name: string;
  status: AgentStatusValue;
  /** Derived by the backend from agents.config. */
  channels: ConversationChannel[];
  /** Derived by the backend from the agent's most recent conversation. */
  last_activity_at: string | null;
  /** True when the agent has the settings it needs to run. */
  configured: boolean;
}

export interface NotificationItem {
  id: string;
  title: string;
  body: string | null;
  href: string | null;
  created_at: string;
  read: boolean;
}

export interface NotificationSummary {
  unread_total: number;
  /** Unread customer messages; drives the Communication Center badge. */
  unread_conversations: number;
  items: NotificationItem[];
}
