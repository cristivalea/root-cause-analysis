from pathlib import Path

from rca.rag import build_incident_records, load_rca_records

ROOT = Path(__file__).resolve().parents[1]


def test_real_incident_records_are_loaded_without_root_cause():
    incidents = build_incident_records(ROOT / "data" / "sources" / "incidents.json")

    assert incidents
    assert all("root_cause" not in item["text"].lower() for item in incidents)
    assert all(item["metadata"].get("source_type") == "incident" for item in incidents)


def test_rca_documents_include_metadata_for_filtering():
    rcas = load_rca_records(ROOT / "data" / "knowledge_base" / "rcas")

    assert rcas
    assert all(item["metadata"].get("service") for item in rcas)
    assert all(item["metadata"].get("completion_date") for item in rcas)
