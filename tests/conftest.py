"""Shared test data: the Payment API evidence ledger (INC-2026-00482).

The ledger is built from the real tools on the mock data, with the same functions as the pipeline.
The historical evidence is written by hand, so these tests need neither Ollama nor the Historical RCA Agent.
"""

from datetime import datetime
from pathlib import Path

import pytest

from rca import storage
from rca.evidence import EvidenceLedger, add_changes, add_dependencies, add_log_groups
from rca.tools import find_changes, find_dependencies, find_logs

ROOT = Path(__file__).resolve().parents[1]
INCIDENT_ID = "INC-2026-00482"
DETECTED_AT = datetime.fromisoformat("2026-07-14T14:32:00+00:00")
# The window chosen by the Investigation Planner for this incident (step 8).
WINDOW_START = datetime.fromisoformat("2026-07-14T10:00:00+00:00")
WINDOW_END = datetime.fromisoformat("2026-07-14T15:17:00+00:00")


def build_payment_ledger(db_path: Path) -> EvidenceLedger:
    """The ledger the pipeline builds for INC-2026-00482: tool results first, then history."""
    ledger = EvidenceLedger()
    add_log_groups(ledger, find_logs("Payment API", WINDOW_START, WINDOW_END, db_path=db_path), DETECTED_AT)
    add_changes(ledger, find_changes(["Payment API"], WINDOW_START, WINDOW_END, db_path=db_path), DETECTED_AT)
    add_dependencies(ledger, find_dependencies("Payment API", db_path=db_path))

    ledger.add(
        "HISTORICAL_RCA",
        "RCA-2025-00114",
        "Past Payment API RCA: intermittent HTTP 500 errors and latency above 5 seconds after a release. "
        "Root cause was database connection pool exhaustion from unclosed SQL sessions in the payment "
        "retry handler. Mitigated by restarting pods and increasing the maximum pool size.",
        "RCA-2025-00114",
        datetime.fromisoformat("2025-11-20T14:00:00+00:00"),
    )
    ledger.add(
        "HISTORICAL_INCIDENT",
        "INC-2025-00401",
        "Past Payment API incident: card authorisation requests slow during retry bursts, "
        "intermittent HTTP 500 responses and database timeout warnings.",
        "INC-2025-00401",
        datetime.fromisoformat("2025-11-20T14:32:00+00:00"),
    )
    return ledger


@pytest.fixture(scope="session")
def payment_ledger(tmp_path_factory):
    db_path = tmp_path_factory.mktemp("payment_ledger") / "sources.sqlite3"
    storage.load_sources(db_path, ROOT / "data" / "sources")
    return build_payment_ledger(db_path)
