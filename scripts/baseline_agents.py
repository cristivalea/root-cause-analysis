#!/usr/bin/env python3
"""Measure the agents before any change to the prompts or the graph (final_project_steps.md, E1).

    python scripts/baseline_agents.py                         # the 13 stories and the 4 expert follow-ups
    python scripts/baseline_agents.py --stories STORY-004     # some stories only
    python scripts/baseline_agents.py --no-judge              # without the LLM judge of the root cause
    python scripts/baseline_agents.py --records results/baseline/<run>/investigations.json   # measure again, no LLM

Every story of the answer key is investigated from its problem, on a temporary copy of the database,
so nothing appears in the application. A story with an expert follow-up is then sent back for more
details with the request of the answer key, and its second revision is investigated too.

Measured, from the trace of each investigation (llm_calls of every agent step) and the answer key:
LLM requests, input and output tokens, latency, invalid answers, failed investigations, guardrail
attempts, expected citations in the ledger and cited by the main hypothesis, red herrings cited, the
new citations the expert's request should bring, and (with the judge) whether the main hypothesis or
any hypothesis is the true root cause. Results: results/baseline/<time>-<model>/ (summary.md,
metrics.json, investigations.json).
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from rca import config, store  # noqa: E402
from rca.citations import trace_story  # noqa: E402
from rca.config import DB_PATH  # noqa: E402
from rca.models import InvestigationGuidance, RCARecord  # noqa: E402

ANSWER_KEY = ROOT / "data" / "evaluation" / "answer_key.json"
SOURCES = ROOT / "data" / "sources"
RESULTS = ROOT / "results" / "baseline"
AGENTS = ("investigation_planner", "historical_review", "rca_reasoning_agent")
OLD_NAMES = {"historical_rca_agent": "historical_review"}  # the name of the step before E5


def redact(text: str) -> str:
    """Without the account id the provider puts in its error messages."""
    return re.sub(r"org_[A-Za-z0-9]+", "org_<redacted>", text)


def error_text(exc: Exception) -> str:
    return redact(f"{type(exc).__name__}: {exc}")


def by_id(name: str, key: str) -> dict[str, dict]:
    return {item[key]: item for item in json.loads((SOURCES / name).read_text(encoding="utf-8"))}


# --------------------------------------------------------------------------------------
# running the stories
# --------------------------------------------------------------------------------------


def investigate(story: dict, db_copy: Path) -> list[dict]:
    """Revision 1 of the story, and revision 2 when the answer key has an expert follow-up."""
    from rca.pipeline import run_investigation

    runs = []
    started = time.monotonic()
    try:
        first = run_investigation(problem_id=story["problem_id"], owner="Baseline", db_path=db_copy)
        runs.append({"story_id": story["story_id"], "revision": 1, "record": first,
                     "seconds": round(time.monotonic() - started, 1)})
    except Exception as exc:  # one failed investigation must not lose the others
        runs.append({"story_id": story["story_id"], "revision": 1, "record": None,
                     "seconds": round(time.monotonic() - started, 1), "error": error_text(exc)})
        return runs

    followup = story.get("expert_followup")
    if not followup or first.status != "DRAFT":
        return runs
    store.submit_for_review(first.rca_id, "Baseline", db_path=db_copy)
    store.apply_review(first.rca_id, reviewer="Baseline expert", decision="REQUEST_MORE_DETAILS",
                       comment=followup["request"], db_path=db_copy,
                       guidance=InvestigationGuidance.model_validate(followup["guidance"]))
    started = time.monotonic()
    try:
        second = run_investigation(rca_id=first.rca_id, owner="Baseline", db_path=db_copy)
        runs.append({"story_id": story["story_id"], "revision": 2, "record": second,
                     "seconds": round(time.monotonic() - started, 1)})
    except Exception as exc:
        runs.append({"story_id": story["story_id"], "revision": 2, "record": None,
                     "seconds": round(time.monotonic() - started, 1), "error": error_text(exc)})
    return runs


def run_stories(stories: list[dict], folder: Path) -> list[dict]:
    runs: list[dict] = []
    with tempfile.TemporaryDirectory() as temporary:
        db_copy = Path(temporary) / "baseline.sqlite3"
        shutil.copy(DB_PATH, db_copy)
        for story in stories:
            print(f"{story['story_id']} ({story['problem_id']}) ...", flush=True)
            for item in investigate(story, db_copy):
                runs.append(item)
                outcome = item["record"].status if item["record"] else item["error"]
                print(f"  revision {item['revision']}: {outcome} in {item['seconds']} s", flush=True)
            save_runs(runs, folder)  # after every story, so a stopped run keeps what it measured
    return runs


def save_runs(runs: list[dict], folder: Path) -> None:
    saved = [{**{key: value for key, value in item.items() if key != "record"},
              "record": item["record"].model_dump(mode="json") if item["record"] else None} for item in runs]
    (folder / "investigations.json").write_text(json.dumps(saved, indent=2, ensure_ascii=False), encoding="utf-8")


def legacy(record: dict) -> dict:
    """A record saved before E3 (results of E1), read with the statuses of E3. Every ESCALATED of E1 was
    a draft the guardrail refused, so it reads as ESCALATED_MANUAL."""
    from rca.models import LEGACY_RCA_STATUS

    if record["status"] not in LEGACY_RCA_STATUS or record["status"] in ("DRAFT", "REJECTED", "ESCALATED_MANUAL"):
        return record
    status = "ESCALATED_MANUAL" if record["status"] == "ESCALATED" else LEGACY_RCA_STATUS[record["status"]]
    return {**record, "status": status, "revision": record.get("cycle") or 1}


def load_runs(paths: list[Path]) -> list[dict]:
    """The runs of earlier investigations.json files. A run that succeeded in a later file replaces the
    same story and revision that failed in an earlier one, so a run stopped by a daily limit can be completed."""
    runs: dict[tuple[str, int], dict] = {}
    for path in paths:
        for item in json.loads(path.read_text(encoding="utf-8")):
            key = (item["story_id"], item["revision"])
            if item["record"] or key not in runs or not runs[key]["record"]:
                runs[key] = {**item, "error": redact(item["error"]) if item.get("error") else None,
                             "record": RCARecord.model_validate(legacy(item["record"])) if item["record"] else None}
    return sorted(runs.values(), key=lambda item: (item["story_id"], item["revision"]))


# --------------------------------------------------------------------------------------
# measuring
# --------------------------------------------------------------------------------------


def llm_calls(record: RCARecord) -> dict[str, list[dict]]:
    calls: dict[str, list[dict]] = {agent: [] for agent in AGENTS}
    for step in record.trace:
        name = OLD_NAMES.get(step.name, step.name)
        if name in calls:
            calls[name] += (step.details or {}).get("llm_calls") or []
    return calls


def judge_hypotheses(record: RCARecord, true_cause: str) -> tuple[bool, bool] | None:
    """(main hypothesis is the true root cause, any hypothesis is), by the judge of eval_kpi_accuracy.
    None when the judge could not answer: its errors come back as "no match" and must not count."""
    from eval_kpi_accuracy import verify_with_llm

    verdicts = []
    for item in record.hypotheses:
        match, reason = verify_with_llm(item.candidate_root_cause, true_cause)
        if reason.startswith("Eroare arbitraj LLM"):
            print(f"  judge failed for {record.rca_id}: {redact(reason)[:200]}", flush=True)
            return None
        verdicts.append(match)
    return bool(verdicts and verdicts[0]), any(verdicts)


def measure(item: dict, story: dict, logs: dict, changes: dict, judge: bool) -> dict:
    record: RCARecord | None = item["record"]
    row = {"story_id": story["story_id"], "kind": story["kind"], "revision": item["revision"],
           "seconds": item["seconds"], "error": item.get("error")}
    if record is None:
        return row
    calls = llm_calls(record)
    every = [call for agent_calls in calls.values() for call in agent_calls]
    trace = trace_story(story, record, logs, changes)
    row |= {
        "rca_id": record.rca_id,
        "status": record.status,
        "requests": len(every),
        "requests_by_agent": {agent: len(agent_calls) for agent, agent_calls in calls.items()},
        "input_tokens": sum(call["input_tokens"] or 0 for call in every),
        "output_tokens": sum(call["output_tokens"] or 0 for call in every),
        "reasoning_tokens": sum(call.get("reasoning_tokens") or 0 for call in every),
        "cut_answers": sum(1 for call in every if call.get("finish_reason") == "length"),
        "main_hypothesis": record.hypotheses[0].candidate_root_cause if record.hypotheses else None,
        "input_tokens_by_agent": {agent: sum(c["input_tokens"] or 0 for c in agent_calls)
                                  for agent, agent_calls in calls.items()},
        "llm_seconds": round(sum(call["latency_seconds"] for call in every), 1),
        "waited_seconds": round(sum(call["waited_seconds"] for call in every), 1),
        "invalid_answers": sum(1 for call in every if call["outcome"] == "invalid"),
        "failed_requests": sum(1 for call in every if call["outcome"] not in ("valid", "invalid")),
        "reasoning_attempts": sum(1 for step in record.trace if step.name == "rca_reasoning_agent"),
        "guardrail_passed": record.status not in ("ESCALATED", "ESCALATED_MANUAL", "FAILED"),
        "hypotheses": len(record.hypotheses),
        "confidence": record.hypotheses[0].confidence if record.hypotheses else None,
        "expected_citations": len(trace.citations),
        "in_ledger": trace.preserved,
        "cited_by_main": trace.cited_by_main,
        "red_herrings_cited_by_main": trace.red_herrings_cited_by_main,
    }
    followup = story.get("expert_followup")
    if item["revision"] == 2 and followup:
        cited_any = {cited for evidence in record.evidence
                     if any(evidence.evidence_id in h.supporting_evidence for h in record.hypotheses)
                     for cited in (evidence.citation, *evidence.related_ids)}
        in_ledger = {cited for evidence in record.evidence for cited in (evidence.citation, *evidence.related_ids)}
        expected = followup["expected_new_citations"]
        row |= {"expert_expected": len(expected),
                "expert_in_ledger": sum(1 for cited in expected if cited in in_ledger),
                "expert_cited": sum(1 for cited in expected if cited in cited_any)}
    if judge and record.hypotheses and item["revision"] == 1:
        verdict = judge_hypotheses(record, story["true_root_cause"])
        if verdict is not None:
            row["top1"], row["topk"] = verdict
    return row


def total(rows: list[dict], key: str) -> int | float:
    return sum(row.get(key) or 0 for row in rows)


def summary(rows: list[dict], model: str, judge: bool) -> list[str]:
    done = [row for row in rows if row.get("rca_id")]
    first = [row for row in done if row["revision"] == 1]
    second = [row for row in done if row["revision"] == 2]
    count = max(len(done), 1)
    lines = [
        f"# Baseline of the agents ({datetime.now():%Y-%m-%d %H:%M})", "",
        f"Model: {model}. Investigations: {len(rows)} ({len(first)} first revisions, {len(second)} expert "
        f"follow-ups), {len(rows) - len(done)} failed with an error.", "",
        "| Measure | Value |", "|---|---|",
        f"| LLM requests per investigation | {total(done, 'requests') / count:.1f} |",
        f"| Input tokens per investigation | {total(done, 'input_tokens') / count:.0f} |",
        f"| Output tokens per investigation | {total(done, 'output_tokens') / count:.0f} |",
        f"| of which the model's own reasoning (gpt-oss) | {total(done, 'reasoning_tokens') / count:.0f} |",
        f"| Answers cut by the output limit (finish_reason length; measured from E10) | "
        f"{total(done, 'cut_answers')}/{total(done, 'requests')} |",
        f"| Input tokens per agent per investigation | " + ", ".join(
            f"{agent} {sum(row['input_tokens_by_agent'][agent] for row in done) / count:.0f}" for agent in AGENTS) + " |",
        f"| LLM time per investigation (s, without rate limit waits) | {total(done, 'llm_seconds') / count:.1f} |",
        f"| Rate limit waits per investigation (s) | {total(done, 'waited_seconds') / count:.1f} |",
        f"| Total time per investigation (s) | {total(done, 'seconds') / count:.1f} |",
        f"| Invalid answers (all requests) | {total(done, 'invalid_answers')}/{total(done, 'requests')} |",
        f"| Failed requests (all requests) | {total(done, 'failed_requests')}/{total(done, 'requests')} |",
        f"| Investigations with more than one reasoning attempt | "
        f"{sum(1 for row in done if row['reasoning_attempts'] > 1)}/{len(done)} |",
        f"| Investigations escalated by the guardrail | {sum(1 for row in done if not row['guardrail_passed'])}/{len(done)} |",
        f"| Expected citations in the ledger (first revisions) | {total(first, 'in_ledger')}/{total(first, 'expected_citations')} |",
        f"| Expected citations cited by the main hypothesis (first revisions) | "
        f"{total(first, 'cited_by_main')}/{total(first, 'expected_citations')} |",
        f"| First revisions where the main hypothesis cites a red herring | "
        f"{sum(1 for row in first if row['red_herrings_cited_by_main'])}/{len(first)} |",
        f"| Expert follow-ups: new citations in the ledger | {total(second, 'expert_in_ledger')}/{total(second, 'expert_expected')} |",
        f"| Expert follow-ups: new citations cited by a hypothesis | {total(second, 'expert_cited')}/{total(second, 'expert_expected')} |",
    ]
    if judge:
        judged = [row for row in first if "top1" in row]
        with_hypotheses = sum(1 for row in first if row.get("hypotheses"))
        lines += [f"| Main hypothesis is the true root cause (LLM judge, first revisions with hypotheses) | "
                  f"{sum(row['top1'] for row in judged)}/{len(judged)} judged of {with_hypotheses} |",
                  f"| Some hypothesis is the true root cause (LLM judge, first revisions with hypotheses) | "
                  f"{sum(row['topk'] for row in judged)}/{len(judged)} judged of {with_hypotheses} |"]
    lines += ["", "| Story | Rev. | Status | Requests | Input tokens | Output tokens | Time (s) | Reasoning attempts "
              "| In ledger | Cited by main | Expert citations | Error |", "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for row in rows:
        expert = f"{row['expert_cited']}/{row['expert_expected']}" if "expert_expected" in row else "-"
        lines.append(
            f"| {row['story_id']} | {row['revision']} | {row.get('status', '-')} | {row.get('requests', '-')} "
            f"| {row.get('input_tokens', '-')} | {row.get('output_tokens', '-')} | {row['seconds']} "
            f"| {row.get('reasoning_attempts', '-')} | {row.get('in_ledger', '-')}/{row.get('expected_citations', '-')} "
            f"| {row.get('cited_by_main', '-')}/{row.get('expected_citations', '-')} | {expert} | {row.get('error') or '-'} |")
    lines += ["", "Tokens are those the provider reports. A request it refused (an answer that is not valid JSON, "
              "a request too large) reports none, though it used tokens: the totals are lower bounds. The judge "
              "requests are not counted in the measures of the investigations."]
    return lines


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Measure the agents on the stories of the answer key.")
    parser.add_argument("--model", default="openai/gpt-oss-20b", help="Groq model of the agents (and of the judge)")
    parser.add_argument("--stories", nargs="+", help="story ids (default: all)")
    parser.add_argument("--records", nargs="+",
                        help="investigations.json files of earlier runs: measure again, no investigation; a later "
                             "file completes the failed runs of an earlier one")
    parser.add_argument("--no-judge", action="store_true", help="do not ask the LLM judge for the root cause")
    parser.add_argument("--label", help="added to the name of the results folder, for example the variant measured")
    args = parser.parse_args()

    config.GROQ_MODEL = args.model  # rca.llm reads it on every request
    config.LLM_FALLBACK = False  # every investigation on the same model, so the runs can be compared
    answer_key = json.loads(ANSWER_KEY.read_text(encoding="utf-8"))
    stories = [story for story in answer_key.values() if not args.stories or story["story_id"] in args.stories]

    folder = RESULTS / (f"{datetime.now():%Y%m%d-%H%M%S}-{args.model.split('/')[-1]}"
                        + (f"-{args.label}" if args.label else ""))
    folder.mkdir(parents=True, exist_ok=True)
    runs = load_runs([Path(path) for path in args.records]) if args.records else run_stories(stories, folder)
    if args.records:
        save_runs(runs, folder)

    logs, changes = by_id("logs.json", "log_id"), by_id("changes.json", "change_id")
    stories_by_id = {story["story_id"]: story for story in stories}
    rows = [measure(item, stories_by_id[item["story_id"]], logs, changes, not args.no_judge)
            for item in runs if item["story_id"] in stories_by_id]
    (folder / "metrics.json").write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
    text = summary(rows, args.model, not args.no_judge)
    (folder / "summary.md").write_text("\n".join(text) + "\n", encoding="utf-8")
    print("\n".join(text))
    print(f"\nWritten to {folder.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
