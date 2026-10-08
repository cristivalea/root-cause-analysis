#!/usr/bin/env python3
"""Follow every expected citation of the answer key through one run of the 13 stories.

    python scripts/trace_citations.py --records results/ragas/<run>/investigations.json
    python scripts/trace_citations.py --rca-ids RCA-2026-00001 RCA-2026-00002

For each citation it prints the last stage reached (ledger, cited by the main hypothesis) and,
when the plan can tell, why a log line or a change never reached the ledger. No LLM is used.
The results go to results/citations/<time>/ (summary.md, details.json).
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from rca import store  # noqa: E402
from rca.citations import CITED_BY_MAIN, NOT_IN_LEDGER, record_for_story, trace_story  # noqa: E402
from rca.models import RCARecord  # noqa: E402

ANSWER_KEY = ROOT / "data" / "evaluation" / "answer_key.json"
SOURCES = ROOT / "data" / "sources"
RESULTS = ROOT / "results" / "citations"


def load_records(args: argparse.Namespace) -> list[RCARecord]:
    if args.records:
        return [RCARecord.model_validate(item) for item in json.loads(Path(args.records).read_text(encoding="utf-8"))]
    records = [store.get_rca(rca_id) for rca_id in args.rca_ids]
    missing = [rca_id for rca_id, record in zip(args.rca_ids, records) if record is None]
    if missing:
        raise SystemExit(f"RCA not found: {', '.join(missing)}")
    return records


def by_id(name: str, key: str) -> dict[str, dict]:
    return {item[key]: item for item in json.loads((SOURCES / name).read_text(encoding="utf-8"))}


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Follow the expected citations through the investigations.")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--records", help="an investigations.json written by scripts/evaluate_ragas.py --run-stories")
    source.add_argument("--rca-ids", nargs="+", help="RCAs saved in the application")
    args = parser.parse_args()

    records = load_records(args)
    answer_key = json.loads(ANSWER_KEY.read_text(encoding="utf-8"))
    logs, changes = by_id("logs.json", "log_id"), by_id("changes.json", "change_id")

    traces, missing = [], []
    for story in answer_key.values():
        record = record_for_story(story, records)
        if record is None:
            missing.append(story["story_id"])
            continue
        traces.append(trace_story(story, record, logs, changes))

    lines = []
    for trace in traces:
        lines.append(f"{trace.story_id}  ({trace.rca_id}, {trace.incident_id})")
        for item in trace.citations:
            where = f" -> {item.evidence_id}" if item.evidence_id else ""
            by = f" ({', '.join(item.cited_by)})" if item.cited_by and item.stage != CITED_BY_MAIN else ""
            why = f": {item.reason}" if item.reason else ""
            mark = "" if item.stage == CITED_BY_MAIN else "   <- lost here"
            lines.append(f"  {item.citation:<26}{where:<10} {item.stage}{by}{why}{mark}")
        lines.append("")

    expected = sum(len(trace.citations) for trace in traces)
    preserved = sum(trace.preserved for trace in traces)
    cited = sum(trace.cited_by_main for trace in traces)
    ledger = sum(trace.ledger_size for trace in traces)
    relevant = sum(trace.relevant_in_ledger for trace in traces)
    summary = [
        f"# Citation trace ({datetime.now():%Y-%m-%d %H:%M})", "",
        f"Stories traced: {len(traces)}" + (f". No investigation for: {', '.join(missing)}." if missing else "."), "",
        "| Measure | Value |", "|---|---|",
        f"| Expected citations in the ledger (preservation) | {preserved}/{expected} |",
        f"| Expected citations cited by the main hypothesis (utilization) | {cited}/{preserved} of those in the ledger |",
        f"| Ledger evidence the answer key names anywhere (precision) | {relevant}/{ledger} |",
        f"| Stories where the main hypothesis cites a red herring | {sum(bool(t.red_herrings_cited_by_main) for t in traces)}/{len(traces)} |",
        "", "| Story | In ledger | Cited by main | Not in ledger | Red herrings cited by main |", "|---|---|---|---|---|",
    ]
    summary += [f"| {t.story_id} | {t.preserved}/{len(t.citations)} | {t.cited_by_main}/{len(t.citations)} | "
                f"{', '.join(c.citation for c in t.citations if c.stage == NOT_IN_LEDGER) or '-'} | "
                f"{', '.join(t.red_herrings_cited_by_main) or '-'} |" for t in traces]

    folder = RESULTS / datetime.now().strftime("%Y%m%d-%H%M%S")
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "summary.md").write_text("\n".join(summary + ["", "```", *lines, "```"]) + "\n", encoding="utf-8")
    (folder / "details.json").write_text(json.dumps([asdict(t) for t in traces], indent=2, ensure_ascii=False), encoding="utf-8")
    print("\n".join(lines + summary))
    print(f"\nWritten to {folder.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
