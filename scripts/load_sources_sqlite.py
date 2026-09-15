#!/usr/bin/env python3
"""Validate mock source JSON and load it into SQLite."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from rca.storage import load_sources

DEFAULT_DB = ROOT / "data" / "rca_sources.sqlite3"
DEFAULT_SOURCES = ROOT / "data" / "sources"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Load validated mock source data into SQLite.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="SQLite database path")
    parser.add_argument("--sources", type=Path, default=DEFAULT_SOURCES, help="Directory containing source JSON files")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    load_sources(args.db, args.sources)
    print(f"Loaded validated source data into {args.db}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # pragma: no cover
        raise SystemExit(f"Error: {exc}")
