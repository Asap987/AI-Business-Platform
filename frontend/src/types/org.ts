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
  created_at: string;
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
