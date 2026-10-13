#!/usr/bin/env python3
"""Run the RAGAS evaluation and write the results to results/ragas/ (explained in ragas_project.md).

Commands:
  retrieval     score the search on the 26 questions (needs Ollama, not Groq)
  calibrate     the same, for several similarity thresholds, to choose the best one
  faithfulness  score the hypotheses of RCAs with an LLM judge (needs Groq)

Examples:
  python scripts/evaluate_ragas.py retrieval
  python scripts/evaluate_ragas.py calibrate --thresholds 0.35 0.40 0.45 0.50 0.55
  python scripts/evaluate_ragas.py faithfulness --run-stories
  python scripts/evaluate_ragas.py faithfulness --records results/ragas/<run>/investigations.json
  python scripts/evaluate_ragas.py faithfulness --rca-ids RCA-2026-00012 RCA-2026-00013

Every run writes a new folder results/ragas/<date>-<time>-<command>/ and never changes the
application data. Investigations started by --run-stories are saved in a temporary copy of the
database, so they do not appear in the RCA history of the application.
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import sys
import tempfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from rca import evaluation, rag, store  # noqa: E402
from rca.config import DB_PATH  # noqa: E402
from rca.models import RCARecord  # noqa: E402

RESULTS_DIR = ROOT / "results" / "ragas"
CACHE_DIR = RESULTS_DIR / ".cache"  # the answers of the judge, so a repeated run asks Groq nothing


def run_folder(command: str) -> Path:
    folder = RESULTS_DIR / f"{datetime.now():%Y%m%d-%H%M%S}-{command}"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def number(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.2f}"


# --------------------------------------------------------------------------------------
# retrieval and calibrate
# --------------------------------------------------------------------------------------


def write_retrieval_rows(path: Path, results: list[evaluation.RetrievalResult]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["question_id", "incident_id", "collection", "method", "max_distance",
                         "recall", "precision", "retrieved", "relevant", "misleading_found"])
        for item in results:
            writer.writerow([item.question_id, item.incident_id, item.collection, item.method,
                             "" if item.max_distance is None else item.max_distance,
                             number(item.recall), number(item.precision), " ".join(item.retrieved),
                             " ".join(item.relevant), " ".join(item.misleading_found)])


def summary_table(summaries: list[evaluation.RetrievalSummary]) -> list[str]:
    lines = [
        "| Method | Collection | Threshold | Recall | Precision | Nothing to find: returned nothing | Misleading record returned |",
        "|---|---|---|---|---|---|---|",
    ]
    for item in summaries:
        lines.append(
            f"| {item.method} | {item.collection} | {item.max_distance if item.max_distance is not None else '-'} "
            f"| {number(item.recall)} | {number(item.precision)} "
            f"| {item.empty_correct} of {item.empty_expected} | {item.misleading} of {item.questions} |"
        )
    return lines


def write_summary(path: Path, title: str, summaries: list[evaluation.RetrievalSummary], note: str) -> None:
    text = [f"# {title}", "", f"Run: {datetime.now():%Y-%m-%d %H:%M}", "", *summary_table(summaries), "", note, ""]
    path.write_text("\n".join(text), encoding="utf-8")
    print("\n".join(summary_table(summaries)))


RETRIEVAL_NOTE = (
    "Recall: of the records that should be found, the share found. Precision: of the records "
    "returned, the share that is right. Both are averages over the questions; a question with "
    "nothing to find has no recall, a search that returned nothing has no precision. Details per "
    "question in rows.csv."
)


def cmd_retrieval(args: argparse.Namespace) -> None:
    questions = evaluation.load_questions()
    results = evaluation.evaluate_retrieval(questions, "semantic", args.max_distance, args.limit)
    if not args.no_keyword:
        results += evaluation.evaluate_retrieval(questions, "keyword", None, args.limit)
    folder = run_folder("retrieval")
    write_retrieval_rows(folder / "rows.csv", results)
    write_summary(folder / "summary.md", "RAGAS: search quality", evaluation.summarize_retrieval(results), RETRIEVAL_NOTE)
    print(f"\nWritten to {folder.relative_to(ROOT)}")


def cmd_calibrate(args: argparse.Namespace) -> None:
    questions = evaluation.load_questions()
    results = evaluation.evaluate_thresholds(questions, sorted(args.thresholds), args.limit)
    folder = run_folder("calibrate")
    write_retrieval_rows(folder / "rows.csv", results)
    note = (f"The application uses the threshold {rag.DEFAULT_MAX_DISTANCE} (DEFAULT_MAX_DISTANCE in "
            "rca/rag.py). A lower threshold returns fewer records: precision goes up, recall goes "
            "down. " + RETRIEVAL_NOTE)
    write_summary(folder / "summary.md", "RAGAS: similarity threshold calibration", evaluation.summarize_retrieval(results), note)
    print(f"\nWritten to {folder.relative_to(ROOT)}")


# --------------------------------------------------------------------------------------
# faithfulness
# --------------------------------------------------------------------------------------


def run_stories(folder: Path, model: str | None) -> list[RCARecord]:
    """Investigate the 13 story incidents on a temporary copy of the database."""
    from rca import config
    from rca.pipeline import run_investigation

    if model:
        config.GROQ_MODEL = model  # rca.llm reads it on every request
    config.LLM_FALLBACK = False  # every story on the same model, so the scores can be compared

    records = []
    with tempfile.TemporaryDirectory() as temporary:
        db_copy = Path(temporary) / "evaluation.sqlite3"
        shutil.copy(DB_PATH, db_copy)
        for incident_id in evaluation.story_incidents():
            print(f"Investigating {incident_id} ...", flush=True)
            try:
                records.append(run_investigation(incident_id, owner="RAGAS evaluation", db_path=db_copy))
            except Exception as exc:  # one failed investigation must not lose the others
                print(f"  failed: {type(exc).__name__}: {exc}")
    (folder / "investigations.json").write_text(
        json.dumps([record.model_dump(mode="json") for record in records], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return records


def load_records(args: argparse.Namespace, folder: Path) -> list[RCARecord]:
    if args.run_stories:
        return run_stories(folder, args.agent_model)
    if args.records:
        return [RCARecord.model_validate(item) for item in json.loads(Path(args.records).read_text(encoding="utf-8"))]
    records = [store.get_rca(rca_id) for rca_id in args.rca_ids]
    missing = [rca_id for rca_id, record in zip(args.rca_ids, records) if record is None]
    if missing:
        raise SystemExit(f"RCA not found: {', '.join(missing)}")
    return records


def cmd_faithfulness(args: argparse.Namespace) -> None:
    folder = run_folder("faithfulness")
    records = load_records(args, folder)
    without = [record.rca_id for record in records if not record.hypotheses]
    judge = evaluation.make_judge(args.judge_model, None if args.no_cache else CACHE_DIR)
    print(f"Judging the hypotheses of {len(records)} RCA(s) with {args.judge_model} ...", flush=True)
    results = evaluation.evaluate_faithfulness(records, judge, args.pause)

    with (folder / "rows.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["rca_id", "incident_id", "hypothesis_id", "faithfulness", "statements",
                         "supported", "cited_evidence", "hypothesis"])
        for item in results:
            writer.writerow([item.sample.rca_id, item.sample.incident_id, item.sample.hypothesis_id,
                             number(item.score), len(item.verdicts), sum(v.supported for v in item.verdicts),
                             " ".join(item.sample.cited), item.sample.response])

    details = ["# RAGAS Faithfulness: the verdicts of the judge", ""]
    for item in results:
        details += [f"## {item.sample.rca_id} / {item.sample.incident_id} / {item.sample.hypothesis_id}: "
                    f"{number(item.score)}", "", f"**Hypothesis:** {item.sample.response}", "", "**Cited evidence:**", ""]
        details += [f"- {context}" for context in item.sample.contexts]
        details += ["", "**Statements:**", ""]
        details += [f"- {'YES' if v.supported else 'NO'}: {v.statement} ({v.reason})" for v in item.verdicts]
        details.append("")
    (folder / "verdicts.md").write_text("\n".join(details), encoding="utf-8")

    scores = [item.score for item in results if item.score is not None]
    average = round(sum(scores) / len(scores), 3) if scores else None
    summary = [
        "# RAGAS: faithfulness of the hypotheses", "",
        f"Run: {datetime.now():%Y-%m-%d %H:%M}. Judge: {args.judge_model}.", "",
        "| RCAs | Hypotheses judged | Average faithfulness | Hypotheses with a score below 1 |",
        "|---|---|---|---|",
        f"| {len(records)} | {len(results)} | {number(average)} | {sum(1 for s in scores if s < 1)} |", "",
        "Faithfulness: of the statements in a hypothesis, the share the cited evidence supports. "
        "The statements and the verdict on each one are in verdicts.md.", "",
    ]
    if without:
        summary.append(f"RCAs without hypotheses (escalated, nothing to judge): {', '.join(without)}.")
    (folder / "summary.md").write_text("\n".join(summary) + "\n", encoding="utf-8")
    print("\n".join(summary))
    print(f"Written to {folder.relative_to(ROOT)}")


# --------------------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate the RAG parts of the application with RAGAS.")
    commands = parser.add_subparsers(dest="command", required=True)

    retrieval = commands.add_parser("retrieval", help="score the search on the evaluation questions")
    retrieval.add_argument("--max-distance", type=float, default=rag.DEFAULT_MAX_DISTANCE,
                           help=f"similarity threshold (default {rag.DEFAULT_MAX_DISTANCE}, the one the application uses)")
    retrieval.add_argument("--limit", type=int, default=evaluation.DEFAULT_LIMIT, help="results per search")
    retrieval.add_argument("--no-keyword", action="store_true", help="skip the keyword search comparison")
    retrieval.set_defaults(handler=cmd_retrieval)

    calibrate = commands.add_parser("calibrate", help="score the search for several thresholds")
    calibrate.add_argument("--thresholds", type=float, nargs="+", default=[0.35, 0.40, 0.45, 0.50, 0.55])
    calibrate.add_argument("--limit", type=int, default=evaluation.DEFAULT_LIMIT)
    calibrate.set_defaults(handler=cmd_calibrate)

    faithfulness = commands.add_parser("faithfulness", help="score the hypotheses with an LLM judge")
    source = faithfulness.add_mutually_exclusive_group(required=True)
    source.add_argument("--run-stories", action="store_true", help="investigate the 13 story incidents first")
    source.add_argument("--records", help="a investigations.json written by an earlier --run-stories")
    source.add_argument("--rca-ids", nargs="+", help="RCAs saved in the application")
    faithfulness.add_argument("--judge-model", default=evaluation.JUDGE_MODEL)
    faithfulness.add_argument("--agent-model", help="Groq model for the investigations (default: GROQ_MODEL from .env)")
    faithfulness.add_argument("--pause", type=float, default=2.0, help="seconds between two hypotheses")
    faithfulness.add_argument("--no-cache", action="store_true", help="ask the judge again even for known hypotheses")
    faithfulness.set_defaults(handler=cmd_faithfulness)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    args.handler(args)


if __name__ == "__main__":
    main()
