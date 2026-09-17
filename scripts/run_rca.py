#!/usr/bin/env python3
"""Run one RCA investigation from the terminal and save the draft RCA in SQLite.

Usage:
    python scripts/run_rca.py INC-2026-00482

Before the first run: the SQLite database (scripts/load_sources_sqlite.py), the ChromaDB index
(scripts/ingest_chroma.py, with Ollama running) and GROQ_API_KEY in .env.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from rca.config import DB_PATH, GROQ_MODEL
from rca.models import InvestigationStep, RCARecord
from rca.pipeline import DEFAULT_OWNER, run_investigation


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run one RCA investigation and save the draft RCA.")
    parser.add_argument("incident_id", help="Incident to investigate, e.g. INC-2026-00482")
    parser.add_argument("--owner", default=DEFAULT_OWNER, help="Who started the RCA")
    return parser.parse_args()


def print_step(step: InvestigationStep) -> None:
    print(f"[{step.finished_at:%H:%M:%S}] {step.name}: {step.summary}", flush=True)
    for problem in step.details.get("problems", []):
        print(f"           - {problem[:300]}", flush=True)


def print_record(record: RCARecord) -> None:
    print(f"\n{record.rca_id} for {record.incident_id}: {record.status} in {record.duration_seconds:.0f} s")
    print(f"\n{record.investigation_summary}")

    if record.evidence:
        print("\nEvidence ledger:")
        for item in record.evidence:
            print(f"  {item.evidence_id}  {item.type:<19} {item.citation}")

    for hypothesis in record.hypotheses:
        print(f"\n{hypothesis.hypothesis_id}  {hypothesis.confidence} ({hypothesis.confidence_points} points)")
        print(f"  Candidate root cause: {hypothesis.candidate_root_cause}")
        print(f"  Supporting: {', '.join(hypothesis.supporting_evidence)}")
        print(f"  Contradicting: {', '.join(hypothesis.contradicting_evidence) or '-'}")
        for reason in hypothesis.confidence_reasons:
            print(f"  - {reason}")

    if record.weakly_supported:
        print("\nWeakly supported: no hypothesis is above LOW. Request more evidence before approving.")
    if record.not_checked:
        print("\nNot checked:")
        for item in record.not_checked:
            print(f"  - {item}")

    print(f"\nSaved in {DB_PATH}. final_root_cause stays empty until a Technical Expert approves.")


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")  # the model sometimes writes characters the Windows console cannot show
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    args = parse_args()
    print(f"Investigating {args.incident_id} with {GROQ_MODEL}\n", flush=True)
    record = run_investigation(args.incident_id, owner=args.owner, on_step=print_step)
    print_record(record)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # pragma: no cover
        raise SystemExit(f"Error: {exc}")
