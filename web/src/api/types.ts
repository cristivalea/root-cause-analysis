/** The shapes the API sends, as rca/models.py and rca/suggestions.py define them (serialised with
 * model_dump(mode="json"): datetimes are ISO strings). Only the fields the interface reads are typed. */

export type Role = "problem_manager" | "technical_expert";
export const ROLES: readonly Role[] = ["problem_manager", "technical_expert"];

export interface LoginResponse {
  access_token: string;
  token_type: string;
  username: string;
  role: string;
}

export type Severity = "SEV-1" | "SEV-2" | "SEV-3" | "SEV-4";
export type Priority = "P1" | "P2" | "P3" | "P4";
export type ProblemStatus = "Open" | "In investigation" | "Manual" | "Closed";
export const PROBLEM_STATUSES: readonly ProblemStatus[] = ["Open", "In investigation", "Manual", "Closed"];

export type RCAStatus =
  | "DRAFT"
  | "AWAITING_TECHNICAL_REVIEW"
  | "VALIDATED"
  | "REJECTED"
  | "REQUEST_MORE_DETAILS"
  | "ESCALATED_MANUAL"
  | "FAILED";
export const RCA_STATUSES: readonly RCAStatus[] = [
  "DRAFT", "AWAITING_TECHNICAL_REVIEW", "REQUEST_MORE_DETAILS", "VALIDATED", "REJECTED", "FAILED", "ESCALATED_MANUAL",
];
export type RunStatus = "RUNNING" | "COMPLETED" | "FAILED";
export type Confidence = "HIGH" | "MEDIUM" | "LOW";
export type EvidenceType = "INCIDENT" | "LOG" | "CHANGE" | "CMDB" | "HISTORICAL_RCA" | "HISTORICAL_INCIDENT";

export interface Incident {
  incident_id: string;
  title: string;
  description: string;
  severity: Severity;
  status: "Resolved" | "Closed";
  service: string;
  business_service: string;
  environment: string;
  detected_at: string;
  resolved_at: string | null;
  duration_minutes: number | null;
  affected_regions: string[];
  impact: { failed_transactions: number | null; estimated_customers_affected: number | null; error_rate_peak: string | null } | null;
  symptoms: string[];
  initial_mitigation: string | null;
  reported_by: string | null;
  rca_required: boolean;
  rca_reason: string | null;
}

export interface InvestigationGuidance {
  notes: string | null;
  instructions: string | null;
  extra_services: string[];
  change_window_days: number | null;
  log_hours_before: number | null;
}

export interface ProblemLink {
  incident_id: string;
  linked_at: string;
  linked_by: string;
}

export interface Problem {
  problem_id: string;
  title: string;
  description: string;
  status: ProblemStatus;
  priority: Priority;
  services: string[];
  created_at: string;
  created_by: string;
  closed_at: string | null;
  close_reason: string | null;
  rca_id: string | null;
  guidance: InvestigationGuidance | null;
  incidents: ProblemLink[];
}

export type ProblemAction =
  | "created" | "incident_added" | "incident_removed" | "incident_moved_in" | "incident_moved_out"
  | "guide_updated" | "closed" | "reopened" | "manual" | "status_changed" | "rca_status";

export interface ProblemEvent {
  problem_id: string;
  at: string;
  by: string;
  action: ProblemAction;
  incident_id: string | null;
  reason: string | null;
  rca_id: string | null;
  details: Record<string, unknown>;
}

/** The result of every change to a problem: the problem as saved, and the warnings worth a second look. */
export interface ProblemResult {
  problem: Problem;
  warnings: string[];
}

export interface ProblemDetail {
  problem: Problem;
  events: ProblemEvent[];
  rcas: RCARecord[];
}

export interface Candidate {
  incident_id: string;
  title: string;
  service: string;
  severity: Severity;
  detected_at: string;
  similarity: number | null; // cosine similarity of the texts, 0 to 1; not a probability
  closest_incident_id: string | null;
  alike: boolean;
}

export type ProposalKind = "group" | "attach" | "single";

export interface Proposal {
  key: string;
  kind: ProposalKind;
  incident_ids: string[];
  problem_id: string | null;
  score: number | null;
  reasons: string[]; // why it is proposed (written by code)
  evidence: string[]; // the facts behind it (CMDB item, log error types, dates)
  recurrence_of: string | null;
  score_label: string;
  score_meaning: string;
}

export interface Evidence {
  evidence_id: string;
  type: EvidenceType;
  source: string;
  description: string;
  citation: string;
  timestamp: string | null;
  related_ids: string[];
  service: string | null;
}

export interface WhyStep {
  why: string;
  because: string;
  evidence: string[];
}

export type FishboneCategory = "Change / Release" | "Configuration" | "Capacity" | "Dependencies" | "Monitoring" | "Process";

export interface CauseFactor {
  category: FishboneCategory;
  factor: string;
  evidence: string[];
}

export interface Hypothesis {
  hypothesis_id: string;
  candidate_root_cause: string;
  reasons: string[];
  supporting_evidence: string[];
  contradicting_evidence: string[];
  recommended_validation: string[];
  missing_evidence: string[];
  why_chain: WhyStep[];
  factors: CauseFactor[];
  confidence: Confidence;
  confidence_points: number;
  confidence_reasons: string[];
}

export interface InvestigationStep {
  name: string;
  summary: string;
  started_at: string;
  finished_at: string | null;
  details: Record<string, unknown>;
}

export interface ReviewDecision {
  reviewer: string;
  decision: "APPROVE" | "REJECT" | "REQUEST_MORE_DETAILS";
  hypothesis_id: string | null;
  comment: string;
  decided_at: string;
  requested_checks: string[];
  guidance: InvestigationGuidance | null;
}

export interface TimelineEntry {
  at: string;
  evidence_id: string;
  type: EvidenceType;
  citation: string;
  what: string;
  marker: string | null;
}

export interface InvestigationContext {
  problem_id: string | null;
  incident_ids: string[];
  reference_incident_id: string;
  services: string[];
  related_services: string[];
  title: string | null;
  notes: string | null;
  instructions: string | null;
  expert_request: string | null;
  previous_conclusions: string[];
  guidance: InvestigationGuidance | null;
}

export interface InvestigationPlan {
  service: string;
  related_services: string[];
  window_start: string;
  window_end: string;
  sources: string[];
  search_queries: string[];
  rationale: string;
}

/** One revision of an RCA (RCA-2026-00001-R2): one run of the investigation. */
export interface RCARecord {
  rca_id: string;
  revision: number;
  previous_revision_id: string | null;
  run_status: RunStatus;
  error: string | null;
  incident_id: string;
  status: RCAStatus;
  owner: string;
  created_at: string;
  completed_at: string | null;
  duration_seconds: number | null;
  linked_incidents: string[];
  problem_id: string | null;
  guidance: InvestigationGuidance | null;
  current_step: string | null;
  context: InvestigationContext | null;
  plan: InvestigationPlan | null;
  evidence: Evidence[];
  timeline: TimelineEntry[];
  trace: InvestigationStep[];
  investigation_summary: string;
  observed_patterns: string[];
  hypotheses: Hypothesis[];
  single_hypothesis_reason: string | null;
  not_checked: string[];
  weakly_supported: boolean;
  suggested_workaround: string | null;
  change_likely_required: boolean;
  review: ReviewDecision | null;
  final_root_cause: string | null;
  review_rounds: number;
}

/** An RCA of a problem, with its counters (models.RCA). */
export interface RCASummary {
  rca_id: string;
  problem_id: string;
  title: string;
  status: RCAStatus;
  created_at: string;
  created_by: string;
  updated_at: string;
  revisions: number;
  review_rounds: number;
  sent_to_expert: boolean;
  latest_revision_id: string | null;
}

export interface RCAStatusChange {
  rca_id: string;
  revision_id: string | null;
  from_status: RCAStatus | null;
  to_status: RCAStatus;
  by: string;
  at: string;
  comment: string | null;
  decision: ReviewDecision | null;
  details: Record<string, unknown>;
}

export const revisionId = (record: Pick<RCARecord, "rca_id" | "revision">) => `${record.rca_id}-R${record.revision}`;

/** GET /rcas/{id}/diagram: the diagram rca/diagram.py chose for the hypotheses of a revision. */
export interface DiagramData {
  kind: "five_whys" | "fishbone";
  hypothesis_id: string | null;
  steps: WhyStep[];
  factors: (CauseFactor & { hypothesis_id: string })[];
}

/** GET /rcas/{id}/comparison: what changed since the previous revision with an analysis (rca/compare.py). */
export interface Comparison {
  previous_id: string;
  previous_revision: number;
  current_id: string;
  request: string | null;
  new_evidence: string[];
  dropped_evidence: string[];
  main_changed: boolean;
  newly_not_checked: string[];
  hypotheses: {
    kind: "kept" | "new" | "dropped";
    current: { hypothesis_id: string; confidence: Confidence; candidate_root_cause: string } | null;
    previous: { hypothesis_id: string; confidence: Confidence; candidate_root_cause: string } | null;
    similarity: number | null;
  }[];
}

/** GET /kpis (rca/kpis.py): the live KPIs of the RCAs started in a period, and the benchmark reports. */
export interface KpiBenchmark {
  status: "measured" | "not_measured" | "outdated";
  timestamp: string | null;
  agent_model: string | null;
  judge_model: string | null;
  selected: number | null;
  evaluated: number | null;
  values: Record<string, number | null>;
  excluded: string[];
}

export interface KpiReport {
  period: { from: string | null; to: string | null };
  overview: {
    problems: Record<ProblemStatus, number>;
    awaiting_review: number;
    rcas_started: number;
    rcas_running: number;
    problems_closed: number;
    median_hours_to_decision: number | null;
    decided_count: number;
  };
  kpi1_interactions: {
    finished: number; average_interactions: number | null; reduction_percent: number | null; happy_path: number;
    with_more_steps: number; manual_interactions: number; design_interactions: number; design_reduction_percent: number;
  };
  kpi2_autonomy: {
    runs: number; autonomous: number; failed: number; refused_by_checks: number; rate_percent: number | null;
    design_automated: number; design_stages: number; design_percent: number;
  };
  kpi3_accuracy: { decided: number; top1: number; topk: number; top1_percent: number | null; topk_percent: number | null };
  kpi4_calibration: {
    decisions: number;
    levels: { level: Confidence; decisions: number; approved: number; approved_percent: number | null }[];
    ordered: boolean | null;
  };
  weeks: { week: string; started: number; validated: number; rejected: number }[];
  benchmark: { accuracy: KpiBenchmark; calibration: KpiBenchmark };
}
