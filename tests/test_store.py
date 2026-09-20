"""Tests for rca.store: RCAs are saved in SQLite, read back unchanged, updated and listed."""

import json
from pathlib import Path

from rca import store
from rca.models import RCARecord
from rca.store import get_rca, list_rcas, next_rca_id, save_rca

FIXTURES = Path(__file__).parent / "fixtures"


def sample_record() -> RCARecord:
    data = json.loads((FIXTURES / "sample_rca_record.json").read_text(encoding="utf-8"))
    return RCARecord.model_validate(data)


def test_saved_rca_is_read_back_unchanged(tmp_path):
    db_path = tmp_path / "rca.sqlite3"
    record = sample_record()

    save_rca(record, db_path)

    assert get_rca(record.rca_id, db_path) == record
    assert get_rca("RCA-2099-00001", db_path) is None


def test_saving_again_updates_the_same_rca(tmp_path):
    db_path = tmp_path / "rca.sqlite3"
    record = sample_record()
    save_rca(record, db_path)

    save_rca(record.model_copy(update={"status": "REJECTED"}), db_path)

    assert get_rca(record.rca_id, db_path).status == "REJECTED"
    assert len(list_rcas(db_path=db_path)) == 1


def test_rcas_are_listed_by_status(tmp_path):
    db_path = tmp_path / "rca.sqlite3"
    pending = sample_record()
    escalated = pending.model_copy(update={"rca_id": "RCA-2026-00138", "status": "ESCALATED"})
    save_rca(pending, db_path)
    save_rca(escalated, db_path)

    assert [item.rca_id for item in list_rcas("PENDING_REVIEW", db_path)] == ["RCA-2026-00137"]
    assert len(list_rcas(db_path=db_path)) == 2


def test_new_rca_ids_continue_the_numbering_of_the_year(tmp_path):
    db_path = tmp_path / "rca.sqlite3"

    assert next_rca_id(2026, db_path) == "RCA-2026-00001"

    save_rca(sample_record(), db_path)  # RCA-2026-00137

    assert next_rca_id(2026, db_path) == "RCA-2026-00138"
    assert next_rca_id(2027, db_path) == "RCA-2027-00001"


# ---- The review decisions and the case they belong to ----


def test_asking_for_more_detail_is_recorded_as_a_decision(tmp_path):
    """The old behaviour lost who asked and what for; the request is part of the case."""
    db = tmp_path / "rca.sqlite3"
    record = sample_record()
    record.status = "PENDING_REVIEW"
    store.save_rca(record, db_path=db)

    updated = store.apply_review(
        record.rca_id, "Ana", "REQUEST_MORE_DETAILS", "Check the connection pool settings.",
        db_path=db, requested_checks=["connection pool size"],
    )

    assert updated.status == "MORE_DETAILS_REQUESTED"
    assert updated.review is not None
    assert updated.review.decision == "REQUEST_MORE_DETAILS"
    assert updated.review.reviewer == "Ana"
    assert updated.review.requested_checks == ["connection pool size"]
    assert updated.final_root_cause is None


def test_the_older_name_of_that_decision_still_works(tmp_path):
    db = tmp_path / "rca.sqlite3"
    record = sample_record()
    record.status = "PENDING_REVIEW"
    store.save_rca(record, db_path=db)

    updated = store.apply_review(record.rca_id, "Ana", "REANALYZE", "More detail please.", db_path=db)
    assert updated.review.decision == "REQUEST_MORE_DETAILS"
    assert updated.status == "MORE_DETAILS_REQUESTED"


def test_a_second_investigation_joins_the_case_instead_of_replacing_it(tmp_path):
    db = tmp_path / "rca.sqlite3"
    first = sample_record()
    first.status = "REJECTED"
    store.save_rca(first, db_path=db)

    second = sample_record()
    second.rca_id = "RCA-2026-00099"
    store.save_rca(second, db_path=db)

    linked = store.start_next_cycle(first.rca_id, second.rca_id, db_path=db)

    assert linked.case == first.rca_id
    assert linked.cycle == 2
    assert linked.parent_rca_id == first.rca_id
    assert store.get_rca(first.rca_id, db_path=db) is not None  # nothing was overwritten

    case = store.list_case(first.rca_id, db_path=db)
    assert [item.rca_id for item in case] == [first.rca_id, second.rca_id]


def test_analyses_are_grouped_into_cases(tmp_path):
    db = tmp_path / "rca.sqlite3"
    first = sample_record()
    store.save_rca(first, db_path=db)
    second = sample_record()
    second.rca_id = "RCA-2026-00099"
    store.save_rca(second, db_path=db)
    store.start_next_cycle(first.rca_id, second.rca_id, db_path=db)

    alone = sample_record()
    alone.rca_id = "RCA-2026-00077"
    alone.incident_id = "INC-2026-00101"
    store.save_rca(alone, db_path=db)

    cases = store.list_cases(db_path=db)
    assert len(cases) == 2
    assert {len(case) for case in cases} == {1, 2}
