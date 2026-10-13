#!/usr/bin/env python3
"""Measure a change to the agents against the code without it, on the same model (final_project_steps.md, E10).

    python scripts/compare_variants.py --variants v3=LLM_COMPACT_SCHEMA v5=REASONING_CAUSE_RULE \
        --models groq:qwen/qwen3.8-27b gemini:gemini-3.6-flash openrouter:nvidia/nemotron-3-super-120b-a12b:free

Every story is investigated once with the code as it is (the control) and once with each variant (one setting of
rca/config.py switched on), one after the other on the same model, each on its own copy of the database. A model
that reaches its limit, or is unavailable, is set aside and the story starts again, control and variants, on the
next model: a comparison never mixes two models, and the free models can be used one after the other.

The measures are those of scripts/baseline_agents.py, per variant, over the stories measured for every variant.
Results: results/baseline/<time>-compare-<labels>/ (summary.md, metrics.json, investigations.json).
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from baseline_agents import (ANSWER_KEY, RESULTS, by_id, investigate, measure, redact,  # noqa: E402
                             total)

from rca import config  # noqa: E402
from rca.config import DB_PATH  # noqa: E402

# What says the model cannot answer now, rather than that the code is wrong: a limit reached (429), a request
# too large for this model (413), a model that is gone (404) or a provider that is down (5xx, no connection).
MODEL_UNAVAILABLE = ("429", "RateLimit", "413", "404", "500", "502", "503", "504", "Connection", "Timeout",
                     "DailyLimit", "No model can be used")


BUSY = ("500", "502", "503", "504", "Connection", "Timeout")  # the provider is busy: worth another try later
BUSY_TRIES = 3


def unavailable(runs: list[dict]) -> str | None:
    for item in runs:
        # an error during the run is saved on the revision (FAILED), not raised
        error = item.get("error") or (item["record"].error if item["record"] and item["record"].error else "")
        if any(sign in error for sign in MODEL_UNAVAILABLE):
            return error
    return None


def run_variant(story: dict, settings: dict[str, object], folder: Path) -> list[dict]:
    """The story investigated with the settings switched on, on a fresh copy of the database."""
    before = {name: getattr(config, name) for name in settings}
    for name, value in settings.items():
        setattr(config, name, value)
    try:
        db_copy = folder / f"{story['story_id']}-{time.monotonic_ns()}.sqlite3"
        shutil.copy(DB_PATH, db_copy)
        return investigate(story, db_copy)
    finally:
        for name, value in before.items():
            setattr(config, name, value)


def parse_variant(text: str) -> tuple[str, dict[str, object]]:
    """'v3=LLM_COMPACT_SCHEMA' or 'v1=LLM_REASONING_EFFORT:low' -> ('v3', {'LLM_COMPACT_SCHEMA': True})."""
    label, _, settings = text.partition("=")
    values: dict[str, object] = {}
    for setting in settings.split(","):
        name, _, value = setting.partition(":")
        if not hasattr(config, name):
            raise SystemExit(f"Unknown setting {name} in rca/config.py")
        values[name] = value if value else True
    return label, values


def compare(stories: list[dict], variants: list[tuple[str, dict]], models: list[str], folder: Path) -> list[dict]:
    runs: list[dict] = []
    left = list(models)
    tries: dict[str, int] = {}
    with tempfile.TemporaryDirectory() as temporary:
        for story in stories:
            while left:
                model = left[0]
                config.GROQ_MODEL = model
                print(f"{story['story_id']} on {model}", flush=True)
                measured, failure = [], None
                for label, settings in variants:
                    items = run_variant(story, settings, Path(temporary))
                    failure = unavailable(items)
                    if failure:
                        break
                    for item in items:
                        outcome = item["record"].status if item["record"] else item["error"]
                        print(f"  {label} revision {item['revision']}: {outcome} in {item['seconds']} s", flush=True)
                    measured += [{**item, "variant": label, "model": model} for item in items]
                if failure:
                    left.pop(0)
                    busy = any(code in failure for code in BUSY)
                    if busy and tries.get(model, 0) < BUSY_TRIES:  # busy for now: tried again after the others
                        tries[model] = tries.get(model, 0) + 1
                        left.append(model)
                        print(f"  {model} busy, tried again later: {redact(failure)[:160]}", flush=True)
                    else:
                        print(f"  {model} set aside: {redact(failure)[:200]}", flush=True)
                    continue
                runs += measured
                save(runs, folder)
                break
            else:
                print(f"{story['story_id']}: no model left", flush=True)
    return runs


def save(runs: list[dict], folder: Path) -> None:
    saved = [{**{key: value for key, value in item.items() if key != "record"},
              "record": item["record"].model_dump(mode="json") if item["record"] else None} for item in runs]
    (folder / "investigations.json").write_text(json.dumps(saved, indent=2, ensure_ascii=False), encoding="utf-8")


MEASURES = [
    ("Investigations (DRAFT / all)", lambda rows: f"{sum(1 for r in rows if r.get('status') == 'DRAFT')}/{len(rows)}"),
    ("LLM requests per investigation", lambda rows: f"{total(rows, 'requests') / max(len(rows), 1):.1f}"),
    ("Input tokens per investigation", lambda rows: f"{total(rows, 'input_tokens') / max(len(rows), 1):.0f}"),
    ("Output tokens per investigation", lambda rows: f"{total(rows, 'output_tokens') / max(len(rows), 1):.0f}"),
    ("of which the model's own reasoning", lambda rows: f"{total(rows, 'reasoning_tokens') / max(len(rows), 1):.0f}"),
    ("Answers cut by the output limit", lambda rows: f"{total(rows, 'cut_answers')}/{total(rows, 'requests')}"),
    ("Invalid answers", lambda rows: f"{total(rows, 'invalid_answers')}/{total(rows, 'requests')}"),
    ("Investigations with more than one reasoning attempt",
     lambda rows: f"{sum(1 for r in rows if (r.get('reasoning_attempts') or 0) > 1)}/{len(rows)}"),
    ("Escalated or failed", lambda rows: f"{sum(1 for r in rows if not r.get('guardrail_passed'))}/{len(rows)}"),
    ("LLM time per investigation (s)", lambda rows: f"{total(rows, 'llm_seconds') / max(len(rows), 1):.1f}"),
    ("Expected citations cited by the main hypothesis (revision 1)",
     lambda rows: f"{total([r for r in rows if r['revision'] == 1], 'cited_by_main')}/"
                  f"{total([r for r in rows if r['revision'] == 1], 'expected_citations')}"),
    ("Main hypothesis cites a red herring (revision 1)",
     lambda rows: f"{sum(1 for r in rows if r['revision'] == 1 and r.get('red_herrings_cited_by_main'))}/"
                  f"{sum(1 for r in rows if r['revision'] == 1)}"),
    ("Expert follow-ups: new citations cited by a hypothesis",
     lambda rows: f"{total(rows, 'expert_cited')}/{total(rows, 'expert_expected')}"),
]


def summary(rows: list[dict], labels: list[str], stories: dict) -> list[str]:
    lines = [f"# Comparison of variants ({datetime.now():%Y-%m-%d %H:%M})", "",
             "Each story ran with every variant on the same model; a story without every variant measured is left out.",
             "", "| Measure | " + " | ".join(labels) + " |", "|---|" + "---|" * len(labels)]
    for name, value in MEASURES:
        lines.append(f"| {name} | " + " | ".join(value([r for r in rows if r["variant"] == label]) for label in labels) + " |")
    lines += ["", "| Story | Rev. | Model | Variant | Status | Tokens in/out | Attempts | Cited by main | Main hypothesis |",
              "|---|---|---|---|---|---|---|---|---|"]
    for row in rows:
        lines.append(f"| {row['story_id']} | {row['revision']} | {row['model']} | {row['variant']} | {row.get('status', row.get('error'))} "
                     f"| {row.get('input_tokens', '-')}/{row.get('output_tokens', '-')} | {row.get('reasoning_attempts', '-')} "
                     f"| {row.get('cited_by_main', '-')}/{row.get('expected_citations', '-')} "
                     f"| {(row.get('main_hypothesis') or '-')[:140]} |")
    lines += ["", "True root causes:"] + [f"- {key}: {story['true_root_cause']}" for key, story in stories.items()]
    return lines


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Measure variants of the agents against the control, model by model.")
    parser.add_argument("--variants", nargs="+", required=True, help="label=SETTING[,SETTING:value] of rca/config.py")
    parser.add_argument("--models", nargs="+", required=True, help="provider:model, used one after the other")
    parser.add_argument("--stories", nargs="+", help="story ids (default: all)")
    args = parser.parse_args()

    config.LLM_FALLBACK = False  # one model per story, chosen here
    answer_key = json.loads(ANSWER_KEY.read_text(encoding="utf-8"))
    stories = [story for story in answer_key.values() if not args.stories or story["story_id"] in args.stories]
    variants = [("control", {})] + [parse_variant(text) for text in args.variants]
    labels = [label for label, _ in variants]

    folder = RESULTS / f"{datetime.now():%Y%m%d-%H%M%S}-compare-{'-'.join(labels[1:])}"
    folder.mkdir(parents=True, exist_ok=True)
    runs = compare(stories, variants, args.models, folder)

    logs, changes = by_id("logs.json", "log_id"), by_id("changes.json", "change_id")
    by_story = {story["story_id"]: story for story in stories}
    rows = [measure(item, by_story[item["story_id"]], logs, changes, False) | {"variant": item["variant"],
                                                                              "model": item["model"]} for item in runs]
    (folder / "metrics.json").write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
    text = summary(rows, labels, {key: by_story[key] for key in sorted({row["story_id"] for row in rows})})
    (folder / "summary.md").write_text("\n".join(text) + "\n", encoding="utf-8")
    print("\n".join(text))
    print(f"\nWritten to {folder.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
