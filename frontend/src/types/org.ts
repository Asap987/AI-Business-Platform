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
