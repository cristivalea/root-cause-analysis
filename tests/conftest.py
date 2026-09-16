"""Shared test data: the Payment API evidence ledger (INC-2026-00482).

The ledger is built from the real tools on the mock data, the way the pipeline will build it.
The historical evidence is written by hand until the Historical RCA Agent (step 9) is connected.
"""

from datetime import datetime
from pathlib import Path

import pytest

from rca import storage
from rca.evidence import EvidenceLedger
from rca.tools import find_changes, find_dependencies, find_logs

ROOT = Path(__file__).resolve().parents[1]
INCIDENT_ID = "INC-2026-00482"
DETECTED_AT = datetime.fromisoformat("2026-07-14T14:32:00+00:00")
# The window chosen by the Investigation Planner for this incident (step 8).
WINDOW_START = datetime.fromisoformat("2026-07-14T10:00:00+00:00")
WINDOW_END = datetime.fromisoformat("2026-07-14T15:17:00+00:00")


def minutes_before_detection(moment: datetime) -> str:
    minutes = round((DETECTED_AT - moment).total_seconds() / 60)
    return f"{minutes} minutes before detection" if minutes >= 0 else f"{-minutes} minutes after detection"


def build_payment_ledger(db_path: Path) -> EvidenceLedger:
    """The ledger the pipeline will build for INC-2026-00482: tool results first, then history."""
    ledger = EvidenceLedger()

    for group in find_logs("Payment API", WINDOW_START, WINDOW_END, db_path=db_path):
        first = group.examples[0]
        ledger.add(
            "LOG",
            ", ".join(group.hosts),
            f"{group.count} {group.level} log line(s) of type {group.error_type} between "
            f"{group.first_seen:%H:%M} and {group.last_seen:%H:%M} UTC, the first "
            f"{minutes_before_detection(group.first_seen)}. Example: \"{first.message}\"",
            first.log_id,
            group.first_seen,
        )

    for change in find_changes(["Payment API"], WINDOW_START, WINDOW_END, db_path=db_path):
        ledger.add(
            "CHANGE",
            change.change_id,
            f"{change.title} on {change.ci_id}: {change.description} Implemented at "
            f"{change.implemented_at:%H:%M} UTC, {minutes_before_detection(change.implemented_at)}.",
            change.change_id,
            change.implemented_at,
        )

    for dependency in find_dependencies("Payment API", db_path=db_path).dependencies:
        ledger.add(
            "CMDB",
            "CMDB",
            f"{dependency.component.name} ({dependency.component.ci_id}) {dependency.relationship_type} "
            f"{dependency.depends_on.name} ({dependency.depends_on.ci_id}, {dependency.depends_on.type}).",
            dependency.depends_on.ci_id,
        )

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
