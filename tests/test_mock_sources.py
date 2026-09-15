import json
from datetime import datetime
from pathlib import Path

from rca.models import Change, CIRelationship, ConfigItem, Incident, LogEntry

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
