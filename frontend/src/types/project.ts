export type TaskStatus = "not_started" | "in_progress" | "awaiting_external" | "awaiting_approval" | "testing" | "completed" | "blocked";
export type TaskPriority = "low" | "medium" | "high" | "critical";
export type EvidenceKind = "merged_commit" | "passing_test" | "integration" | "documented_verification";
export type LaunchArea = "security" | "data_isolation" | "voice_quality" | "call_transfers" | "email_delivery" | "monitoring" | "backup";
export type ExternalCategory = "awaiting_us" | "awaiting_provider" | "awaiting_approval" | "completed";
export type FinanceKind = "estimate" | "actual" | "commitment";
export type FinanceCategory = "api" | "telephony" | "email" | "hosting" | "other";

export interface Completion {
  percent: number;
  weight_done: number;
  weight_total: number;
  tasks: number;
  counts: Record<TaskStatus, number>;
}

export interface TestSplit { passed: number; failed: number; skipped: number }

export interface ModuleSummary extends Completion {
  key: string;
  name: string;
  remaining: number;
  status: string;
  depends_on_modules: string[];
  known_issues: string[];
  next_action: string | null;
  last_updated: string | null;
  tests: TestSplit | null;
  thin_test_coverage: boolean;
}

export interface TaskDependency { id: string; title: string; status: TaskStatus }

export interface ProjectTask {
  id: string;
  module: string;
  title: string;
  description: string;
  status: TaskStatus;
  priority: TaskPriority;
  weight: number;
  start_date: string | null;
  deadline: string | null;
  blocker: string;
  notes: string;
  depends_on: TaskDependency[];
  evidence_kind: EvidenceKind | null;
  evidence: string;
  is_launch: boolean;
  launch_area: LaunchArea | null;
  completed_at: string | null;
  updated_at: string;
  overdue: boolean;
}

export interface Milestone {
  id: string;
  name: string;
  phase: string;
  description: string;
  start_date: string | null;
  target_date: string;
  reached_at: string | null;
  overdue: boolean;
}

export interface ExternalItem {
  id: string;
  name: string;
  category: ExternalCategory;
  owner: string;
  detail: string;
  updated_at: string;
}

export interface FinanceRow {
  id: string;
  label: string;
  category: FinanceCategory;
  kind: FinanceKind;
  amount_usd: string;
  period: string;
  state: "" | "outstanding" | "settled";
  note: string;
}

export interface TestRun {
  id: string;
  ran_at: string;
  commit: string;
  source: string;
  total: number;
  passed: number;
  failed: number;
  skipped: number;
  duration_s: number | null;
  coverage_pct: number | null;
  checks: unknown;
  failures: string[];
  age_hours: number;
  stale: boolean;
  matches_head: boolean | null;
}

export interface LaunchItem { area: LaunchArea; total: number; done: number; ready: boolean; has_items: boolean }

export interface ProjectData {
  generated_at: string;
  git_head: string | null;
  overall: Completion;
  modules: ModuleSummary[];
  tasks: ProjectTask[];
  launch: LaunchItem[];
  milestones: Milestone[];
  external: ExternalItem[];
  tests: {
    latest: TestRun | null;
    history: { ran_at: string; commit: string; total: number; passed: number; failed: number; skipped: number }[];
    coverage_note: string | null;
  };
  finance: {
    rows: FinanceRow[];
    totals: Record<FinanceKind, string>;
    api_usage_this_month: { estimated_cost_usd: string; complete: boolean; basis: string };
    note: string;
  };
  recent_tasks: { id: string; title: string; status: TaskStatus; updated_at: string }[];
  git_log: { commit: string; date: string; subject: string }[];
  deployment: { configured: boolean; note: string };
}
