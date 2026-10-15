"""The KPIs of the application, computed from what is stored (docs/KPIS.md, docs/ui-ux-rebuild/kpi-plan.md).

Read only: nothing here changes the data. Two kinds of numbers:

- live: from the problems, the RCAs, their revisions and their status history, for the RCAs started in a period;
- benchmark: the reports the evaluation scripts write (scripts/eval_kpi_accuracy.py, eval_kpi_confidence.py),
  used only when they were written by the current version of the scripts.

The four KPIs keep the definitions of docs/KPIS.md and measure them on real RCAs:

KPI 1  human interactions: 1 to start the RCA, 1 per sending to the expert, 1 per decision of the expert, 1 per
       further revision started, 1 to read the final decision. The happy path is the 4 of docs/KPIS.md; the
       reduction is measured against the 11 steps of the manual process described there.
KPI 2  runs completed without a person: a run (a revision) that ended with an analysis, out of every run that
       ended. A run FAILED, or refused by the guardrail in every attempt (the run itself moved the RCA to
       ESCALATED_MANUAL, no decision of the expert did), needed a person. Next to it, the design share of docs/KPIS.md.
KPI 3  accuracy, the expert being the judge: of the RCAs the expert decided for good (VALIDATED, REJECTED, or
       ESCALATED_MANUAL after the last request), Top-K = validated, Top-1 = validated with the first hypothesis
       of the revision the expert approved (the hypotheses are ordered strongest first by rca/confidence.py).
KPI 4  calibration: every decision of the expert, by the confidence of the first hypothesis of the revision it
       was taken on; the share approved per level. Well calibrated: HIGH approved more often than MEDIUM, than LOW.
"""

from __future__ import annotations

import json
import statistics
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path

from rca import problems as problem_rules, store
from rca.config import DB_PATH, ROOT_DIR
from rca.models import RCA, RCARecord, RCAStatusChange

# docs/KPIS.md, KPI 1 and KPI 2: the process comparison of the teammate, kept as the reference
MANUAL_INTERACTIONS = 11
DESIGN_INTERACTIONS = 4
DESIGN_AUTOMATED_STAGES = 5
DESIGN_STAGES = 8
# the reports of the evaluation scripts this module trusts: written by the version that runs on a database
# built from the sources, without fallback models (older reports are listed as not valid)
BENCHMARK_SCRIPT_VERSION = 2
ACCURACY_REPORT = ROOT_DIR / "data" / "evaluation" / "kpi_accuracy_report.json"
CONFIDENCE_REPORT = ROOT_DIR / "data" / "evaluation" / "kpi_confidence_report.json"
FINAL = ("VALIDATED", "REJECTED")
LEVELS = ("HIGH", "MEDIUM", "LOW")


def percent(part: int, whole: int) -> float | None:
    return round(part / whole * 100, 1) if whole else None


@dataclass
class Case:
    """One RCA with what the KPIs need from it."""

    rca: RCA
    revisions: list[RCARecord]
    history: list[RCAStatusChange]

    @property
    def decisions(self) -> list[RCAStatusChange]:
        return [item for item in self.history if item.decision is not None]

    @property
    def decided(self) -> bool:
        """Decided for good by the expert: validated, rejected, or escalated after the last request."""
        return self.rca.status in FINAL or (self.rca.status == "ESCALATED_MANUAL" and bool(self.decisions))

    def refused_by_checks(self) -> set[str]:
        """The revisions whose run ended in manual review by itself (the guardrail refused the draft in every
        attempt): a change to ESCALATED_MANUAL that no decision of the expert caused."""
        return {item.revision_id or "" for item in self.history if item.to_status == "ESCALATED_MANUAL" and item.decision is None}

    def interactions(self) -> int:
        """KPI 1: the steps a person made on this RCA (records rebuilt by the migration may lack the sending:
        every decision was taken on an RCA that had been sent)."""
        sends = max(sum(1 for item in self.history if item.to_status == "AWAITING_TECHNICAL_REVIEW"), len(self.decisions))
        return 1 + sends + len(self.decisions) + (len(self.revisions) - 1) + 1

    def top1(self) -> bool:
        """KPI 3: validated with the first hypothesis of the approved revision."""
        approval = next((item for item in reversed(self.decisions) if item.decision.decision == "APPROVE"), None)
        if self.rca.status != "VALIDATED" or approval is None:
            return False
        revision = next((item for item in self.revisions if item.revision_id == approval.revision_id), self.revisions[-1])
        return bool(revision.hypotheses) and revision.hypotheses[0].hypothesis_id == approval.decision.hypothesis_id

    def hours_to_decision(self) -> float | None:
        if not self.decided or not self.decisions:
            return None
        return (self.decisions[-1].at - self.rca.created_at).total_seconds() / 3600


def load_cases(db_path: Path = DB_PATH, start: date | None = None, end: date | None = None) -> list[Case]:
    """The RCAs started in the period (both days included), with their revisions and history."""
    cases = []
    for rca in store.list_summaries(db_path=db_path):
        day = rca.created_at.date()
        if (start and day < start) or (end and day > end):
            continue
        cases.append(Case(rca, store.list_revisions(rca.rca_id, db_path=db_path), store.status_history(rca.rca_id, db_path)))
    return cases


def week_of(moment: datetime) -> str:
    """The Monday of the week, for the trend."""
    day = moment.date()
    return (day - timedelta(days=day.weekday())).isoformat()


@dataclass
class Overview:
    problems: dict[str, int]
    awaiting_review: int
    rcas_started: int
    rcas_running: int
    problems_closed: int
    median_hours_to_decision: float | None
    decided_count: int


@dataclass
class Kpi1:
    finished: int
    average_interactions: float | None
    reduction_percent: float | None
    happy_path: int
    with_more_steps: int
    manual_interactions: int = MANUAL_INTERACTIONS
    design_interactions: int = DESIGN_INTERACTIONS
    design_reduction_percent: float = round((MANUAL_INTERACTIONS - DESIGN_INTERACTIONS) / MANUAL_INTERACTIONS * 100, 2)


@dataclass
class Kpi2:
    runs: int
    autonomous: int
    failed: int
    refused_by_checks: int
    rate_percent: float | None
    design_automated: int = DESIGN_AUTOMATED_STAGES
    design_stages: int = DESIGN_STAGES
    design_percent: float = round(DESIGN_AUTOMATED_STAGES / DESIGN_STAGES * 100, 1)


@dataclass
class Kpi3:
    decided: int
    top1: int
    topk: int
    top1_percent: float | None
    topk_percent: float | None


@dataclass
class Level:
    level: str
    decisions: int
    approved: int
    approved_percent: float | None


@dataclass
class Kpi4:
    decisions: int
    levels: list[Level]
    ordered: bool | None  # HIGH ≥ MEDIUM ≥ LOW among the levels with decisions; None with fewer than two levels


@dataclass
class Week:
    week: str
    started: int
    validated: int
    rejected: int


@dataclass
class Benchmark:
    status: str  # "measured", "not_measured" (no report), "outdated" (a report of an older script version)
    timestamp: str | None = None
    agent_model: str | None = None
    judge_model: str | None = None
    selected: int | None = None
    evaluated: int | None = None
    values: dict = field(default_factory=dict)
    excluded: list[str] = field(default_factory=list)


def _benchmark(path: Path, keys: dict[str, str]) -> Benchmark:
    if not path.exists():
        return Benchmark("not_measured")
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return Benchmark("not_measured")
    if report.get("script_version") != BENCHMARK_SCRIPT_VERSION:
        return Benchmark("outdated", timestamp=report.get("timestamp"))
    return Benchmark(
        "measured", timestamp=report.get("timestamp"), agent_model=report.get("agent_model"),
        judge_model=report.get("judge_model"), selected=report.get("selected"), evaluated=report.get("evaluated"),
        values={name: report.get(key) for name, key in keys.items()}, excluded=list(report.get("run_errors", [])),
    )


def compute(db_path: Path = DB_PATH, start: date | None = None, end: date | None = None) -> dict:
    """Every KPI for the RCAs started in the period, plus the current situation and the benchmarks."""
    cases = load_cases(db_path, start, end)
    decided = [case for case in cases if case.decided]

    problems = problem_rules.list_problems(db_path=db_path)
    counts = {status: sum(1 for item in problems if item.status == status) for status in ("Open", "In investigation", "Manual", "Closed")}
    closed = [item for item in problems if item.closed_at and (not start or item.closed_at.date() >= start)
              and (not end or item.closed_at.date() <= end)]
    hours = [value for value in (case.hours_to_decision() for case in decided) if value is not None]
    overview = Overview(
        problems=counts,
        awaiting_review=sum(1 for case in cases if case.rca.status == "AWAITING_TECHNICAL_REVIEW"),
        rcas_started=len(cases),
        rcas_running=sum(1 for case in cases if case.revisions and case.revisions[-1].run_status == "RUNNING"),
        problems_closed=len(closed),
        median_hours_to_decision=round(statistics.median(hours), 2) if hours else None,
        decided_count=len(decided),
    )

    interactions = [case.interactions() for case in decided]
    average = round(statistics.mean(interactions), 2) if interactions else None
    kpi1 = Kpi1(
        finished=len(decided), average_interactions=average,
        reduction_percent=round((MANUAL_INTERACTIONS - average) / MANUAL_INTERACTIONS * 100, 1) if average is not None else None,
        happy_path=sum(1 for value in interactions if value <= DESIGN_INTERACTIONS),
        with_more_steps=sum(1 for value in interactions if value > DESIGN_INTERACTIONS),
    )

    runs = [(revision, case.refused_by_checks()) for case in cases for revision in case.revisions if revision.run_status != "RUNNING"]
    refused = sum(1 for run, by_checks in runs if run.run_status == "COMPLETED" and run.revision_id in by_checks)
    failed = sum(1 for run, _ in runs if run.run_status == "FAILED")
    kpi2 = Kpi2(runs=len(runs), autonomous=len(runs) - refused - failed, failed=failed, refused_by_checks=refused,
                rate_percent=percent(len(runs) - refused - failed, len(runs)))

    top1 = sum(1 for case in decided if case.top1())
    topk = sum(1 for case in decided if case.rca.status == "VALIDATED")
    kpi3 = Kpi3(decided=len(decided), top1=top1, topk=topk, top1_percent=percent(top1, len(decided)),
                topk_percent=percent(topk, len(decided)))

    by_level: dict[str, list[bool]] = defaultdict(list)
    for case in cases:
        revisions = {revision.revision_id: revision for revision in case.revisions}
        for change in case.decisions:
            revision = revisions.get(change.revision_id or "")
            if revision is not None and revision.hypotheses:
                by_level[revision.hypotheses[0].confidence].append(change.decision.decision == "APPROVE")
    levels = [Level(level, len(by_level[level]), sum(by_level[level]), percent(sum(by_level[level]), len(by_level[level])))
              for level in LEVELS]
    rates = [item.approved_percent for item in levels if item.decisions]
    kpi4 = Kpi4(decisions=sum(item.decisions for item in levels), levels=levels,
                ordered=all(a >= b for a, b in zip(rates, rates[1:])) if len(rates) >= 2 else None)

    weeks: dict[str, Week] = {}
    for case in cases:
        week = weeks.setdefault(week_of(case.rca.created_at), Week(week_of(case.rca.created_at), 0, 0, 0))
        week.started += 1
        week.validated += case.rca.status == "VALIDATED"
        week.rejected += case.rca.status == "REJECTED"

    return {
        "period": {"from": start.isoformat() if start else None, "to": end.isoformat() if end else None},
        "overview": asdict(overview),
        "kpi1_interactions": asdict(kpi1),
        "kpi2_autonomy": asdict(kpi2),
        "kpi3_accuracy": asdict(kpi3),
        "kpi4_calibration": asdict(kpi4),
        "weeks": [asdict(weeks[key]) for key in sorted(weeks)],
        "benchmark": {
            "accuracy": asdict(_benchmark(ACCURACY_REPORT, {"top1_percent": "top1_accuracy_percent", "topk_percent": "topk_accuracy_percent"})),
            "calibration": asdict(_benchmark(CONFIDENCE_REPORT, {"calibration_percent": "overall_calibration_rate_percent"})),
        },
    }
