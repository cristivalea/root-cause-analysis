"""The two KPI evaluation scripts, run end to end without any model: the investigation and the judge are
replaced by fixed answers. Checks what was fixed on 2026-10-15 (rca/kpi_evaluation.py): the exam runs on a
database built from the sources, never on the application's; the fallback models are off; the report says
which version wrote it and which models answered, so rca/kpis.py can trust it."""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

from rca import config, kpi_evaluation, kpis, storage
from rca.models import RCARecord

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = RCARecord.model_validate(json.loads((ROOT / "tests" / "fixtures" / "sample_rca_record.json").read_text(encoding="utf-8")))
MODEL = "groq:openai/gpt-oss-120b"


def load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def answer_with_models(record: RCARecord) -> RCARecord:
    trace = [step.model_copy(update={"details": {**(step.details or {}), "models": [MODEL]}}) for step in record.trace]
    return record.model_copy(update={"trace": trace})


def test_the_exam_database_is_built_from_the_sources_with_the_problems_of_the_stories_open():
    path = kpi_evaluation.fresh_database()

    assert path != config.DB_PATH and path.exists()
    assert storage.get_problem(path, "PRB-2026-00008").status == "Open"  # STORY-009, closed in the demo database
    assert storage.get_problem_id_for_incident(path, "INC-2026-00109") == "PRB-2026-00008"


@pytest.fixture
def fake_runs(monkeypatch):
    """The investigation: the sample analysis for every story, run on the database the script gives."""
    calls = []
    built = kpi_evaluation.fresh_database()
    monkeypatch.setattr(kpi_evaluation, "fresh_database", lambda: built)

    def run(**kwargs):
        calls.append(kwargs)
        assert config.LLM_FALLBACK is False  # one model for every story
        return answer_with_models(SAMPLE)

    return calls, run, built


def test_the_accuracy_script_runs_every_story_and_writes_a_report_the_kpi_page_trusts(fake_runs, tmp_path, monkeypatch):
    calls, run, built = fake_runs
    script = load("eval_kpi_accuracy")
    script.run_investigation = run
    script.OUTPUT_REPORT_PATH = tmp_path / "kpi_accuracy_report.json"
    asked = []

    def judge(instructions, user_input, schema, model=None):
        asked.append(model)
        return schema(is_match=True, reason="same component and mechanism")

    monkeypatch.setattr(script.judge, "ask_json", judge)
    monkeypatch.setattr(config, "LLM_FALLBACK", True)
    monkeypatch.setattr(sys, "argv", ["eval_kpi_accuracy.py", "--judge-model", "llama-3.3-70b-versatile"])

    script.main()

    report = json.loads(script.OUTPUT_REPORT_PATH.read_text(encoding="utf-8"))
    assert len(calls) == 13 and all(call["db_path"] == built for call in calls)  # never the application's database
    assert set(asked) == {"llama-3.3-70b-versatile"}
    assert report["script_version"] == kpi_evaluation.SCRIPT_VERSION
    assert (report["selected"], report["evaluated"]) == (13, 13)
    assert report["agent_models_used"] == [MODEL]
    assert report["judge_model"] == "llama-3.3-70b-versatile"
    assert report["top1_accuracy_percent"] == report["topk_accuracy_percent"] == 100.0

    monkeypatch.setattr(kpis, "ACCURACY_REPORT", script.OUTPUT_REPORT_PATH)
    benchmark = kpis.compute(built)["benchmark"]["accuracy"]
    assert benchmark["status"] == "measured" and benchmark["values"]["topk_percent"] == 100.0


def test_the_confidence_script_runs_every_story_on_the_exam_database(fake_runs, tmp_path, monkeypatch):
    calls, run, built = fake_runs
    script = load("eval_kpi_confidence")
    script.run_investigation = run
    script.EVAL_DB = None
    script.OUTPUT_REPORT_PATH = tmp_path / "kpi_confidence_report.json"
    monkeypatch.setattr(config, "LLM_FALLBACK", True)
    monkeypatch.setattr(sys, "argv", ["eval_kpi_confidence.py"])

    script.main()

    report = json.loads(script.OUTPUT_REPORT_PATH.read_text(encoding="utf-8"))
    answer_key = json.loads((ROOT / "data" / "evaluation" / "answer_key.json").read_text(encoding="utf-8"))
    level = SAMPLE.hypotheses[0].confidence
    expected = sum(1 for story in answer_key.values() if level in story["expected_outcome"]["acceptable_confidence"])
    assert len(calls) == 13 and all(call["db_path"] == built for call in calls)
    assert report["script_version"] == kpi_evaluation.SCRIPT_VERSION
    assert (report["selected"], report["evaluated"]) == (13, 13)
    assert report["overall_calibration_rate_percent"] == round(expected / 13 * 100, 2)
    assert report["agent_models_used"] == [MODEL]
