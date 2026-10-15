"""The KPIs of rca/kpis.py on RCAs built by hand, each with a known outcome, so every formula is checked
against numbers worked out in advance (docs/ui-ux-rebuild/kpi-plan.md)."""

import json
from datetime import date, timedelta
from pathlib import Path

import pytest

from rca import kpis, problems, storage
from rca.models import RCARecord
from rca_helpers import make_rca

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "rca.sqlite3"
    storage.load_sources(path, ROOT / "data" / "sources")
    return path


@pytest.fixture
def template():
    return RCARecord.model_validate(json.loads((ROOT / "tests" / "fixtures" / "sample_rca_record.json").read_text(encoding="utf-8")))


@pytest.fixture
def five_cases(db, template):
    """A: approved at once. B: more details, revision 2, approved. C: rejected. D: refused by the checks in
    every attempt. E: stopped on a technical error. One open problem each (one RCA at a time per problem)."""
    open_problems = [item.problem_id for item in problems.list_problems("Open", db_path=db)][:5]
    steps = {
        "A": ("draft", "submit", "approve"),
        "B": ("draft", "submit", "more", "next", "draft", "submit", "approve"),
        "C": ("draft", "submit", "reject"),
        "D": ("escalate",),
        "E": ("fail",),
    }
    return {name: make_rca(db, problem_id, template, *walk) for (name, walk), problem_id in zip(steps.items(), open_problems)}


def test_kpi1_counts_the_real_steps_of_people_against_the_11_manual_ones(db, five_cases):
    found = kpis.compute(db)["kpi1_interactions"]

    # A: start + send + decision + read = 4; B: start + 2 sends + 2 decisions + 1 new revision + read = 7; C: 4
    assert found["finished"] == 3
    assert found["average_interactions"] == 5.0
    assert found["reduction_percent"] == round((11 - 5) / 11 * 100, 1)  # 54.5
    assert (found["happy_path"], found["with_more_steps"]) == (2, 1)
    assert found["design_reduction_percent"] == 63.64  # the calculation of docs/KPIS.md, kept as the reference


def test_kpi2_counts_the_runs_that_ended_with_an_analysis_without_a_person(db, five_cases):
    found = kpis.compute(db)["kpi2_autonomy"]

    # runs: A 1, B 2, C 1, D 1, E 1 = 6; with an analysis: A, B twice, C = 4; D refused by the checks, E failed
    assert (found["runs"], found["autonomous"], found["refused_by_checks"], found["failed"]) == (6, 4, 1, 1)
    assert found["rate_percent"] == 66.7
    assert found["design_percent"] == 62.5


def test_kpi3_takes_the_expert_as_the_judge(db, five_cases):
    found = kpis.compute(db)["kpi3_accuracy"]

    # decided for good: A, B (validated with the first hypothesis), C (rejected); D and E were never decided
    assert (found["decided"], found["top1"], found["topk"]) == (3, 2, 2)
    assert found["top1_percent"] == found["topk_percent"] == 66.7


def test_kpi4_groups_every_decision_by_the_confidence_of_the_first_hypothesis(db, five_cases, template):
    found = kpis.compute(db)["kpi4_calibration"]
    level = template.hypotheses[0].confidence

    # decisions: A approve, B more details then approve, C reject = 4, all on revisions of the same template
    assert found["decisions"] == 4
    row = next(item for item in found["levels"] if item["level"] == level)
    assert (row["decisions"], row["approved"], row["approved_percent"]) == (4, 2, 50.0)
    assert found["ordered"] is None  # one level only: nothing to compare


def test_the_period_and_the_overview(db, five_cases):
    everything = kpis.compute(db)
    assert everything["overview"]["rcas_started"] == 5
    assert everything["overview"]["decided_count"] == 3
    assert everything["weeks"][0]["started"] == 5

    tomorrow = date.today() + timedelta(days=1)
    later = kpis.compute(db, start=tomorrow)
    assert later["overview"]["rcas_started"] == 0
    assert later["kpi3_accuracy"]["top1_percent"] is None  # no case: no number, never a 0 % made up


def test_a_benchmark_counts_only_when_the_current_scripts_wrote_it(db, tmp_path, monkeypatch):
    report = tmp_path / "kpi_accuracy_report.json"
    monkeypatch.setattr(kpis, "ACCURACY_REPORT", report)
    assert kpis.compute(db)["benchmark"]["accuracy"]["status"] == "not_measured"

    report.write_text(json.dumps({"timestamp": "2026-10-06T13:02:12Z", "top1_accuracy_percent": 7.69}), encoding="utf-8")
    assert kpis.compute(db)["benchmark"]["accuracy"]["status"] == "outdated"

    report.write_text(json.dumps({"script_version": kpis.BENCHMARK_SCRIPT_VERSION, "timestamp": "2026-10-16T09:00:00Z",
                                  "agent_model": "openai/gpt-oss-120b", "judge_model": "llama-3.3-70b-versatile",
                                  "selected": 13, "evaluated": 12, "run_errors": ["INC-2026-00110"],
                                  "top1_accuracy_percent": 66.67, "topk_accuracy_percent": 91.67}), encoding="utf-8")
    found = kpis.compute(db)["benchmark"]["accuracy"]
    assert found["status"] == "measured"
    assert found["values"] == {"top1_percent": 66.67, "topk_percent": 91.67}
    assert found["excluded"] == ["INC-2026-00110"]


def test_the_route_is_read_only_and_for_the_problem_manager(db, five_cases, monkeypatch):
    fastapi_testclient = pytest.importorskip("fastapi.testclient")
    import api

    monkeypatch.setattr(api, "DB_PATH", db)
    user = {"username": "pm", "role": "problem_manager", "active": True}
    api.app.dependency_overrides[api.get_current_user] = lambda: user
    try:
        http = fastapi_testclient.TestClient(api.app)
        answer = http.get("/api/v1/kpis")
        assert answer.status_code == 200 and answer.json()["kpi3_accuracy"]["decided"] == 3
        assert http.get("/api/v1/kpis?date_from=yesterday").status_code == 400
        user["role"] = "technical_expert"
        assert http.get("/api/v1/kpis").status_code == 403
    finally:
        api.app.dependency_overrides.clear()
