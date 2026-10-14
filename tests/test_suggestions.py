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


def covered(found) -> list[str]:
    return [incident_id for item in found for incident_id in item.incident_ids]


def test_every_incident_in_no_problem_is_in_exactly_one_proposal(db, embeddings):
    an_incident_for_an_open_problem(db)  # an incident removed from a problem is proposed again too

    found = suggestions.proposals(db, embeddings)

    unassigned = sorted(item.incident_id for item in problems.unassigned_incidents(db))
    assert sorted(covered(found)) == unassigned  # every one, and none twice
    assert "INC-2026-00857" in covered(found)
    assert {"group", "attach"} <= {item.kind for item in found} <= {"group", "attach", "single"}

def test_proposed_groups_are_alike_incidents_in_no_problem_of_one_service(db, embeddings):
    groups = [item.incident_ids for item in suggestions.proposals(db, embeddings) if item.kind == "group"]

    assert groups
    owned = {link.incident_id for problem in problems.list_problems(db_path=db) for link in problem.incidents}
    for group in groups:
        assert len(group) >= suggestions.MIN_GROUP
        assert not set(group) & owned
        assert len({storage.get_incident(db, item).service for item in group}) == 1


def test_the_incidents_that_may_be_added_to_a_problem_come_with_their_similarity(db, embeddings):
    """An incident removed from a problem is eligible again, and it is the most alike of the candidates."""
    payment_problem = storage.get_problem_id_for_incident(db, "INC-2026-00482")
    problems.detach_incident(payment_problem, "INC-2026-00857", "pm", "Test.", db_path=db)

    found = suggestions.candidates_for_problem(payment_problem, db, embeddings, limit=500)

    ids = [item.incident_id for item in found]
    assert "INC-2026-00857" in ids and "INC-2026-00482" not in ids  # only incidents in no problem
    first = found[0]
    assert (first.incident_id, first.closest_incident_id, first.alike) == ("INC-2026-00857", "INC-2026-00482", True)
    assert all(0 <= item.similarity <= 1 for item in found if item.similarity is not None)
    scores = [item.similarity for item in found if item.alike]
    assert scores == sorted(scores, reverse=True)  # the alike ones first, the closest first


# Proposed Problem Records (E6) ---------------------------------------------------------------------


def an_incident_for_an_open_problem(db):
    """The source data puts every incident of an open problem in it: one removed, with a reason, is proposed back."""
    payment_problem = storage.get_problem_id_for_incident(db, "INC-2026-00482")
    problems.detach_incident(payment_problem, "INC-2026-00857", "pm", "Test.", db_path=db)


def test_the_proposals_are_of_three_kinds_with_a_stable_key_an_explained_score_reasons_and_evidence(db, embeddings):
    an_incident_for_an_open_problem(db)
    found = suggestions.proposals(db, embeddings)

    kinds = {item.kind for item in found}
    assert {"group", "attach"} <= kinds
    for item in found:
        assert item.key == suggestions.proposal_key(item.kind, item.incident_ids, item.problem_id)
        assert item.reasons and item.evidence
        assert "not a probability" in item.score_meaning
        assert item.score is None or 0 <= item.score <= 1
    groups = [item for item in found if item.kind == "group"]
    assert all(len(item.incident_ids) >= suggestions.MIN_GROUP for item in groups)
    assert suggestions.proposals(db, embeddings) == found  # the same data gives the same proposals


def test_an_incident_is_proposed_only_for_an_open_problem_and_a_closed_one_is_named_as_a_recurrence(db, embeddings):
    found = suggestions.proposals(db, embeddings)
    statuses = {item.problem_id: item.status for item in problems.list_problems(db_path=db)}

    assert all(statuses[item.problem_id] in ("Open", "In investigation") for item in found if item.kind == "attach")
    recurrences = [item for item in found if item.recurrence_of]
    assert recurrences and all(statuses[item.recurrence_of] == "Closed" and item.kind in ("group", "single")
                               for item in recurrences)
    assert all(any(item.recurrence_of in reason for reason in item.reasons) for item in recurrences)


def test_an_incident_belongs_to_one_proposal_at_most(db, embeddings):
    seen = [incident_id for item in suggestions.proposals(db, embeddings) for incident_id in item.incident_ids]

    assert len(seen) == len(set(seen))


def test_the_incidents_of_a_rejected_group_come_back_on_their_own_the_major_ones_first(db, embeddings):
    group = next(item for item in suggestions.proposals(db, embeddings) if item.kind == "group" and any(
        storage.get_incident(db, incident_id).severity == "SEV-1" or storage.get_incident(db, incident_id).rca_required
        for incident_id in item.incident_ids))
    major = next(incident_id for incident_id in group.incident_ids
                 if storage.get_incident(db, incident_id).severity == "SEV-1"
                 or storage.get_incident(db, incident_id).rca_required)

    problems.reject_proposal(group.key, "group", group.incident_ids, "pm", reason="Different causes.", db_path=db)
    found = suggestions.proposals(db, embeddings)

    alone = {item.incident_ids[0]: item for item in found if item.kind == "single"}
    assert set(group.incident_ids) <= set(alone)
    assert all("was rejected" in alone[item].reasons[0] for item in group.incident_ids)  # it says why it is alone
    singles = [item for item in found if item.kind == "single"]
    majors = [suggestions._major(suggestions._World(db, embeddings), item) for item in singles]
    assert majors == sorted(majors, reverse=True)  # the major incidents first
    assert majors[[item.incident_ids[0] for item in singles].index(major)]
    assert sorted(covered(found)) == sorted(item.incident_id for item in problems.unassigned_incidents(db))


def test_no_incident_is_proposed_for_a_problem_in_investigation(db, embeddings):
    from rca import store

    an_incident_for_an_open_problem(db)
    payment_problem = storage.get_problem_id_for_incident(db, "INC-2026-00482")
    assert any(item.kind == "attach" and item.problem_id == payment_problem for item in suggestions.proposals(db, embeddings))

    store.begin_rca(payment_problem, "pm", None, db_path=db)
    found = suggestions.proposals(db, embeddings)

    assert not any(item.kind == "attach" and item.problem_id == payment_problem for item in found)
    assert "INC-2026-00857" in covered(found)  # it is proposed another way meanwhile

def test_a_rejected_proposal_is_not_proposed_again(db, embeddings):
    an_incident_for_an_open_problem(db)
    found = suggestions.proposals(db, embeddings)
    group = next(item for item in found if item.kind == "group")
    attach = next(item for item in found if item.kind == "attach")

    problems.reject_proposal(group.key, "group", group.incident_ids, "pm", reason="Different causes.", db_path=db)
    problems.reject_proposal(attach.key, "attach", attach.incident_ids, "pm", attach.problem_id, db_path=db)

    found = suggestions.proposals(db, embeddings)
    keys = {item.key for item in found}
    assert group.key not in keys and attach.key not in keys
    assert set(group.incident_ids + attach.incident_ids) <= set(covered(found))  # still proposed, another way
    again = suggestions.suggest(attach.incident_ids[0], db, embeddings)  # that problem is not proposed for it again
    assert again is None or again.problem_id != attach.problem_id


def test_an_incident_removed_from_a_problem_is_proposed_again(db, embeddings):
    payment_problem = storage.get_problem_id_for_incident(db, "INC-2026-00482")
    problems.detach_incident(payment_problem, "INC-2026-00857", "pm", "Test.", db_path=db)

    found = [item for item in suggestions.proposals(db, embeddings) if "INC-2026-00857" in item.incident_ids]

    assert found and found[0].kind == "attach" and found[0].problem_id == payment_problem


def test_a_rejected_group_is_proposed_again_once_a_new_alike_incident_joins_it(db, embeddings):
    """The rejection holds for those incidents only: when another alike incident arrives the group is not the
    same any more, and it is proposed again with all of them. Simulated by rejecting the group without its
    newest incident, as it was before that incident arrived."""
    group = next(item for item in suggestions.proposals(db, embeddings) if item.kind == "group" and len(item.incident_ids) >= 3)
    earlier = group.incident_ids[:-1]
    problems.reject_proposal(suggestions.proposal_key("group", earlier), "group", earlier, "pm", db_path=db)

    found = suggestions.proposals(db, embeddings)

    assert group.key in {item.key for item in found}


def test_incidents_put_in_a_problem_manually_leave_the_proposals_they_were_in(db, embeddings):
    found = suggestions.proposals(db, embeddings)
    group = next(item for item in found if item.kind == "group")
    other = next(item for item in found if item.kind != "group" or item.key != group.key)
    chosen = [group.incident_ids[0], other.incident_ids[0]]

    problems.create_problem(chosen, "pm", reason="Same cause, known from the vendor.", manual=True, db_path=db)
    after = suggestions.proposals(db, embeddings)

    assert not set(chosen) & set(covered(after))
    assert group.key not in {item.key for item in after}  # the group is no longer the same
    assert sorted(covered(after)) == sorted(item.incident_id for item in problems.unassigned_incidents(db))
