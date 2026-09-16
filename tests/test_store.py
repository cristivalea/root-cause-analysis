"""Tests for rca.store: RCAs are saved in SQLite, read back unchanged, updated and listed."""

import json
from pathlib import Path

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
