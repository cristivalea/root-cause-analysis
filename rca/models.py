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
    rca_required: bool
    rca_reason: str | None = None


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


# --------------------------------------------------------------------------------------
# Application data
# --------------------------------------------------------------------------------------

EvidenceType = Literal["LOG", "CHANGE", "CMDB", "HISTORICAL_RCA", "HISTORICAL_INCIDENT"]
SourceName = Literal["logs", "changes", "cmdb", "historical_rcas", "historical_incidents"]
ConfidenceLevel = Literal["HIGH", "MEDIUM", "LOW"]
# The states an RCA goes through.
# DRAFT: investigation finished, but the Problem Manager has not sent it to the expert yet.
# MORE_DETAILS_REQUESTED: the Technical Expert asked for a further investigation of this case.
RCAStatus = Literal[
    "INVESTIGATING",
    "DRAFT",
    "PENDING_REVIEW",
    "MORE_DETAILS_REQUESTED",
    "ESCALATED",
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


class Hypothesis(BaseModel):
    """A candidate root cause proposed by the RCA Reasoning Agent. No confidence on purpose:
    the model writes the reasons, the code calculates the level."""

    hypothesis_id: str = Field(pattern=r"^HYP-\d{3}$")
    candidate_root_cause: str
    reasons: list[str]
    supporting_evidence: list[str]  # evidence ids only
    contradicting_evidence: list[str]  # evidence ids only
    recommended_validation: list[str]


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
    plan: InvestigationPlan | None = None
    evidence: list[Evidence] = []
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
