#!/usr/bin/env python3
"""Query the project ChromaDB collections using the shared RCA RAG layer."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MODEL = "nomic-embed-text"
sys.path.insert(0, str(ROOT))

from rca.rag import DEFAULT_MAX_DISTANCE, query_collection


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Query the ChromaDB collections used by this project.")
    parser.add_argument("--collection", choices=["historical_incidents", "historical_rcas"], required=True)
    parser.add_argument("--query", required=True, help="Natural-language query to search for")
    parser.add_argument("--limit", type=int, default=5, help="Maximum number of results to return")
    parser.add_argument("--where", default=None, help="Optional metadata filter in JSON format, e.g. '{\"service\": \"Payroll Service\"}'")
    parser.add_argument("--service", default=None, help="Filter results by service without JSON quoting")
    parser.add_argument("--before", default=None, help="Only return records older than this ISO timestamp")
    parser.add_argument("--max-distance", type=float, default=DEFAULT_MAX_DISTANCE, help="Maximum cosine distance to keep")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Embedding model used by Ollama")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    where_filter = json.loads(args.where) if args.where else None
    if args.service:
        if where_filter is not None:
            raise ValueError("Use either --where or --service, not both.")
        where_filter = {"service": args.service}
    before_timestamp = None
    if args.before:
        before_timestamp = int(datetime.fromisoformat(args.before.replace("Z", "+00:00")).timestamp())
    results = query_collection(
        args.collection,
        args.query,
        limit=args.limit,
        where=where_filter,
        before_timestamp=before_timestamp,
        max_distance=args.max_distance,
        model=args.model,
    )
    print(json.dumps(results, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # pragma: no cover
        raise SystemExit(f"Error: {exc}")
