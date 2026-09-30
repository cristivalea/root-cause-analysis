#!/usr/bin/env python3
"""Export the investigation graph — the same one LangGraph Studio draws — as a file.

Usage:
    python scripts/export_graph.py                  # both files, in diagrams/04-architecture/
    python scripts/export_graph.py --format mmd     # only the Mermaid text
    python scripts/export_graph.py --out-dir docs   # somewhere else

The graph is read from `rca/pipeline.py:graph`, which is what `langgraph.json` points Studio
at, so the picture always matches the pipeline that runs.

The Mermaid file is written offline. The PNG is drawn by mermaid.ink, a public service:
the node and edge names of the graph leave this machine for it. Nothing else is sent, and
`--format mmd` avoids the call altogether. If the call fails, the Mermaid file is still
written and the script says so.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

DEFAULT_OUT_DIR = ROOT / "diagrams" / "04-architecture"
NAME = "rca_graph"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export the LangGraph investigation graph.")
    parser.add_argument(
        "--format",
        choices=("mmd", "png", "both"),
        default="both",
        help="mmd is written locally; png is drawn by mermaid.ink (default: both)",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=DEFAULT_OUT_DIR,
        help=f"Where to write the files (default: {DEFAULT_OUT_DIR.relative_to(ROOT)})",
    )
    return parser.parse_args()


def _short(path: Path) -> str:
    """The path as it is written in the project, or in full when it is outside it."""
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def main() -> int:
    args = parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)

    from rca.pipeline import graph

    drawing = graph.get_graph()
    written: list[Path] = []

    if args.format in ("mmd", "both"):
        path = args.out_dir / f"{NAME}.mmd"
        path.write_text(drawing.draw_mermaid(), encoding="utf-8")
        written.append(path)

    if args.format in ("png", "both"):
        path = args.out_dir / f"{NAME}.png"
        try:
            path.write_bytes(drawing.draw_mermaid_png())
            written.append(path)
        except Exception as error:  # no network, or the service is unavailable
            print(f"The PNG could not be drawn by mermaid.ink: {error}", file=sys.stderr)
            print("The Mermaid file is written; open it at https://mermaid.live to export "
                  "the picture by hand.", file=sys.stderr)
            if not written:
                return 1

    for path in written:
        print(f"{_short(path)}  ({path.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
