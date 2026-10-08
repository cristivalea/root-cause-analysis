"""Grouping suggestions: right often enough on the mock data, explained, and never repeated once rejected.

These tests read the embeddings stored in ChromaDB (scripts/ingest_chroma.py), without calling Ollama.
"""

import json
from pathlib import Path

import pytest

from rca import problems, rag, storage, suggestions

ROOT = Path(__file__).resolve().parents[1]
TRUTH = {item["incident_id"]: item for item in json.loads(
    (ROOT / "data" / "evaluation" / "grouping_truth.json").read_text(encoding="utf-8"))}

pytestmark = pytest.mark.skipif(not (rag.ROOT / "chroma_db").exists(), reason="run scripts/ingest_chroma.py first")


@pytest.fixture(scope="module")
def embeddings():
    return suggestions.load_embeddings()


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "rca.sqlite3"
    storage.load_sources(path, ROOT / "data" / "sources")
    return path


def belong_together(first: str, second: str) -> bool:
    """The answer key: the same failure family of the generator, or the same problem."""
    a, b = TRUTH[first], TRUTH[second]
    return bool((a["family"] and a["family"] == b["family"]) or (a["problem_id"] and a["problem_id"] == b["problem_id"]))


def test_the_first_suggestion_is_right_for_almost_every_incident_in_no_problem(db, embeddings):
    found = suggestions.suggest_all(db, embeddings)

    right = sum(1 for incident_id, item in found.items() if item and belong_together(incident_id, item.incident_ids[0]))
    assert len(found) > 400
    # measured: 443 of 445. The two others are the STORY-002 look-alikes, which the answer key leaves alone
    # but which the code puts with incidents of the same CMDB item and the same kind of cause.
    assert right / len(found) >= 0.99


def test_the_look_alikes_of_the_payment_problem_are_not_proposed_for_it(db, embeddings):
    payment_problem = storage.get_problem_id_for_incident(db, "INC-2026-00482")

    for look_alike in ("INC-2026-00371", "INC-2026-00411"):
        item = suggestions.suggest(look_alike, db, embeddings)
        assert item is None or item.problem_id != payment_problem


def test_an_incident_of_an_open_problem_is_proposed_for_it_with_its_reasons(db, embeddings):
    payment_problem = storage.get_problem_id_for_incident(db, "INC-2026-00482")
    problems.detach_incident(payment_problem, "INC-2026-00857", "pm", "Test.", db_path=db)

    item = suggestions.suggest("INC-2026-00857", db, embeddings)

    assert (item.kind, item.problem_id, item.incident_ids) == ("open_problem", payment_problem, ["INC-2026-00482"])
    text = " ".join(item.reasons)
    assert "Same service: Payment API." in text and "Same CMDB item" in text
    assert "ConnectionTimeout" in text  # the same error type in the logs around both incidents


def test_an_incident_like_those_of_a_closed_problem_is_proposed_as_a_possible_recurrence(db, embeddings):
    found = [item for item in suggestions.suggest_all(db, embeddings).values() if item and item.kind == "closed_problem"]

    assert found
    assert all("may have come back after the fix" in item.reasons[-1] for item in found)
    assert all(storage.get_problem(db, item.problem_id).status == "Closed" for item in found)


def test_a_rejected_suggestion_is_not_proposed_again(db, embeddings):
    first = next(item for item in suggestions.suggest_all(db, embeddings).values() if item and item.kind == "new_problem")

    problems.reject_suggestion(first.incident_id, first.incident_ids, "pm", db_path=db)
    again = suggestions.suggest(first.incident_id, db, embeddings)

    assert again is None or not set(again.incident_ids) & set(first.incident_ids)


def test_an_incident_marked_as_needing_no_problem_gets_no_suggestion_and_is_suggested_to_no_one(db, embeddings):
    first = next(item for item in suggestions.suggest_all(db, embeddings).values() if item and item.kind == "new_problem")
    partner = first.incident_ids[0]

    problems.dismiss_incident(partner, "pm", "Known vendor issue.", db_path=db)
    found = suggestions.suggest_all(db, embeddings)

    assert partner not in found
    assert all(partner not in item.incident_ids for item in found.values() if item)


def test_proposed_problems_are_groups_of_at_least_three_incidents_in_no_problem(db, embeddings):
    groups = suggestions.proposed_problems(db, embeddings)

    assert groups
    owned = {link.incident_id for problem in problems.list_problems(db_path=db) for link in problem.incidents}
    for group in groups:
        assert len(group) >= suggestions.MIN_PROPOSED_PROBLEM
        assert not set(group) & owned
        assert len({storage.get_incident(db, item).service for item in group}) == 1
