/** Response shapes for customers, cases, departments and employees (see documentation/frontend-api-contract.md). */

export type CaseStatus = "open" | "in_progress" | "waiting_customer" | "waiting_department" | "resolved" | "closed";
export type CasePriority = "low" | "medium" | "high" | "urgent";
export type EmployeeStatus = "active" | "on_leave" | "inactive";

export interface Customer {
  id: string;
  full_name: string;
  email: string | null;
  phone: string | null;
  external_ref: string | null;
  created_at: string;
}

export interface CaseItem {
  id: string;
  customer_id: string;
  /** Present in list and detail responses, null right after creating. */
  customer_name: string | null;
  title: string;
  description: string | null;
  priority: CasePriority;
  status: CaseStatus;
  department_id: string | null;
  assigned_employee_id: string | null;
  conversation_id: string | null;
  resolution_notes: string | null;
  opened_at: string;
  resolved_at: string | null;
  updated_at: string;
}

export interface CaseEvent {
  id: string;
  kind: string;
  actor_kind: "user" | "ai" | "system";
  actor_user_id: string | null;
  detail: Record<string, unknown>;
  created_at: string;
}

export interface Department {
  id: string;
  name: string;
  description: string | null;
  employee_count?: number;
  open_cases?: number;
  created_at: string;
  /** null = always open; otherwise day key (mon..sun) -> ["HH:MM","HH:MM"] ranges. A missing day is closed. */
  hours: Record<string, string[][]> | null;
  timezone: string | null;
  fallback_department_id: string | null;
  accepts_transfers: boolean;
}

export interface Employee {
  id: string;
  full_name: string;
  email: string | null;
  phone: string | null;
  job_title: string | null;
  department_id: string | null;
  status: EmployeeStatus;
  has_login: boolean;
  extension: string | null;
  available: boolean;
  routing_priority: number;
  created_at: string;
}

export type CallbackStatus = "pending" | "contacted" | "done" | "cancelled";

export interface CallbackRequest {
  id: string;
  department_id: string | null;
  customer_id: string | null;
  caller_name: string | null;
  phone: string;
  reason: string;
  preferred_time: string | null;
  context: { intent?: string; summary?: string; collected?: Record<string, string>; done?: string[]; open_questions?: string[] };
  source: "ai" | "staff";
  status: CallbackStatus;
  note: string | null;
  created_at: string;
  updated_at: string;
}

export interface TeamRole {
  id: string;
  name: string;
  description: string | null;
  permissions: string[];
}

export interface TeamUser {
  id: string;
  email: string;
  full_name: string;
  status: "active" | "invited" | "disabled";
  role: { id: string; name: string };
  last_login_at: string | null;
  created_at: string;
  has_employee_profile: boolean;
}

export interface TeamInvite {
  id: string;
  email: string;
  role: { id: string; name: string };
  created_at: string;
  expires_at: string;
  expired: boolean;
}

export interface CreatedInvite {
  id: string;
  email: string;
  token: string;
  expires_at: string;
  /** True when the invitation email was sent; false means the administrator must share the link by hand. */
  email_sent: boolean;
}

export interface KnowledgeDoc {
  id: string;
  title: string;
  category: string | null;
  status: "published" | "archived";
  characters: number;
  created_at: string;
  updated_at: string;
  /** Only on single-document responses. */
  content?: string;
  chunks?: number;
}

export interface KnowledgeHit {
  document_id: string;
  title: string;
  category: string | null;
  text: string;
  score: number;
}

export interface PrivacySettings {
  ai_providers_enabled: boolean;
  redact_contact_details: boolean;
  redact_secrets: boolean;
  updated_at: string | null;
}

export interface AuditEntry {
  id: string;
  action: string;
  actor_name: string | null;
  detail: Record<string, unknown>;
  created_at: string;
}

export interface UsageTotals {
  calls: number;
  stt_seconds: number;
  tts_characters: number;
  llm_requests: number;
  failed_requests: number;
  retries: number;
  turns: number;
  latency_avg_ms: number | null;
  latency_max_ms: number | null;
  /** An ESTIMATE from price records, not a provider invoice. US dollars as a decimal string. */
  estimated_cost_usd: string;
  cost_complete: boolean;
  calls_missing_prices: number;
}

export interface UsageSummary {
  cost_basis: "estimate";
  start: string;
  end: string;
  total: UsageTotals;
  by_day: Array<UsageTotals & { date: string }>;
  by_month: Array<UsageTotals & { month: string }>;
  by_model: Array<{ model: string; calls: number; input_tokens: number; output_tokens: number }>;
}

export interface UsageCall {
  id: string;
  source: string;
  ended_at: string;
  stt_seconds: number;
  tts_characters: number;
  llm_requests: number;
  failed_requests: number;
  retries: number;
  turns: number;
  latency_avg_ms: number | null;
  estimated_cost_usd: string;
  cost_complete: boolean;
  missing_rates: string[];
}

export interface BusinessBranch { name: string; address: string | null; phone: string | null }
export interface BusinessPolicy { title: string; text: string }
export type ServiceTone = "friendly" | "professional" | "formal";
export interface BusinessProfile {
  name: string;
  industry: string | null;
  country: string | null;
  timezone: string;
  description: string | null;
  contact_phone: string | null;
  contact_email: string | null;
  website: string | null;
  address: string | null;
  branches: BusinessBranch[];
  hours: Record<string, string[][]> | null;
  policies: BusinessPolicy[];
  languages: string[];
  preferences: { greeting?: string; tone?: ServiceTone; after_hours_message?: string; escalation_note?: string };
}
