"""The investigation context is built by code from the problem, with the rules of P.1."""

from datetime import datetime, timedelta
from pathlib import Path

import pytest

from rca import storage
from rca.context import build_context, merge_guidance
from rca.models import InvestigationGuidance

ROOT = Path(__file__).resolve().parents[1]


def at(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


@pytest.fixture(scope="module")
def db_path(tmp_path_factory):
    path = tmp_path_factory.mktemp("context") / "rca.sqlite3"
    storage.load_sources(path, ROOT / "data" / "sources")
    return path


def test_an_incident_of_a_problem_brings_the_whole_problem(db_path):
    context, incidents = build_context(db_path, incident_id="INC-2026-00482")

    assert context.problem_id == storage.get_problem_id_for_incident(db_path, "INC-2026-00482")
    assert context.incident_ids == ["INC-2026-00482", "INC-2026-00857"]
    assert [item.incident_id for item in incidents] == context.incident_ids
    assert context.reference_incident_id == "INC-2026-00857"  # the most recent
    assert context.services == ["Payment API"]
    assert context.sources["log_windows"].startswith("rule")


def test_starting_from_the_problem_gives_the_same_context(db_path):
    from_incident, _ = build_context(db_path, incident_id="INC-2026-00482")
    from_problem, _ = build_context(db_path, problem_id=from_incident.problem_id)

    assert from_problem == from_incident


def test_one_log_window_around_every_incident_and_one_change_window_from_7_days_before_the_first(db_path):
    context, _ = build_context(db_path, incident_id="INC-2026-00101")  # STORY-001: 5 Mondays, March to July

    assert [window.incident_id for window in context.log_windows] == context.incident_ids
    first = context.log_windows[0]
    assert first.start == at("2026-03-16T06:48:00Z") - timedelta(hours=2)
    assert first.end == at("2026-03-16T06:48:00Z") + timedelta(hours=1)
    assert context.change_window.start == at("2026-03-16T06:48:00Z") - timedelta(days=7)
    assert context.change_window.end == at("2026-07-27T08:15:00Z")  # the resolution of the last incident
    # the change that introduced the problem, on 11 March, is inside the change window
    assert context.change_window.start <= at("2026-03-11T18:00:00Z") <= context.change_window.end


def test_the_related_services_come_from_the_cmdb(db_path):
    context, _ = build_context(db_path, incident_id="INC-2026-00101")

    assert "Payroll Service" not in context.related_services
    assert context.related_services  # payroll-postgresql lives in the Payroll Service, the cluster in Kubernetes


def test_an_incident_without_a_problem_is_investigated_alone(db_path):
    lonely = next(item for item in storage.list_incidents(db_path)
                  if storage.get_problem_id_for_incident(db_path, item.incident_id) is None)

    context, incidents = build_context(db_path, incident_id=lonely.incident_id)

    assert context.problem_id is None
    assert context.incident_ids == [lonely.incident_id] and incidents == [lonely]


def test_unknown_ids_stop_with_an_error(db_path):
    with pytest.raises(ValueError, match="INC-2099-00001"):
        build_context(db_path, incident_id="INC-2099-00001")
    with pytest.raises(ValueError, match="PRB-2099-00001"):
        build_context(db_path, problem_id="PRB-2099-00001")


def test_the_guidance_of_the_problem_manager_widens_the_search_and_is_recorded(db_path):
    guidance = InvestigationGuidance(notes="Check the egress proxy.", extra_services=["Network Services"],
                                     change_window_days=30, log_hours_before=24)

    context, _ = build_context(db_path, incident_id="INC-2026-00468", guidance=guidance)  # STORY-011

    assert context.services == ["Payment API", "Network Services"]
    assert context.notes == "Check the egress proxy."
    detected = at("2026-09-08T10:20:00Z")
    assert context.log_windows[0].start == detected - timedelta(hours=24)
    assert context.change_window.start == detected - timedelta(days=30)
    assert "Problem Manager" in context.sources["services"]
    assert context.sources["change_window"].startswith("Problem Manager: 30 days")
    assert context.sources["notes"] == "Problem Manager"


def test_without_guidance_the_rules_apply_and_nothing_is_attributed_to_the_problem_manager(db_path):
    context, _ = build_context(db_path, incident_id="INC-2026-00468")

    assert context.notes is None
    assert not any("Problem Manager" in value for value in context.sources.values())


def test_a_service_the_cmdb_does_not_know_is_refused(db_path):
    with pytest.raises(ValueError, match="Load Balancer"):
        build_context(db_path, incident_id="INC-2026-00468", guidance=InvestigationGuidance(extra_services=["Load Balancer"]))


def test_the_windows_of_the_guidance_have_limits():
    with pytest.raises(ValueError):
        InvestigationGuidance(change_window_days=3)  # narrower than the rule
    with pytest.raises(ValueError):
        InvestigationGuidance(log_hours_before=500)


def test_the_expert_widens_the_guidance_of_the_previous_revision_and_never_narrows_it():
    earlier = InvestigationGuidance(notes="Check the pool.", extra_services=["Network Services"], change_window_days=30)
    added = InvestigationGuidance(extra_services=["Kubernetes Platform"], change_window_days=14, log_hours_before=24)

    merged = merge_guidance(earlier, added)

    assert merged.notes == "Check the pool."
    assert merged.extra_services == ["Network Services", "Kubernetes Platform"]
    assert merged.change_window_days == 30  # the expert asked for less than before: the wider one stays
    assert merged.log_hours_before == 24
    assert merge_guidance(None, added) == added and merge_guidance(earlier, None) == earlier


def test_the_request_of_the_expert_is_part_of_the_context(db_path):
    context, _ = build_context(db_path, incident_id="INC-2026-00491", expert_request="Search the last 7 days of logs.")

    assert context.expert_request == "Search the last 7 days of logs."
    assert context.sources["expert_request"].startswith("Technical Expert")
