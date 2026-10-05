import json
from datetime import datetime
from pathlib import Path

from rca.models import Change, CIRelationship, ConfigItem, Incident, IncidentEvent, LogEntry

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ROOT / "data" / "sources"


def load_json(name: str):
    return json.loads((SOURCES / name).read_text(encoding="utf-8"))


def test_mock_source_files_load_through_step_three_models():
    incidents = [Incident.model_validate(item) for item in load_json("incidents.json")]
    items = [ConfigItem.model_validate(item) for item in load_json("cmdb_items.json")]
    relationships = [CIRelationship.model_validate(item) for item in load_json("cmdb_relationships.json")]
    changes = [Change.model_validate(item) for item in load_json("changes.json")]
    logs = [LogEntry.model_validate(item) for item in load_json("logs.json")]

    assert incidents
    assert items
    assert relationships
    assert changes
    assert logs


def test_payment_api_citations_and_timeline_are_coherent():
    incidents = {item["incident_id"]: item for item in load_json("incidents.json")}
    changes = {item["change_id"]: item for item in load_json("changes.json")}
    logs = {item["log_id"]: item for item in load_json("logs.json")}
    items = {item["ci_id"]: item for item in load_json("cmdb_items.json")}

    incident = incidents["INC-2026-00482"]
    change = changes["CHG-2026-00871"]

    detected_at = datetime.fromisoformat(incident["detected_at"].replace("Z", "+00:00"))
    implemented_at = datetime.fromisoformat(change["implemented_at"].replace("Z", "+00:00"))

    assert (detected_at - implemented_at).total_seconds() == 34 * 60
    assert "root cause" not in incident["description"].lower()
    assert "LOG-PAY-20260714-14" in logs
    assert "CI-PAYMENT-API" in items
    assert (ROOT / "data" / "knowledge_base" / "rcas" / "RCA-2025-00114.md").exists()


def test_payment_source_ids_are_unique():
    for filename, key in [
        ("incidents.json", "incident_id"),
        ("cmdb_items.json", "ci_id"),
        ("changes.json", "change_id"),
        ("logs.json", "log_id"),
    ]:
        records = load_json(filename)
        ids = [record[key] for record in records]
        assert len(ids) == len(set(ids)), filename


def test_source_relationships_reference_existing_configuration_items():
    item_ids = {item["ci_id"] for item in load_json("cmdb_items.json")}
    relationships = load_json("cmdb_relationships.json")
    changes = load_json("changes.json")

    for relationship in relationships:
        assert relationship["source_ci"] in item_ids
        assert relationship["target_ci"] in item_ids

    for change in changes:
        assert change["ci_id"] in item_ids


# The generated data (scripts/build_mock_data.py) ----------------------------------------

EVALUATION = ROOT / "data" / "evaluation"
RCA_FOLDER = ROOT / "data" / "knowledge_base" / "rcas"
CAUSE_WORDS = ("root cause", "caused by", "exhaust", "leak", "deadlock", "expired", "missing index", "misconfigur")


def test_incident_events_tell_the_life_of_each_incident():
    incidents = {item["incident_id"]: item for item in load_json("incidents.json")}
    events = [IncidentEvent.model_validate(item) for item in load_json("incident_events.json")]

    by_incident: dict[str, list[IncidentEvent]] = {}
    for event in events:
        by_incident.setdefault(event.incident_id, []).append(event)

    assert set(by_incident) == set(incidents)
    for incident_id, items in by_incident.items():
        incident = Incident.model_validate(incidents[incident_id])
        assert [item.timestamp for item in items] == sorted(item.timestamp for item in items)
        assert items[0].action == "opened" and items[0].timestamp == incident.detected_at
        assert any(item.action == "resolved" and item.timestamp == incident.resolved_at for item in items)
        assert incident.reassignment_count == sum(item.action == "reassigned" for item in items)
        assert incident.status == ("Closed" if items[-1].action == "closed" else "Resolved")


def test_every_answer_key_citation_exists_in_the_sources():
    known = {item["incident_id"] for item in load_json("incidents.json")}
    known |= {item["change_id"] for item in load_json("changes.json")}
    known |= {item["log_id"] for item in load_json("logs.json")}
    known |= {item["ci_id"] for item in load_json("cmdb_items.json")}
    known |= {item["event_id"] for item in load_json("incident_events.json")}
    known |= {path.stem for path in RCA_FOLDER.glob("*.md")}

    for story in json.loads((EVALUATION / "answer_key.json").read_text(encoding="utf-8")).values():
        cited = story["expected_citations"] + [item["citation"] for item in story["timeline"] + story["red_herrings"]]
        cited += [item for step in story["five_whys"] for item in step["evidence"]]
        cited += [item for factors in story["fishbone"].values() for factor in factors for item in factor["evidence"]]
        assert set(cited) <= known, (story["story_id"], set(cited) - known)
        assert story["target_incident"] in known


def test_the_incidents_to_investigate_do_not_contain_the_answer():
    incidents = {item["incident_id"]: item for item in load_json("incidents.json")}
    for story in json.loads((EVALUATION / "story_definitions.json").read_text(encoding="utf-8")):
        incident = incidents[story["target_incident"]]
        text = " ".join([incident["title"], incident["description"], *incident["symptoms"]]).lower()
        assert not [word for word in CAUSE_WORDS if word in text], story["story_id"]
        assert incident["rca_required"]


def test_past_rcas_are_older_than_their_incidents_and_have_the_diagram_sections():
    incidents = {item["incident_id"]: item for item in load_json("incidents.json")}
    for path in RCA_FOLDER.glob("*.md"):
        text = path.read_text(encoding="utf-8")
        completed = next(line for line in text.splitlines() if line.startswith("**Completion Date:**")).split(":", 1)[1]
        linked = next(line for line in text.splitlines() if line.startswith("**Linked Incidents:**")).split(":", 1)[1]
        for incident_id in [item.strip(" *") for item in linked.split(",")]:
            assert incidents[incident_id]["detected_at"] < completed.strip(" *"), path.stem
        for section in ("## Summary", "## Root Cause", "## Five Whys", "## Contributing Factors", "## Corrective Actions"):
            assert section in text, (path.stem, section)
