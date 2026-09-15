#!/usr/bin/env python3
"""Load project data into ChromaDB using the app-level RAG utilities."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
DEFAULT_MODEL = "nomic-embed-text"
sys.path.insert(0, str(ROOT))

from rca.rag import build_incident_records, ensure_ollama_model, load_rca_records, upsert_records


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ingest project data into ChromaDB via the RCA RAG layer.")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Ollama embedding model name")
    parser.add_argument("--incidents", type=Path, default=DATA_DIR / "sources" / "incidents.json", help="Path to the real incident dataset")
    parser.add_argument("--rca-folder", type=Path, default=DATA_DIR / "knowledge_base" / "rcas", help="Folder containing RCA markdown files")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    ensure_ollama_model(args.model)

    incidents = build_incident_records(args.incidents)
    rca_docs = load_rca_records(args.rca_folder)

    upsert_records(incidents, "historical_incidents", model=args.model)
    upsert_records(rca_docs, "historical_rcas", model=args.model)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # pragma: no cover
        raise SystemExit(f"Error: {exc}")
