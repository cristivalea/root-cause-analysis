#!/usr/bin/env python3
"""Evaluare KPI: Corectitudinea Nivelului de Încredere (Confidence Calibration).

Verifică dacă nivelul de încredere (HIGH, MEDIUM, LOW) calculat de pipeline
se potrivește cu expected_outcome.acceptable_confidence din answer_key.json.

Utilizare:
    python scripts/eval_kpi_confidence.py
    python scripts/eval_kpi_confidence.py --incident INC-2026-00482

Reguli de numărare:
- O investigație oprită de eroare sau terminată FAILED (eroare tehnică) nu intră în calcul: apare în raport
  la "run_errors".
- Una terminată ESCALATED_MANUAL (guardrail-ul a refuzat draftul) nu are ipoteze: intră în calcul ca
  necalibrată și apare la "without_hypotheses".
- weakly_supported este o măsură separată: se compară cu answer_key.json doar când acesta o definește.
- Raportul se scrie după fiecare incident.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from rca import kpi_evaluation
from rca.config import GROQ_MODEL
from rca.pipeline import run_investigation

INCIDENTS_PATH = ROOT / "data" / "sources" / "incidents.json"
ANSWER_KEY_PATH = ROOT / "data" / "evaluation" / "answer_key.json"
OUTPUT_REPORT_PATH = ROOT / "data" / "evaluation" / "kpi_confidence_report.json"

TRANSIENT_ERRORS = ("Connection error", "getaddrinfo", "429", "rate limit", "Rate limit")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Măsurare KPI: Corectitudinea Nivelului de Încredere.")
    parser.add_argument(
        "--incident",
        type=str,
        default=None,
        help="Rulează un singur incident specific (ex: INC-2026-00482)",
    )
    return parser.parse_args()


def extract_confidence(hyp) -> tuple[str, int]:
    """Nivelul de încredere (HIGH/MEDIUM/LOW) și punctele ipotezei; NONE când nu există ipoteză."""
    if hyp is None:
        return "NONE", 0
    return str(hyp.confidence).upper().strip(), int(hyp.confidence_points)


def evaluation_db() -> Path:
    """A database built from the source files, in a temporary folder (rca/kpi_evaluation.py): the same data at
    every run, whatever was done in the application, which is never read or written."""
    return kpi_evaluation.fresh_database()


EVAL_DB: Path | None = None


def run_with_connection_retry(incident_id: str, max_retries: int = 3):
    """Rulează investigația cu retry în caz de cădere temporară a conexiunii sau de limită de rată. O rulare
    oprită de eroare este salvată FAILED; reîncercarea este revizia următoare a aceluiași RCA."""
    from rca import storage, store

    global EVAL_DB
    EVAL_DB = EVAL_DB or evaluation_db()
    for attempt in range(1, max_retries + 1):
        problem_id = storage.get_problem_id_for_incident(EVAL_DB, incident_id)
        failed = [item.rca_id for item in store.list_summaries("FAILED", problem_id, EVAL_DB)] if problem_id else []
        try:
            return run_investigation(
                incident_id=None if failed else incident_id,
                rca_id=failed[0] if failed else None,
                owner="Confidence KPI Evaluator",
                db_path=EVAL_DB,
            )
        except Exception as exc:
            if attempt < max_retries and any(token in str(exc) for token in TRANSIENT_ERRORS):
                print(f"\n   [Avertisment] Eroare temporară (conexiune/limită). Reîncercare {attempt}/{max_retries} în 15s...")
                time.sleep(15)
                continue
            raise


def percent(part: int, whole: int) -> float:
    return round(part / whole * 100, 2) if whole else 0.0


def build_report(results: list[dict]) -> dict:
    """Metrics over the cases that count: the run completed (not an error or FAILED)."""
    counted = [item for item in results if item["counted"]]
    success = [item for item in counted if item["kind"] == "success"]
    edge = [item for item in counted if item["kind"] != "success"]
    calibrated = lambda items: sum(1 for item in items if item["is_calibrated"])  # noqa: E731
    weak_checked = [item for item in counted if item["weakly_supported_match"] is not None]
    return {
        "script_version": kpi_evaluation.SCRIPT_VERSION,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "agent_model": GROQ_MODEL,
        "agent_models_used": sorted({model for item in results for model in item.get("models", [])}),
        "selected": len(results),
        "evaluated": len(counted),
        "total_cases_selected": len(results),
        "total_cases": len(counted),
        "overall_calibration_rate_percent": percent(calibrated(counted), len(counted)),
        "success_cases": {
            "total": len(success),
            "correct": calibrated(success),
            "rate_percent": percent(calibrated(success), len(success)),
        },
        "edge_cases": {
            "total": len(edge),
            "correct": calibrated(edge),
            "rate_percent": percent(calibrated(edge), len(edge)),
        },
        "weakly_supported": {
            "checked": len(weak_checked),
            "matching": sum(1 for item in weak_checked if item["weakly_supported_match"]),
            "rate_percent": percent(sum(1 for item in weak_checked if item["weakly_supported_match"]), len(weak_checked)),
        },
        "run_errors": [item["incident_id"] for item in results if item["error"]],
        "without_hypotheses": [item["incident_id"] for item in counted if item["actual_confidence"] == "NONE"],
        "details": results,
    }


def save_report(report: dict) -> None:
    OUTPUT_REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_REPORT_PATH.open("w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)


def main() -> None:
    args = parse_args()
    kpi_evaluation.same_model_for_every_story()

    if not INCIDENTS_PATH.exists() or not ANSWER_KEY_PATH.exists():
        sys.exit("Eroare: Fișierele incidents.json sau answer_key.json lipsesc.")

    with INCIDENTS_PATH.open(encoding="utf-8") as f:
        all_incidents: list[dict] = json.load(f)

    with ANSWER_KEY_PATH.open(encoding="utf-8") as f:
        answer_key: dict = json.load(f)

    benchmark_by_incident: dict[str, dict] = {
        data["target_incident"]: {
            "story_id": data["story_id"],
            "title": data["title"],
            "kind": data["kind"],
            "acceptable_confidence": [c.upper() for c in data["expected_outcome"]["acceptable_confidence"]],
            "expected_weakly_supported": data["expected_outcome"].get("weakly_supported"),
        }
        for data in answer_key.values()
    }

    incidents_to_evaluate = [
        inc for inc in all_incidents
        if inc["incident_id"] in benchmark_by_incident
        and (args.incident is None or inc["incident_id"] == args.incident)
    ]

    if not incidents_to_evaluate:
        sys.exit("Nu s-au găsit incidente eligibile pentru evaluare.")

    print(f"=== EVALUARE KPI: CORECTITUDINEA NIVELULUI DE ÎNCREDERE ({len(incidents_to_evaluate)} cazuri) ===\n")

    results: list[dict] = []

    for idx, incident in enumerate(incidents_to_evaluate, start=1):
        inc_id = incident["incident_id"]
        bench = benchmark_by_incident[inc_id]
        entry = {
            "story_id": bench["story_id"],
            "incident_id": inc_id,
            "kind": bench["kind"],
            "title": bench["title"],
            "rca_status": None,
            "counted": False,
            "duration_seconds": 0.0,
            "actual_confidence": "ERROR",
            "actual_points": 0,
            "acceptable_confidence": bench["acceptable_confidence"],
            "is_calibrated": False,
            "expected_weakly_supported": bench["expected_weakly_supported"],
            "actual_weakly_supported": None,
            "weakly_supported_match": None,
            "models": [],
            "error": None,
        }
        results.append(entry)

        print("=" * 70)
        print(f"[{idx}/{len(incidents_to_evaluate)}] {bench['story_id']} | INCIDENT: {inc_id} ({bench['kind'].upper()})")
        print(f"   Titlu: {bench['title']}")
        print(f"   Interval așteptat: {bench['acceptable_confidence']}")
        print("   Rulează investigația...", end="", flush=True)

        t0 = time.time()
        try:
            record = run_with_connection_retry(inc_id)
        except Exception as exc:
            entry["duration_seconds"] = time.time() - t0
            entry["error"] = f"{type(exc).__name__}: {exc}"
            print(f" EȘUAT ({exc}) după {entry['duration_seconds']:.1f}s.\n")
            save_report(build_report(results))
            continue

        entry["duration_seconds"] = time.time() - t0
        entry["rca_status"] = record.status
        entry["models"] = kpi_evaluation.models_used(record)
        print(f" gata în {entry['duration_seconds']:.1f}s (status {record.status}).")

        if record.status == "FAILED":  # a technical failure, not a judgement of the application
            entry["error"] = "FAILED: no usable answer from the agents"
            save_report(build_report(results))
            continue

        top_hyp = record.hypotheses[0] if record.hypotheses else None
        actual_conf, actual_points = extract_confidence(top_hyp)
        is_match = actual_conf in bench["acceptable_confidence"]
        entry.update(counted=True, actual_confidence=actual_conf, actual_points=actual_points, is_calibrated=is_match)

        if bench["expected_weakly_supported"] is not None:
            entry["actual_weakly_supported"] = record.weakly_supported
            entry["weakly_supported_match"] = record.weakly_supported == bench["expected_weakly_supported"]

        verdict_str = "✅ CORECT" if is_match else "❌ DISCREPANȚĂ (Over/Under confident)"
        print(f"   • Nivel generat (Top-1): {actual_conf} ({actual_points} puncte)")
        print(f"   • Calibrare:            {verdict_str}")
        if entry["weakly_supported_match"] is not None:
            print(f"   • weakly_supported:     {record.weakly_supported} (așteptat {bench['expected_weakly_supported']})")
        print()
        save_report(build_report(results))

    report = build_report(results)
    save_report(report)

    total = report["total_cases"]
    print("=" * 70)
    print("REZULTATE FINALE DEMONSTRAȚIE KPI - CALIBRARE ÎNCREDERE:")
    print(f"  • Cazuri selectate / evaluate:           {report['total_cases_selected']} / {total}")
    print(f"  • Rata globală de calibrare corectă:     "
          f"{sum(1 for item in results if item['is_calibrated'])}/{total} ({report['overall_calibration_rate_percent']:.1f}%)")
    print(f"  • Cazuri 'success' calibrate:            {report['success_cases']['correct']}/{report['success_cases']['total']} "
          f"({report['success_cases']['rate_percent']:.1f}%)")
    print(f"  • Cazuri 'edge' calibrate:               {report['edge_cases']['correct']}/{report['edge_cases']['total']} "
          f"({report['edge_cases']['rate_percent']:.1f}%)")
    weak = report["weakly_supported"]
    print(f"  • weakly_supported conform cheii:        {weak['matching']}/{weak['checked']} ({weak['rate_percent']:.1f}%)")
    if report["run_errors"]:
        print(f"  • Excluse (eroare la rulare/FAILED):     {', '.join(report['run_errors'])}")
    if report["without_hypotheses"]:
        print(f"  • Fără ipoteze (numărate necalibrate):   {', '.join(report['without_hypotheses'])}")
    print("=" * 70)
    print(f"\nRaportul de calibrare a fost salvat în: {OUTPUT_REPORT_PATH}")


if __name__ == "__main__":
    main()
