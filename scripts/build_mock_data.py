#!/usr/bin/env python3
"""Build all mock source data, the past RCA documents and the evaluation files.

The output is deterministic: the same code always gives the same files (fixed random seed).

    python scripts/build_mock_data.py            # write the files
    python scripts/build_mock_data.py --check    # build and validate only, write nothing

What it writes:
    data/sources/incidents.json, incident_events.json, changes.json, logs.json,
    cmdb_items.json, cmdb_relationships.json
    data/knowledge_base/rcas/*.md                 (the old files are replaced)
    data/evaluation/answer_key.json, story_definitions.json, retrieval_questions.json

After writing, reload SQLite (scripts/load_sources_sqlite.py --reset) and ChromaDB
(scripts/ingest_chroma.py --reset).
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from mock_data import catalog  # noqa: E402
from mock_data.stories import STORIES  # noqa: E402
from rca.models import Change, CIRelationship, ConfigItem, Incident, IncidentEvent, LogEntry  # noqa: E402

SEED = 20260930
NOW = datetime(2026, 9, 30, 12, 0, tzinfo=timezone.utc)
FIRST_DAY = datetime(2024, 1, 3, tzinfo=timezone.utc)
LAST_DAY = datetime(2026, 9, 29, tzinfo=timezone.utc)
TOTAL_INCIDENTS = 500
RECURRENCE_DAYS = 60  # the third similar incident in this many days needs an RCA
ROUTINE_SPACING = 1.4  # stretches the intervals of catalog.ROUTINE_CHANGES

SOURCES = ROOT / "data" / "sources"
RCA_DIR = ROOT / "data" / "knowledge_base" / "rcas"
EVALUATION = ROOT / "data" / "evaluation"

# Numbers per year, so the ids grow with the date like in a real ITSM tool.
INCIDENTS_PER_YEAR = 1600
CHANGES_PER_YEAR = 1600
RCAS_PER_YEAR = 400

EXTRA_PREFIXES = {"Kubernetes Platform": "K8S", "Network Services": "NET", "Event Streaming Platform": "KAFKA",
                  "Observability Platform": "OBS", "External Vendors": "VENDOR"}
# (major version, minor versions per month) of each service, so versions grow over time.
VERSIONS = {"Payment API": (4, 0.6), "Auth Service": (7, 0.5), "Billing Service": (2, 1.07), "Settlement Service": (3, 0.4),
            "Notification Service": (6, 0.5), "Payroll Service": (2, 0.4), "User Profile Service": (3, 0.08),
            "Reporting Service": (3, 0.33)}
OTHER_GROUPS = ["Database Engineering", "Network Engineering", "Platform Operations", "Service Desk"]
# Words that name a cause. They must not appear in what the investigation starts from.
CAUSE_WORDS = re.compile(r"root cause|caused by|exhaust|leak|deadlock|expired|missing index|misconfigur|race condition|"
                         r"out of memory|disk full|poison|evict", re.I)

rng = random.Random(SEED)


# --------------------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------------------


def ts(value: str | datetime) -> datetime:
    return value if isinstance(value, datetime) else datetime.fromisoformat(value.replace("Z", "+00:00"))


def iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def weighted(weights: dict | tuple | list):
    items = list(weights.items()) if isinstance(weights, dict) else list(enumerate(weights))
    return rng.choices([key for key, _ in items], weights=[weight for _, weight in items])[0]


def prefix_of(service: str) -> str:
    return catalog.SERVICES[service]["prefix"] if service in catalog.SERVICES else EXTRA_PREFIXES[service]


def version_for(service: str, at: datetime) -> str:
    if service == "Customer Portal":
        return f"{at.year}.{at.month:02d}.{rng.randint(1, 5)}"
    major, per_month = VERSIONS.get(service, (1, 0.5))
    months = (at.year - 2024) * 12 + at.month - 1
    return f"{major}.{int(months * per_month)}.{rng.randint(0, 4)}"


def fill(template: str, counter: float | None = None) -> str:
    """Fill the placeholders of a log message."""
    n = counter if counter is not None else rng.randint(2, 60)
    n_text = f"{n:.1f}" if isinstance(n, float) and not n.is_integer() else f"{int(n):,}"
    return (template.replace("{n}", n_text).replace("{ms}", f"{rng.randint(1200, 9800):,}")
            .replace("{pct}", str(rng.randint(86, 99))).replace("{id}", str(rng.randint(10000, 99999))))


def number_ids(items: list[dict], key: str, stamp: str, prefix: str, per_year: int, reserved: set[str]) -> None:
    """Give ids like INC-2025-00412 to the items without one, growing with the date inside each year."""
    by_year: dict[int, list[dict]] = defaultdict(list)
    for item in items:
        by_year[ts(item[stamp]).year].append(item)
    for year, group in by_year.items():
        previous = 0
        for item in sorted(group, key=lambda entry: ts(entry[stamp])):
            if item.get(key):
                continue
            number = max(previous + 1, int(ts(item[stamp]).timetuple().tm_yday * per_year / 366))
            while f"{prefix}-{year}-{number:05d}" in reserved:
                number += 1
            item[key] = f"{prefix}-{year}-{number:05d}"
            reserved.add(item[key])
            previous = number


# --------------------------------------------------------------------------------------
# CMDB
# --------------------------------------------------------------------------------------


def build_cmdb() -> tuple[list[dict], list[dict]]:
    items = [
        {"ci_id": ci_id, "name": name, "type": type_, "service": service, "environment": "production",
         "owner_team": owner, "criticality": criticality}
        for ci_id, name, type_, service, owner, criticality in catalog.CONFIG_ITEMS
    ]
    relationships = [{"source_ci": s, "target_ci": t, "relationship_type": r} for s, t, r in catalog.RELATIONSHIPS]
    return items, relationships


def related_services(service: str, items: list[dict], relationships: list[dict]) -> set[str]:
    """The service and the services it depends on directly, as the change lookup sees them."""
    by_id = {item["ci_id"]: item for item in items}
    own = {item["ci_id"] for item in items if item["service"] == service}
    return {service} | {by_id[rel["target_ci"]]["service"] for rel in relationships if rel["source_ci"] in own}


# --------------------------------------------------------------------------------------
# Incidents and their events
# --------------------------------------------------------------------------------------


def make_incident(base: dict, service: str) -> dict:
    """The incident record as the source file stores it (the fields of rca.models.Incident)."""
    info = catalog.SERVICES[service]
    detected, resolved = ts(base["detected_at"]), ts(base["resolved_at"])
    return {
        "incident_id": base.get("incident_id"),
        "title": base["title"],
        "description": base["description"],
        "severity": base["severity"],
        "status": "Closed",  # set from the events
        "service": service,
        "business_service": info["business"],
        "environment": "production",
        "detected_at": iso(detected),
        "resolved_at": iso(resolved),
        "duration_minutes": int((resolved - detected).total_seconds() // 60),
        "affected_regions": base.get("affected_regions") or rng.choice(info["regions"]),
        "impact": base.get("impact") if base.get("impact") is not None else make_impact(service, base["severity"]),
        "symptoms": base["symptoms"],
        "initial_mitigation": base["initial_mitigation"],
        "reported_by": base["reported_by"],
        "ci_id": base.get("ci_id"),
        "assignment_group": info["team"],
        "reassignment_count": 0,
        "reopen_count": 0,
        "rca_required": base["rca_required"],
        "rca_reason": base["rca_reason"],
    }


def make_impact(service: str, severity: str) -> dict | None:
    if severity == "SEV-4" or (severity == "SEV-3" and rng.random() < 0.5):
        return None
    info = catalog.SERVICES[service]
    low, high = info["customers"]
    share = {"SEV-1": (0.5, 1.0), "SEV-2": (0.15, 0.5), "SEV-3": (0.02, 0.15)}[severity]
    customers = int(high * rng.uniform(*share)) + low // 10
    error_rate = {"SEV-1": (20, 60), "SEV-2": (6, 25), "SEV-3": (1, 8)}[severity]
    return {
        "failed_transactions": int(customers * rng.uniform(1.1, 2.4)) if info["transactional"] else None,
        "estimated_customers_affected": customers,
        "error_rate_peak": f"{rng.uniform(*error_rate):.1f}%",
    }


def build_events(incident: dict, flow: list | None, vendor: bool) -> list[dict]:
    """The lifecycle of an incident, like the state changes of a ServiceNow ticket."""
    detected, resolved = ts(incident["detected_at"]), ts(incident["resolved_at"])
    duration = max((resolved - detected).total_seconds() / 60, 10)
    team = incident["assignment_group"]
    events: list[tuple[datetime, str, str, str | None]] = []

    if flow:
        for minutes, action, group, note in flow:
            if action == "workaround":
                note = note or incident["initial_mitigation"]
            events.append((detected + timedelta(minutes=minutes), action, group, note))
    else:
        events.append((detected, "opened", "Service Desk", f"Raised by {incident['reported_by']}."))
        assigned = detected + timedelta(minutes=rng.randint(2, 12))
        events.append((assigned, "assigned", team, None))
        moments = sorted(rng.uniform(0.15, 0.55) * duration for _ in range(weighted(catalog.REASSIGNMENT_WEIGHTS)))
        for index, minutes in enumerate(moments):
            group = rng.choice(OTHER_GROUPS) if index % 2 == 0 else team
            note = "Handed over for investigation." if group != team else "Returned to the service owner."
            events.append((detected + timedelta(minutes=minutes + 12), "reassigned", group, note))
        if vendor:
            at = detected + timedelta(minutes=duration * rng.uniform(0.3, 0.5))
            events.append((at, "awaiting_vendor", team, "Case opened with the vendor."))
            events.append((at + timedelta(minutes=duration * 0.2), "resumed", team, "Vendor confirmed the problem on their side."))
        elif rng.random() < catalog.AWAITING_CALLER_RATE:
            at = detected + timedelta(minutes=duration * rng.uniform(0.2, 0.4))
            events.append((at, "awaiting_caller", team, "Asked the reporter for examples of failed requests."))
            events.append((at + timedelta(minutes=duration * 0.1), "resumed", team, None))
        events.append((detected + timedelta(minutes=duration * rng.uniform(0.6, 0.85)), "workaround", team, incident["initial_mitigation"]))

    events.append((resolved, "resolved", team, "Service restored."))
    closed_at = resolved + timedelta(days=catalog.AUTO_CLOSE_DAYS)
    if rng.random() < catalog.REOPEN_RATE and not flow:
        reopened = resolved + timedelta(hours=rng.randint(20, 40))
        events.append((reopened, "reopened", team, "Reporter says the problem came back."))
        events.append((reopened + timedelta(hours=rng.randint(2, 6)), "resolved", team, "Fix confirmed with the reporter."))
        closed_at = reopened + timedelta(days=catalog.AUTO_CLOSE_DAYS)
        incident["reopen_count"] = 1
    if closed_at <= NOW:
        events.append((closed_at, "closed", team, "Closed automatically after 5 days."))

    events.sort(key=lambda event: event[0])
    incident["status"] = "Closed" if events[-1][1] == "closed" else "Resolved"
    incident["reassignment_count"] = sum(1 for event in events if event[1] == "reassigned")
    states = {"opened": "New", "awaiting_caller": "On Hold", "awaiting_vendor": "On Hold", "resolved": "Resolved", "closed": "Closed"}
    return [
        {"event_id": f"EVT-{incident['incident_id'][4:]}-{index:02d}", "incident_id": incident["incident_id"],
         "timestamp": iso(at), "action": action, "state": states.get(action, "In Progress"),
         "assignment_group": group, "note": note}
        for index, (at, action, group, note) in enumerate(events, start=1)
    ]


# --------------------------------------------------------------------------------------
# Logs
# --------------------------------------------------------------------------------------


def burst_lines(burst: dict, service: str) -> list[dict]:
    start, end = ts(burst["start"]), ts(burst["end"])
    count = burst["n"]
    span = (end - start).total_seconds()
    offsets = [0.0] + sorted(rng.uniform(0, span) for _ in range(count - 1)) if count > 1 else [0.0]
    counter = burst.get("counter")
    lines = []
    for index, offset in enumerate(offsets):
        template = burst["messages"][index] if len(burst["messages"]) == count else rng.choice(burst["messages"])
        value = None
        if counter:
            low, high = counter
            value = low + (high - low) * (index / max(count - 1, 1))
            value = round(value, 1) if isinstance(low, float) else int(value)
        lines.append({
            "log_id": burst["ids"][index] if burst.get("ids") else None,
            "timestamp": iso(start + timedelta(seconds=round(offset))),
            "service": burst.get("service") or service,
            "host": rng.choice(burst["hosts"]),
            "level": burst["level"],
            "message": fill(template, value),
            "error_type": burst["error_type"],
            "_ref": burst["ref"],
        })
    return lines


def number_logs(lines: list[dict]) -> None:
    """LOG-PAY-20260714-18: per source and day, in time order, after any id fixed by hand."""
    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for line in lines:
        groups[(prefix_of(line["service"]), line["timestamp"][:10].replace("-", ""))].append(line)
    for (prefix, day), group in groups.items():
        fixed = {line["log_id"] for line in group if line["log_id"]}
        number = max((int(item.rsplit("-", 1)[1]) for item in fixed), default=0) + 1
        for line in sorted(group, key=lambda item: item["timestamp"]):
            if line["log_id"] is None:
                line["log_id"] = f"LOG-{prefix}-{day}-{number:02d}"
                number += 1


# --------------------------------------------------------------------------------------
# The build
# --------------------------------------------------------------------------------------


class World:
    def __init__(self) -> None:
        self.items, self.relationships = build_cmdb()
        self.incidents: list[dict] = []
        self.events: list[dict] = []
        self.changes: list[dict] = []
        self.logs: list[dict] = []
        self.rcas: list[dict] = []
        self.flows: dict[str, list] = {}
        self.vendor: set[str] = set()
        self.family_of: dict[str, str] = {}
        self.protected: list[tuple[set[str], datetime, datetime]] = []  # no background data here

    # ---------------------------------------------------------------- stories
    def add_stories(self) -> None:
        for story in STORIES:
            service = story["service"]
            related = related_services(service, self.items, self.relationships)
            for role, bases in (("target", [story["target"]]), ("history", story["history"]),
                                ("distractor", story.get("distractors", []))):
                for base in bases:
                    incident = make_incident(base, service)
                    incident["_story"], incident["_role"] = story["story_id"], role
                    self.incidents.append(incident)
                    self.flows[incident["incident_id"]] = base.get("flow")
                    before = timedelta(days=8 if role == "target" else 2)
                    self.protected.append((related, ts(incident["detected_at"]) - before, ts(incident["resolved_at"]) + timedelta(days=1)))
            for change in story["changes"]:
                self.changes.append({**{k: v for k, v in change.items() if k != "role"}, "_story": story["story_id"], "_role": change["role"]})
            for burst in story["logs"]:
                self.logs += burst_lines(burst, service)
            for rca in story["rcas"]:
                self.rcas.append({**rca, "_story": story["story_id"]})

    def is_protected(self, service: str, start: datetime, end: datetime) -> bool:
        return any(service in services and start <= window_end and end >= window_start
                   for services, window_start, window_end in self.protected)

    # ---------------------------------------------------------------- background incidents
    def add_background(self) -> None:
        story_count = len(self.incidents)
        wanted = TOTAL_INCIDENTS - story_count
        scale = wanted / sum(family["count"] for family in catalog.FAMILIES)
        plan = [(family, max(3, round(family["count"] * scale))) for family in catalog.FAMILIES]
        # adjust the rounding so the total is exact
        difference = wanted - sum(count for _, count in plan)
        for index in range(abs(difference)):
            family, count = plan[index % len(plan)]
            plan[index % len(plan)] = (family, count + (1 if difference > 0 else -1))

        for family, count in plan:
            for _ in range(count):
                self.incidents.append(self.background_incident(family))

    def background_incident(self, family: dict) -> dict:
        service = family["service"]
        for _ in range(200):
            day = FIRST_DAY + timedelta(days=rng.randint(0, (LAST_DAY - FIRST_DAY).days))
            hours = {"business": list(range(8, 18)), "peak": [8, 9, 17, 18, 19, 20], "night": [0, 1, 2, 3, 4, 22, 23],
                     "any": list(range(24))}[family["hours"]]
            if family["hours"] == "business" and day.weekday() >= 5:
                continue
            detected = day.replace(hour=rng.choice(hours), minute=rng.randint(0, 59))
            severity = f"SEV-{weighted(family['severity']) + 1}"
            median = {"SEV-1": 70, "SEV-2": 95, "SEV-3": 130, "SEV-4": 190}[severity]
            resolved = detected + timedelta(minutes=max(15, int(rng.lognormvariate(0, 0.45) * median)))
            if not self.is_protected(service, detected - timedelta(hours=26), resolved + timedelta(hours=2)):
                break
        info = catalog.SERVICES[service]
        description = rng.choice(family["descriptions"])
        extra = []
        if family.get("change"):
            extra.append("The problems started shortly after a planned change on the service.")
        extra.append(rng.choice(["", "Monitoring raised the alert before customers called.", "First reports came from customers.",
                                 f"Impact was limited to {', '.join(rng.choice(info['regions']))}."]))
        base = {
            "title": rng.choice(family["titles"]),
            "description": " ".join(part for part in [description, *extra] if part),
            "severity": severity, "detected_at": iso(detected), "resolved_at": iso(resolved),
            "symptoms": sorted(rng.sample(family["symptoms"], k=min(len(family["symptoms"]), rng.choice([1, 2, 2, 2, 3]))),
                               key=family["symptoms"].index),
            "initial_mitigation": family["mitigation"], "reported_by": rng.choice(info["reporters"]),
            "rca_required": False, "rca_reason": None, "ci_id": family["ci"],
        }
        incident = make_incident(base, service)
        incident["_family"] = family["key"]
        if family.get("vendor"):
            self.vendor.add(id(incident))
        # the change behind the family, and the log lines
        first_log = detected - timedelta(minutes=rng.randint(2, 25))
        if family.get("change"):
            template = family["change"]
            at = first_log - timedelta(minutes=rng.randint(*template["lead"]))
            self.changes.append({
                "change_id": None, "title": template["title"].replace("{version}", version_for(service, at)),
                "description": template["description"], "type": template["type"], "service": service,
                "ci_id": template["ci"], "version": None, "implemented_at": iso(at),
                "implemented_by": info["team"], "risk": template["risk"], "rollback": rng.random() < 0.6,
                "_family": family["key"],
            })
        for level, error_type, messages in family["logs"]:
            count = rng.randint(6, 22) if level == "ERROR" else rng.randint(3, 10)
            start = first_log + timedelta(minutes=0 if level == family["logs"][0][0] else rng.randint(0, 10))
            end = max(start + timedelta(minutes=5), ts(incident["resolved_at"]) - timedelta(minutes=rng.randint(3, 15)))
            self.logs += burst_lines({"ref": None, "start": iso(start), "end": iso(end), "n": count, "level": level,
                                      "error_type": error_type, "messages": messages,
                                      "hosts": rng.sample(info["hosts"], k=min(2, len(info["hosts"])))}, service)
        return incident

    # ---------------------------------------------------------------- ids, RCA flags, events
    def finish_incidents(self) -> None:
        reserved = {incident["incident_id"] for incident in self.incidents if incident["incident_id"]}
        number_ids(self.incidents, "incident_id", "detected_at", "INC", INCIDENTS_PER_YEAR, reserved)
        for incident in self.incidents:
            if "_family" in incident:
                self.family_of[incident["incident_id"]] = incident["_family"]
                if id(incident) in self.vendor:
                    self.vendor.add(incident["incident_id"])

        # the rule for background incidents: SEV-1, or the third similar incident in 60 days (SEV-4 excluded)
        by_family: dict[str, list[dict]] = defaultdict(list)
        for incident in self.incidents:
            if "_family" in incident:
                by_family[incident["_family"]].append(incident)
        for group in by_family.values():
            group.sort(key=lambda item: item["detected_at"])
            for index, incident in enumerate(group):
                detected = ts(incident["detected_at"])
                recent = [item for item in group[:index] if detected - ts(item["detected_at"]) <= timedelta(days=RECURRENCE_DAYS)]
                if incident["severity"] == "SEV-1":
                    incident["rca_required"], incident["rca_reason"] = True, "SEV-1 major incident: RCA mandatory."
                elif len(recent) >= 2 and incident["severity"] != "SEV-4":
                    incident["rca_required"] = True
                    incident["rca_reason"] = f"Recurring: third similar incident on {incident['service']} within {RECURRENCE_DAYS} days."
                else:
                    incident["rca_reason"] = rng.choice(["No RCA requested at closure.", "Isolated incident; monitored.",
                                                         "Fixed during the incident; no recurrence expected."])
                    if incident["incident_id"] in self.vendor:
                        incident["rca_reason"] = "Vendor issue, followed up through vendor management."

        for incident in self.incidents:
            self.events += build_events(incident, self.flows.get(incident["incident_id"]), incident["incident_id"] in self.vendor)

    # ---------------------------------------------------------------- routine changes
    def add_routine_changes(self) -> None:
        for service, ci_id, type_, risk, every, title, description, versioned in catalog.ROUTINE_CHANGES:
            at = FIRST_DAY + timedelta(days=rng.uniform(0, every))
            while at < LAST_DAY:
                moment = at.replace(hour=rng.choice([19, 20, 21]) if type_ == "normal" else rng.choice([10, 11, 14, 15]),
                                    minute=rng.choice([0, 15, 30, 45]))
                if moment.weekday() < 5 and not self.is_protected(service, moment, moment):
                    version = version_for(service, moment) if versioned else None
                    self.changes.append({
                        "change_id": None, "title": title.replace("{version}", version or ""), "description": description,
                        "type": type_, "service": service, "ci_id": ci_id, "version": version,
                        "implemented_at": iso(moment), "implemented_by": next(item["owner_team"] for item in self.items if item["ci_id"] == ci_id),
                        "risk": risk, "rollback": False,
                    })
                at += timedelta(days=every * ROUTINE_SPACING * rng.uniform(0.7, 1.3))

    # ---------------------------------------------------------------- background RCAs
    def add_family_rcas(self) -> None:
        reserved = {rca["rca_id"] for rca in self.rcas}
        pending = []
        for family in catalog.FAMILIES:
            if not family.get("rca"):
                continue
            group = sorted((item for item in self.incidents if item.get("_family") == family["key"]), key=lambda item: item["detected_at"])
            anchor = next((item for index, item in enumerate(group)
                           if index >= 1 and item["severity"] in ("SEV-1", "SEV-2") and ts(item["resolved_at"]) < datetime(2026, 7, 1, tzinfo=timezone.utc)),
                          None) or (group[1] if len(group) > 1 else group[0])
            earlier = [item for item in group if item["detected_at"] < anchor["detected_at"]
                       and ts(anchor["detected_at"]) - ts(item["detected_at"]) <= timedelta(days=150)][-1:]
            anchor["rca_required"], anchor["rca_reason"] = True, "Recurring problem; RCA requested by the service owner."
            completed = ts(anchor["resolved_at"]) + timedelta(days=rng.randint(12, 25), hours=rng.randint(0, 6))
            pending.append({**family["rca"], "rca_id": None, "service": family["service"], "completed": iso(completed.replace(minute=0, second=0)),
                            "linked": [item["incident_id"] for item in earlier + [anchor]],
                            "owner": catalog.SERVICES[family["service"]]["team"], "cost_eur": rng.randint(3, 60) * 500,
                            "timeline": self.timeline_from_events(anchor), "_family": family["key"]})
        number_ids(pending, "rca_id", "completed", "RCA", RCAS_PER_YEAR, reserved)
        self.rcas += pending

    def timeline_from_events(self, incident: dict) -> list[str]:
        names = {"opened": "Incident raised", "assigned": "Assigned to {group}", "reassigned": "Reassigned to {group}",
                 "awaiting_vendor": "Waiting for the vendor", "workaround": "Workaround applied", "resolved": "Service restored"}
        lines = []
        for event in (item for item in self.events if item["incident_id"] == incident["incident_id"]):
            if event["action"] in names and not (event["action"] == "resolved" and lines and lines[-1].endswith("Service restored.")):
                lines.append(f"{event['timestamp'][11:16]} UTC: {names[event['action']].format(group=event['assignment_group'])}.")
        return lines

    # ---------------------------------------------------------------- final ids
    def finish_changes_and_logs(self) -> None:
        reserved = {change["change_id"] for change in self.changes if change["change_id"]}
        number_ids(self.changes, "change_id", "implemented_at", "CHG", CHANGES_PER_YEAR, reserved)
        number_logs(self.logs)

    def first_line(self, ref: str) -> dict:
        lines = [line for line in self.logs if line["_ref"] == ref]
        if not lines:
            raise ValueError(f"Unknown log burst '{ref}'")
        return min(lines, key=lambda line: line["timestamp"])

    def cite(self, value: str) -> str:
        """A citation of the answer key: "@burst" is the first log line of a burst, "family:key" the RCA of a family."""
        if value.startswith("@"):
            return self.first_line(value[1:])["log_id"]
        if value.startswith("family:"):
            return next(rca["rca_id"] for rca in self.rcas if rca.get("_family") == value.split(":", 1)[1])
        return value


# --------------------------------------------------------------------------------------
# Past RCA documents
# --------------------------------------------------------------------------------------


def render_rca(rca: dict) -> str:
    whys = "\n".join(f"{index}. {why} {because}" for index, (why, because) in enumerate(rca["whys"], start=1))
    factors = "\n".join(f"- **{category}:** {text}" for category, text in rca["factors"].items())
    timeline = "\n".join(f"- {line}" for line in rca["timeline"])
    return (
        f"# INCIDENT INVESTIGATION REPORT: {rca['rca_id']}\n"
        f"**Service:** {rca['service']}  \n"
        f"**Completion Date:** {rca['completed']}  \n"
        f"**Linked Incidents:** {', '.join(rca['linked'])}  \n"
        f"**Investigation Owner:** {rca['owner']}  \n"
        f"**Root Cause Category:** {rca['category']}  \n"
        f"**Business Impact:** EUR {rca['cost_eur']:,} (estimated)  \n\n"
        f"## Summary\n{rca['summary']}\n\n"
        f"## Timeline\n{timeline}\n\n"
        f"## Root Cause\n{rca['root_cause']}\n\n"
        f"## Five Whys\n{whys}\n\n"
        f"## Contributing Factors\n{factors}\n\n"
        f"## Corrective Actions\n{rca['corrective']}\n\n"
        f"## Preventive Actions\n{rca['preventive']}\n"
    )


# --------------------------------------------------------------------------------------
# Evaluation files
# --------------------------------------------------------------------------------------


def build_answer_key(world: World) -> dict:
    changes = {change["change_id"]: change for change in world.changes}
    events_by_incident = defaultdict(list)
    for event in world.events:
        events_by_incident[event["incident_id"]].append(event)

    key = {}
    for story in STORIES:
        answer = story["answer"]
        target = story["target"]["incident_id"]
        detected, resolved = ts(story["target"]["detected_at"]), ts(story["target"]["resolved_at"])

        timeline = []
        for change in story["changes"]:
            at = ts(change["implemented_at"])
            if change["role"] == "cause" or detected - timedelta(days=30) <= at <= resolved:
                timeline.append({"at": change["implemented_at"], "what": f"Change: {change['title']}", "role": change["role"],
                                 "source": "CHANGE", "citation": change["change_id"]})
        for burst in story["logs"]:
            if burst.get("label") and detected - timedelta(days=30) <= ts(burst["start"]) <= resolved:
                line = world.first_line(burst["ref"])
                timeline.append({"at": line["timestamp"], "what": burst["label"], "role": "log", "source": "LOG", "citation": line["log_id"]})
        for event in events_by_incident[target]:
            if event["action"] in ("opened", "assigned", "reassigned", "awaiting_vendor", "awaiting_caller", "workaround", "resolved"):
                what = {"opened": "Incident detected", "workaround": "Workaround applied", "resolved": "Service restored"}.get(
                    event["action"], f"{event['action'].replace('_', ' ').capitalize()}: {event['assignment_group']}")
                timeline.append({"at": event["timestamp"], "what": what, "role": "incident", "source": "INCIDENT_EVENT",
                                 "citation": event["event_id"]})
        timeline.sort(key=lambda item: item["at"])

        key[story["story_id"]] = {
            "story_id": story["story_id"],
            "title": story["title"],
            "kind": story["kind"],
            "service": story["service"],
            "target_incident": target,
            "cluster_incidents": [item["incident_id"] for item in story["history"]],
            "distractor_incidents": [item["incident_id"] for item in story.get("distractors", [])],
            "time_pattern": story["time_pattern"],
            "true_root_cause": answer["true_root_cause"],
            "root_cause_category": answer["root_cause_category"],
            "expected_citations": [world.cite(item) for item in answer["expected_citations"]],
            "red_herrings": [{"citation": world.cite(item["citation"]), "why": item["why"]} for item in answer["red_herrings"]],
            "expected_outcome": answer["expected_outcome"],
            "five_whys": [{"step": index, "why": why, "because": because, "evidence": [world.cite(item) for item in evidence],
                           "verifiable_from_sources": bool(evidence)}
                          for index, (why, because, evidence) in enumerate(answer["five_whys"], start=1)],
            "fishbone": {category: [{"factor": factor, "evidence": [world.cite(item) for item in evidence]}
                                    for factor, evidence in answer["fishbone"].get(category, [])]
                         for category in catalog.FISHBONE_CATEGORIES},
            "timeline": timeline,
        }
        assert all(item["citation"] in changes for item in timeline if item["source"] == "CHANGE")
    return key


def build_story_definitions() -> list[dict]:
    return [
        {
            "story_id": story["story_id"], "title": story["title"], "kind": story["kind"],
            "demo_purpose": story["demo_purpose"], "service": story["service"],
            "business_service": catalog.SERVICES[story["service"]]["business"],
            "target_incident": story["target"]["incident_id"],
            "related_incidents": [item["incident_id"] for item in story["history"]],
            "has_time_pattern": story["time_pattern"] is not None, "time_pattern": story["time_pattern"],
            "has_historical_rca": bool(story["rcas"]), "historical_rca_ids": [rca["rca_id"] for rca in story["rcas"]],
        }
        for story in STORIES
    ]


def build_retrieval_questions(world: World) -> list[dict]:
    """Which past records the search should bring back for a given incident (for RAGAS)."""
    incidents = {incident["incident_id"]: incident for incident in world.incidents}
    questions = []
    for story in STORIES:
        target = incidents[story["target"]["incident_id"]]
        misleading = [rca["rca_id"] for rca in story["rcas"] if story["story_id"] == "STORY-005"]
        questions.append({
            "question_id": f"RQ-{len(questions) + 1:03d}", "source": story["story_id"],
            "incident_id": target["incident_id"], "service": target["service"], "before": target["detected_at"],
            "query": " | ".join([target["title"], target["description"], " | ".join(target["symptoms"])]),
            "relevant_incidents": [item["incident_id"] for item in story["history"]],
            "relevant_rcas": [rca["rca_id"] for rca in story["rcas"] if rca["rca_id"] not in misleading],
            "misleading_records": misleading + [item["incident_id"] for item in story.get("distractors", [])],
        })
    for rca in (item for item in world.rcas if "_family" in item):
        group = sorted((item for item in world.incidents if item.get("_family") == rca["_family"]), key=lambda item: item["detected_at"])
        later = [item for item in group if ts(item["detected_at"]) > ts(rca["completed"])]
        if not later:
            continue
        target = later[0]
        questions.append({
            "question_id": f"RQ-{len(questions) + 1:03d}", "source": rca["_family"],
            "incident_id": target["incident_id"], "service": target["service"], "before": target["detected_at"],
            "query": " | ".join([target["title"], target["description"], " | ".join(target["symptoms"])]),
            "relevant_incidents": [item["incident_id"] for item in group if item["detected_at"] < target["detected_at"]],
            "relevant_rcas": [rca["rca_id"]], "misleading_records": [],
        })
    return questions


# --------------------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------------------


def validate(world: World, answer_key: dict) -> list[str]:
    problems: list[str] = []
    incidents = {item["incident_id"]: item for item in world.incidents}
    changes = {item["change_id"]: item for item in world.changes}
    logs = {item["log_id"]: item for item in world.logs}
    items = {item["ci_id"]: item for item in world.items}
    rcas = {item["rca_id"]: item for item in world.rcas}
    known = set(incidents) | set(changes) | set(logs) | set(items) | set(rcas) | {event["event_id"] for event in world.events}

    for name, records, key in (("incident", world.incidents, "incident_id"), ("change", world.changes, "change_id"),
                               ("log", world.logs, "log_id"), ("event", world.events, "event_id"), ("RCA", world.rcas, "rca_id")):
        duplicates = [value for value, count in Counter(record[key] for record in records).items() if count > 1]
        if duplicates:
            problems.append(f"duplicate {name} ids: {duplicates[:5]}")

    for relationship in world.relationships:
        if relationship["source_ci"] not in items or relationship["target_ci"] not in items:
            problems.append(f"relationship to an unknown CI: {relationship}")
    for change in world.changes:
        if change["ci_id"] not in items:
            problems.append(f"{change['change_id']} touches an unknown CI {change['ci_id']}")
        if change["service"] != items[change["ci_id"]]["service"]:
            problems.append(f"{change['change_id']}: service {change['service']} differs from its CI")
    for incident in world.incidents:
        if incident["ci_id"] and incident["ci_id"] not in items:
            problems.append(f"{incident['incident_id']} has an unknown CI {incident['ci_id']}")
        minutes = int((ts(incident["resolved_at"]) - ts(incident["detected_at"])).total_seconds() // 60)
        if minutes != incident["duration_minutes"]:
            problems.append(f"{incident['incident_id']}: wrong duration")

    events_by_incident = defaultdict(list)
    for event in world.events:
        events_by_incident[event["incident_id"]].append(event)
    for incident_id, events in events_by_incident.items():
        times = [event["timestamp"] for event in events]
        if times != sorted(times) or times[0] != incidents[incident_id]["detected_at"]:
            problems.append(f"{incident_id}: events out of order or not starting at detection")
        if not any(event["action"] == "resolved" and event["timestamp"] == incidents[incident_id]["resolved_at"] for event in events):
            problems.append(f"{incident_id}: no resolved event at resolved_at")

    for rca in world.rcas:
        for incident_id in rca["linked"]:
            if incident_id not in incidents:
                problems.append(f"{rca['rca_id']} links an unknown incident {incident_id}")
            elif incidents[incident_id]["detected_at"] >= rca["completed"]:
                problems.append(f"{rca['rca_id']} was completed before {incident_id} happened")
        if ts(rca["completed"]) > NOW:
            problems.append(f"{rca['rca_id']} is completed in the future")

    for story in STORIES:
        target = incidents[story["target"]["incident_id"]]
        text = " ".join([target["title"], target["description"], *target["symptoms"]])
        if CAUSE_WORDS.search(text):
            problems.append(f"{target['incident_id']}: the incident text names a cause ({CAUSE_WORDS.search(text).group(0)})")
        # only the changes written in the story may be in its window
        related = related_services(story["service"], world.items, world.relationships)
        start, end = ts(target["detected_at"]) - timedelta(days=7), ts(target["resolved_at"])
        allowed = {change["change_id"] for change in story["changes"]}
        extra = [change["change_id"] for change in world.changes
                 if change["service"] in related and start <= ts(change["implemented_at"]) <= end and change["change_id"] not in allowed]
        if extra:
            problems.append(f"{story['story_id']}: unplanned changes in the window: {extra}")
        stray = [line["log_id"] for line in world.logs if line["_ref"] is None and line["service"] == story["service"]
                 and start <= ts(line["timestamp"]) <= end]
        if stray:
            problems.append(f"{story['story_id']}: background log lines in the window: {stray[:3]}")

    for story_id, entry in answer_key.items():
        # a CMDB item can be cited only if the CMDB lookup returns it: a dependency of the service
        own = {item["ci_id"] for item in world.items if item["service"] == entry["service"]}
        citable = {rel["target_ci"] for rel in world.relationships if rel["source_ci"] in own}
        for citation in entry["expected_citations"]:
            if citation in items and citation not in citable:
                problems.append(f"{story_id} expects {citation}, which the CMDB lookup never returns for {entry['service']}")
        cited = entry["expected_citations"] + [item["citation"] for item in entry["timeline"] + entry["red_herrings"]]
        cited += [item for step in entry["five_whys"] for item in step["evidence"]]
        cited += [item for factors in entry["fishbone"].values() for factor in factors for item in factor["evidence"]]
        for citation in cited:
            if citation not in known:
                problems.append(f"{story_id} cites an unknown record {citation}")

    for incident in world.incidents:
        Incident.model_validate(public(incident))
    for record in world.events:
        IncidentEvent.model_validate(record)
    for record in world.changes:
        Change.model_validate(public(record))
    for record in world.logs:
        LogEntry.model_validate(public(record))
    for record in world.items:
        ConfigItem.model_validate(record)
    for record in world.relationships:
        CIRelationship.model_validate(record)
    return problems


def public(record: dict) -> dict:
    """The record without the generator's own bookkeeping fields."""
    return {key: value for key, value in record.items() if not key.startswith("_")}


# --------------------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------------------


def build() -> tuple[World, dict]:
    world = World()
    world.add_stories()
    world.add_background()
    world.finish_incidents()
    world.add_routine_changes()
    world.add_family_rcas()
    world.finish_changes_and_logs()
    answer_key = build_answer_key(world)
    return world, answer_key


def write_json(path: Path, records) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(records, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the mock data of the RCA application.")
    parser.add_argument("--check", action="store_true", help="build and validate only, write nothing")
    args = parser.parse_args()

    world, answer_key = build()
    problems = validate(world, answer_key)
    if problems:
        raise SystemExit("The mock data is not consistent:\n- " + "\n- ".join(problems))

    world.incidents.sort(key=lambda item: item["detected_at"])
    world.changes.sort(key=lambda item: item["implemented_at"])
    world.logs.sort(key=lambda item: (item["timestamp"], item["log_id"]))
    world.events.sort(key=lambda item: (item["incident_id"], item["timestamp"]))
    summary = (f"{len(world.incidents)} incidents ({sum(item['rca_required'] for item in world.incidents)} need an RCA), "
               f"{len(world.events)} incident events, {len(world.changes)} changes, {len(world.logs)} log lines, "
               f"{len(world.items)} CMDB items, {len(world.relationships)} relationships, {len(world.rcas)} past RCAs, "
               f"{len(STORIES)} stories")
    if args.check:
        print(f"OK (nothing written): {summary}")
        return

    write_json(SOURCES / "incidents.json", [public(item) for item in world.incidents])
    write_json(SOURCES / "incident_events.json", world.events)
    write_json(SOURCES / "changes.json", [public(item) for item in world.changes])
    write_json(SOURCES / "logs.json", [public(item) for item in world.logs])
    write_json(SOURCES / "cmdb_items.json", world.items)
    write_json(SOURCES / "cmdb_relationships.json", world.relationships)

    RCA_DIR.mkdir(parents=True, exist_ok=True)
    for old in RCA_DIR.glob("*.md"):
        old.unlink()
    for rca in world.rcas:
        (RCA_DIR / f"{rca['rca_id']}.md").write_text(render_rca(rca), encoding="utf-8")

    write_json(EVALUATION / "answer_key.json", answer_key)
    write_json(EVALUATION / "story_definitions.json", build_story_definitions())
    write_json(EVALUATION / "retrieval_questions.json", build_retrieval_questions(world))
    print(f"Written: {summary}")


if __name__ == "__main__":
    main()
