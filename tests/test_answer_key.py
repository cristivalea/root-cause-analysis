"""The answer key says what the first revision finds and what the expert's wider search adds: checked here
against the real evidence step, so the key cannot drift from what the investigation can see."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from rca import pipeline, storage
from rca.context import build_context
from rca.models import InvestigationGuidance

ROOT = Path(__file__).resolve().parents[1]
ANSWER_KEY = json.loads((ROOT / "data" / "evaluation" / "answer_key.json").read_text(encoding="utf-8"))
TOOL_KINDS = ("LOG-", "CHG-", "CI-")  # what the evidence step finds; RCAs and incidents come from the search


@pytest.fixture(scope="module")
def db(tmp_path_factory):
    path = tmp_path_factory.mktemp("key") / "rca.sqlite3"
    storage.load_sources(path, ROOT / "data" / "sources")
    return path


def found(db, story, guidance=None) -> set[str]:
    context, incidents = build_context(db, incident_id=story["target_incident"], guidance=guidance)
    state = {"db_path": str(db), "context": context, "incidents": incidents, "plan": SimpleNamespace(sources=[])}  # the step only names the sources in its trace
    return {cited for item in pipeline.tools(state)["evidence"] for cited in (item.citation, *item.related_ids)}


@pytest.mark.parametrize("story_id", [key for key, story in ANSWER_KEY.items() if story["expert_followup"]])
def test_the_wider_search_of_the_expert_finds_what_the_key_says(db, story_id):
    story = ANSWER_KEY[story_id]
    followup = story["expert_followup"]

    first, second = found(db, story), found(db, story, InvestigationGuidance.model_validate(followup["guidance"]))

    for citation in followup["expected_new_citations"]:
        assert citation not in first, f"{story_id}: {citation} is already found by the first revision"
        assert citation in second, f"{story_id}: {citation} is not found with {followup['guidance']}"


def test_every_tool_citation_the_key_expects_is_found_by_the_first_revision_or_explained(db):
    for story_id, story in ANSWER_KEY.items():
        missing = [item for item in story["expected_citations"] if item.startswith(TOOL_KINDS) and item not in found(db, story)]
        later = set((story["expert_followup"] or {}).get("expected_new_citations", []))
        unexplained = [item for item in missing if item not in later and item not in story["expected_outcome"]["note"]]
        assert not unexplained, f"{story_id}: {unexplained} is expected but neither found nor explained in the note"
