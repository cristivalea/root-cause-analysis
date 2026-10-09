"""All data models of the application.

Two groups:
- Source data: the mock systems the investigation reads (docs/05-data-and-rag.md).
- Application data: what the agents propose and what the application stores
  (docs/06-reasoning-and-execution.md).

The models only check the shape of the data. The rules about content (citations that
exist, at least two hypotheses, confidence) live in the guardrail and confidence modules.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

# --------------------------------------------------------------------------------------
# Source data
# --------------------------------------------------------------------------------------

Environment = Literal["production", "test"]
Criticality = Literal["high", "medium", "low"]


class SourceRecord(BaseModel):
    """Base for the mock source data. Unknown fields are refused, so a record can never
    carry extra information by mistake, for example the root cause inside an incident."""

    model_config = ConfigDict(extra="forbid")


class IncidentImpact(SourceRecord):
    failed_transactions: int | None = None
    estimated_customers_affected: int | None = None
    error_rate_peak: str | None = None


class Incident(SourceRecord):
    """An incident: the one that starts the investigation, or a past one used for comparison.
    It holds symptoms and context only, never the answer."""

    incident_id: str = Field(pattern=r"^INC-\d{4}-\d{5}$")
    title: str
    description: str
    severity: Literal["SEV-1", "SEV-2", "SEV-3", "SEV-4"]
    status: Literal["Resolved", "Closed"]
    service: str
    business_service: str
    environment: Environment
    detected_at: datetime
    resolved_at: datetime | None = None
    duration_minutes: int | None = None
    affected_regions: list[str] = []
    impact: IncidentImpact | None = None
    symptoms: list[str]
    initial_mitigation: str | None = None
    reported_by: str | None = None
    ci_id: str | None = None  # the CMDB item where the symptoms were seen
    assignment_group: str | None = None  # the team that owned the ticket
    reassignment_count: int = 0  # how many times the ticket moved between teams
    reopen_count: int = 0
    rca_required: bool
    rca_reason: str | None = None


class IncidentEvent(SourceRecord):
    """One step in the life of an incident ticket: opened, assigned, on hold, resolved, closed.
    The events give the Timeline of the incident."""

    event_id: str = Field(pattern=r"^EVT-\d{4}-\d{5}-\d{2}$")
    incident_id: str = Field(pattern=r"^INC-\d{4}-\d{5}$")
    timestamp: datetime
    action: Literal[
        "opened", "assigned", "reassigned", "awaiting_caller", "awaiting_vendor", "resumed",
        "workaround", "resolved", "reopened", "closed",
    ]
    state: Literal["New", "In Progress", "On Hold", "Resolved", "Closed"]
    assignment_group: str
    note: str | None = None


class ConfigItem(SourceRecord):
    """A CMDB configuration item."""

    ci_id: str = Field(pattern=r"^CI-[A-Z0-9-]+$")
    name: str
    type: Literal["application", "database", "queue", "gateway", "host", "cache", "storage"]
    service: str  # the technical service this component belongs to, used by the CMDB lookup
    environment: Environment
    owner_team: str
    criticality: Criticality


class CIRelationship(SourceRecord):
    """A dependency between two configuration items: source_ci depends on target_ci."""

    source_ci: str
    target_ci: str
    relationship_type: Literal["depends_on", "hosted_on", "connects_to"]


class Change(SourceRecord):
    """A change or deployment."""

    change_id: str = Field(pattern=r"^CHG-\d{4}-\d{5}$")
    title: str
    description: str | None = None
    type: Literal["standard", "normal", "emergency"]
    service: str
    ci_id: str
    version: str | None = None
    implemented_at: datetime
    implemented_by: str
    risk: Criticality
    rollback: bool


class LogEntry(SourceRecord):
    """One log line."""

    log_id: str = Field(pattern=r"^LOG-[A-Z0-9]+-\d{8}-\d+$")
    timestamp: datetime
    service: str
    host: str
    level: Literal["ERROR", "WARN", "INFO"]
    message: str
    error_type: str | None = None


class ProblemLink(SourceRecord):
    """An incident attached to a problem: who attached it and when."""

    incident_id: str = Field(pattern=r"^INC-\d{4}-\d{5}$")
    linked_at: datetime
    linked_by: str


class Problem(SourceRecord):
    """A problem (ITIL): the unknown cause behind one or more incidents. The RCA starts from it.
    An incident belongs to one problem at most. Like an incident, it never holds the answer."""

    problem_id: str = Field(pattern=r"^PRB-\d{4}-\d{5}$")
    title: str
    description: str
    # Manual: the application stopped (two rejected cases, or a case past its last revision) and
    # people solve it outside; it is closed with a reason once they have.
    status: Literal["Open", "Closed", "Manual"]
    priority: Literal["P1", "P2", "P3", "P4"]  # from the most severe incident: SEV-1 is P1
    services: list[str] = Field(min_length=1)
    created_at: datetime
    created_by: str
    closed_at: datetime | None = None
    close_reason: str | None = None  # why the Problem Manager closed it, when no RCA did
    rca_id: str | None = None  # the past RCA that closed the problem
    incidents: list[ProblemLink] = Field(min_length=1)


class ProblemEvent(BaseModel):
    """One change to a problem, kept forever: who did what, when and why (rca/problems.py)."""

    problem_id: str
    at: datetime
    by: str
    action: Literal["created", "incident_added", "incident_removed", "incident_moved_in", "incident_moved_out",
                    "closed", "reopened", "manual"]
    incident_id: str | None = None
    reason: str | None = None


# --------------------------------------------------------------------------------------
# Tool results
# --------------------------------------------------------------------------------------


class Dependency(BaseModel):
    """One direct dependency: a component of the service depends on another component."""

    component: ConfigItem
    depends_on: ConfigItem
    relationship_type: Literal["depends_on", "hosted_on", "connects_to"]


class ServiceDependencies(BaseModel):
    """Result of the CMDB lookup: the components of a service and what they depend on."""

    service: str
    components: list[ConfigItem]
    dependencies: list[Dependency]

    @property
    def related_services(self) -> list[str]:
        """Other services this service depends on, for the change lookup."""
        return sorted({item.depends_on.service for item in self.dependencies} - {self.service})


class LogGroup(BaseModel):
    """Result of the log lookup: log lines of one level and error type, summarised."""

    service: str
    level: Literal["ERROR", "WARN", "INFO"]
    error_type: str | None
    count: int
    first_seen: datetime
    last_seen: datetime
    hosts: list[str]
    examples: list[LogEntry]  # the first few lines, kept as citations
    log_ids: list[str] = []  # every line of the group


# --------------------------------------------------------------------------------------
# Application data
# --------------------------------------------------------------------------------------

# INCIDENT: the incident being investigated, with its symptoms. It is what must be explained, so it
# earns no confidence points (rca/confidence.py).
EvidenceType = Literal["INCIDENT", "LOG", "CHANGE", "CMDB", "HISTORICAL_RCA", "HISTORICAL_INCIDENT"]
SourceName = Literal["logs", "changes", "cmdb", "historical_rcas", "historical_incidents"]
ConfidenceLevel = Literal["HIGH", "MEDIUM", "LOW"]
# The states an RCA goes through.
# DRAFT: investigation finished, but the Problem Manager has not sent it to the expert yet.
# MORE_DETAILS_REQUESTED: the Technical Expert asked for a further investigation of this case.
# ESCALATED: the agents could not produce a valid plan or draft (a technical failure).
# ESCALATED_MANUAL: the expert still asked for more after the last allowed revision of the case;
# the case is now solved by people, outside the application.
RCAStatus = Literal[
    "INVESTIGATING",
    "DRAFT",
    "PENDING_REVIEW",
    "MORE_DETAILS_REQUESTED",
    "ESCALATED",
    "ESCALATED_MANUAL",
    "REJECTED",
    "FINAL",
]


class Evidence(BaseModel):
    """One fact found during the investigation. Hypotheses may cite only these ids."""

    evidence_id: str = Field(pattern=r"^EV-\d{3}$")
    type: EvidenceType
    source: str
    description: str
    citation: str  # id of the original record, for example CHG-2026-00871
    timestamp: datetime | None = None
    related_ids: list[str] = []  # the other records the evidence stands for: every line of a log group
    service: str | None = None  # the service of a log line: one of the problem, or a dependency


class TimeWindow(BaseModel):
    start: datetime
    end: datetime
    incident_id: str | None = None  # the incident the window is built around, when there is one


class InvestigationGuidance(BaseModel):
    """What the Problem Manager may add when starting an investigation. Optional; checked by code
    (rca/context.py) and recorded in the context with the source "Problem Manager"."""

    notes: str | None = None  # read by the Investigation Planner
    extra_services: list[str] = []  # also searched for logs and changes; must exist in the CMDB
    change_window_days: int | None = Field(default=None, ge=7, le=90)  # instead of 7 days before the first incident
    log_hours_before: int | None = Field(default=None, ge=2, le=168)  # instead of 2 hours before each detection


class InvestigationContext(BaseModel):
    """What the investigation starts from, built by code from the problem and its incidents, never
    guessed by a model (rca/context.py). `sources` says where every value comes from."""

    problem_id: str | None = None  # None: the incident belongs to no problem yet
    incident_ids: list[str] = Field(min_length=1)  # in the order they happened
    reference_incident_id: str  # the most recent incident of the problem
    services: list[str] = Field(min_length=1)
    related_services: list[str] = []
    log_windows: list[TimeWindow] = Field(min_length=1)  # one around every incident
    change_window: TimeWindow
    notes: str | None = None  # from the Problem Manager
    expert_request: str | None = None  # what the Technical Expert asked for in the review of the previous revision
    guidance: InvestigationGuidance | None = None  # the guidance used, kept for the next revision of the case
    sources: dict[str, str] = {}


class TimelineEntry(BaseModel):
    """One fact of the ledger on the time axis of the investigation (rca/timeline.py)."""

    at: datetime
    evidence_id: str
    type: EvidenceType
    citation: str
    what: str
    marker: str | None = None  # "incident detected", "first error", "before/after the first error"


class InvestigationPlan(BaseModel):
    """Answer of the Investigation Planner: what to look for, where and when."""

    service: str
    related_services: list[str] = []
    window_start: datetime
    window_end: datetime
    sources: list[SourceName]
    search_queries: list[str]
    rationale: str

    @model_validator(mode="after")
    def window_must_be_ordered(self):
        if self.window_start >= self.window_end:
            raise ValueError("window_start must be before window_end")
        return self


FishboneCategory = Literal["Change / Release", "Configuration", "Capacity", "Dependencies", "Monitoring", "Process"]


class WhyStep(BaseModel):
    """One step of a 5 Whys chain, from the symptom down to the candidate cause."""

    why: str
    because: str
    evidence: list[str] = []  # evidence ids; a step without evidence is an open question


class CauseFactor(BaseModel):
    """One contributing factor of a fishbone diagram."""

    category: FishboneCategory
    factor: str
    evidence: list[str] = []  # evidence ids


class Hypothesis(BaseModel):
    """A candidate root cause proposed by the RCA Reasoning Agent. No confidence on purpose:
    the model writes the reasons, the code calculates the level."""

    hypothesis_id: str = Field(pattern=r"^HYP-\d{3}$")
    candidate_root_cause: str
    reasons: list[str]
    supporting_evidence: list[str]  # evidence ids only
    contradicting_evidence: list[str]  # evidence ids only
    recommended_validation: list[str]
    missing_evidence: list[str] = []  # what would confirm or rule it out but is not in the ledger
    why_chain: list[WhyStep] = Field(default=[], max_length=5)  # for the 5 Whys diagram (rca/diagram.py)
    factors: list[CauseFactor] = []  # for the fishbone diagram


class DraftRCA(BaseModel):
    """Answer of the RCA Reasoning Agent."""

    incident_id: str
    investigation_summary: str
    observed_patterns: list[str]
    hypotheses: list[Hypothesis]
    single_hypothesis_reason: str | None = None  # required by the guardrail when there is one hypothesis
    not_checked: list[str]
    suggested_workaround: str | None
    change_likely_required: bool


class AssessedHypothesis(Hypothesis):
    """A hypothesis after the confidence rules were applied."""

    confidence: ConfidenceLevel
    confidence_points: int
    confidence_reasons: list[str]


class InvestigationStep(BaseModel):
    """One step of the investigation, shown in the interface and kept for audit."""

    name: str
    summary: str
    started_at: datetime
    finished_at: datetime | None = None
    details: dict = {}


class ReviewDecision(BaseModel):
    """The decision of the Technical Expert.

    REQUEST_MORE_DETAILS is a decision like the other two: it is recorded with who asked,
    when, and what they want verified, so the request survives as part of the case."""

    reviewer: str
    decision: Literal["APPROVE", "REJECT", "REQUEST_MORE_DETAILS"]
    hypothesis_id: str | None = None  # the approved hypothesis
    comment: str
    decided_at: datetime
    requested_checks: list[str] = []  # what the expert wants the next investigation to verify
    guidance: InvestigationGuidance | None = None  # wider searches the expert asks for, applied by code


class RCARecord(BaseModel):
    """The RCA as the application stores it and the interface shows it."""

    rca_id: str = Field(pattern=r"^RCA-\d{4}-\d{5}$")
    incident_id: str
    status: RCAStatus
    owner: str
    created_at: datetime

    # An incident can be investigated more than once: rejected, or sent back for more detail.
    # Those investigations belong to one case and keep their order, so nothing is overwritten.
    case_id: str | None = None  # None means this analysis is the case
    cycle: int = 1
    parent_rca_id: str | None = None
    completed_at: datetime | None = None
    duration_seconds: float | None = None

    linked_incidents: list[str] = []
    problem_id: str | None = None
    context: InvestigationContext | None = None
    plan: InvestigationPlan | None = None
    evidence: list[Evidence] = []
    timeline: list[TimelineEntry] = []
    trace: list[InvestigationStep] = []

    investigation_summary: str = ""
    observed_patterns: list[str] = []
    hypotheses: list[AssessedHypothesis] = []
    single_hypothesis_reason: str | None = None
    not_checked: list[str] = []
    weakly_supported: bool = False
    suggested_workaround: str | None = None
    change_likely_required: bool = False

    review: ReviewDecision | None = None
    final_root_cause: str | None = None

    @property
    def case(self) -> str:
        """The case this analysis belongs to. An analysis with no case is its own case."""
        return self.case_id or self.rca_id

    @model_validator(mode="after")
    def final_root_cause_requires_human_approval(self):
        approved = self.review is not None and self.review.decision == "APPROVE"
        if self.final_root_cause is not None and not (self.status == "FINAL" and approved):
            raise ValueError("final_root_cause can be set only on a FINAL RCA approved by a Technical Expert")
        if self.status == "FINAL" and (not approved or self.final_root_cause is None):
            raise ValueError("a FINAL RCA needs an approval and a final_root_cause")
        return self
