#!/usr/bin/env python3
"""Validate mock source JSON and load it into SQLite.

    python scripts/load_sources_sqlite.py              # add and update the sources
    python scripts/load_sources_sqlite.py --reset      # empty the source tables first
    python scripts/load_sources_sqlite.py --reset-app  # also start the application data again

The sources (incidents, logs, changes, CMDB) and the work done in the application (problems, their
history, the RCAs) are kept apart. --reset reloads only the sources: the problems and the RCAs stay.
The problems of data/sources/problems.json are loaded only into a database that has none yet.
--reset-app empties the problems, their history and the RCAs together, after writing a copy of the
whole database to data/backups/, and loads the problems of the source data again.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from rca.storage import clear_application_state, load_sources

DEFAULT_DB = ROOT / "data" / "rca_sources.sqlite3"
DEFAULT_SOURCES = ROOT / "data" / "sources"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Load validated mock source data into SQLite.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="SQLite database path")
    parser.add_argument("--sources", type=Path, default=DEFAULT_SOURCES, help="Directory containing source JSON files")
    parser.add_argument("--reset", action="store_true",
                        help="empty the source tables first (the problems and the RCAs are kept)")
    parser.add_argument("--reset-app", action="store_true",
                        help="also empty the problems, their history and the RCAs (a copy of the database is kept)")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.reset_app:
        copy = clear_application_state(args.db)
        if copy:
            print(f"Copy of the database before the reset: {copy}")
    seeded = load_sources(args.db, args.sources, reset=args.reset or args.reset_app)
    print(f"Loaded validated source data into {args.db}")
    print("The problems of the source data were loaded." if seeded
          else "The problems of the application were kept (use --reset-app to start them again).")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # pragma: no cover
        raise SystemExit(f"Error: {exc}")
