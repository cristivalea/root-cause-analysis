#!/usr/bin/env python3
"""Evaluare KPI: Corectitudinea Nivelului de Încredere (Confidence Calibration).

Verifică dacă nivelul de încredere (HIGH, MEDIUM, LOW) calculat de pipeline
se potrivește cu expected_outcome.acceptable_confidence din answer_key.json.

Utilizare:
    python scripts/eval_kpi_confidence.py
    python scripts/eval_kpi_confidence.py --incident INC-2026-00482
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from rca.config import DB_PATH
from rca.pipeline import run_investigation

INCIDENTS_PATH = ROOT / "data" / "sources" / "incidents.json"
ANSWER_KEY_PATH = ROOT / "data" / "evaluation" / "answer_key.json"
OUTPUT_REPORT_PATH = ROOT / "data" / "evaluation" / "kpi_confidence_report.json"


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
    """Extrage robust nivelul de încredere (HIGH/MEDIUM/LOW) și punctele."""
    if hyp is None:
        return "NONE", 0

    # Verificăm confidence_level sau confidence din modelul Hypothesis
    level = getattr(hyp, "confidence_level", None) or getattr(hyp, "confidence", None)
    if isinstance(level, str):
        level_str = level.upper().strip()
    else:
        level_str = "NONE"

    points = getattr(hyp, "confidence_points", None)
    if points is None:
        points = getattr(hyp, "points", 0)

    return level_str, int(points) if isinstance(points, (int, float)) else 0


def run_with_connection_retry(incident_id: str, max_retries: int = 3):
    """Rulează investigația cu retry în caz de cădere temporară a conexiunii la Groq."""
    for attempt in range(1, max_retries + 1):
        try:
            return run_investigation(
                incident_id=incident_id,
                owner="Confidence KPI Evaluator",
                db_path=DB_PATH,
            )
        except Exception as exc:
            err_msg = str(exc)
            if "Connection error" in err_msg or "getaddrinfo" in err_msg:
                if attempt < max_retries:
                    print(f"\n   [Avertisment] Eroare conexiune Groq/DNS. Reîncercare {attempt}/{max_retries} în 5s...")
                    time.sleep(5)
                    continue
            raise exc


def main() -> None:
    args = parse_args()

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
            "expected_weakly_supported": data["expected_outcome"].get("weakly_supported", False),
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

    correct_confidence_count = 0
    correct_success_cases = 0
    total_success_cases = 0
    correct_edge_cases = 0
    total_edge_cases = 0

    results_detail = []

    for idx, incident in enumerate(incidents_to_evaluate, start=1):
        inc_id = incident["incident_id"]
        bench = benchmark_by_incident[inc_id]
        expected_confs = bench["acceptable_confidence"]
        kind = bench["kind"]

        if kind == "success":
            total_success_cases += 1
        else:
            total_edge_cases += 1

        print("=" * 70)
        print(f"[{idx}/{len(incidents_to_evaluate)}] {bench['story_id']} | INCIDENT: {inc_id} ({bench['kind'].upper()})")
        print(f"   Titlu: {bench['title']}")
        print(f"   Interval așteptat: {expected_confs}")
        print("   Rulează investigația...", end="", flush=True)

        t0 = time.time()
        try:
            record = run_with_connection_retry(inc_id)
            elapsed = time.time() - t0
            print(f" gata în {elapsed:.1f}s.")

            top_hyp = record.hypotheses[0] if getattr(record, "hypotheses", None) else None
            actual_conf, actual_points = extract_confidence(top_hyp)

            # Verificare potrivire nivel de încredere
            is_match = actual_conf in expected_confs

            if is_match:
                correct_confidence_count += 1
                if kind == "success":
                    correct_success_cases += 1
                else:
                    correct_edge_cases += 1

            verdict_str = "✅ CORECT" if is_match else "❌ DISCREPANȚĂ (Over/Under confident)"
            print(f"   • Nivel generat (Top-1): {actual_conf} ({actual_points} puncte)")
            print(f"   • Calibrare:            {verdict_str}\n")

            results_detail.append({
                "story_id": bench["story_id"],
                "incident_id": inc_id,
                "kind": kind,
                "title": bench["title"],
                "duration_seconds": elapsed,
                "actual_confidence": actual_conf,
                "actual_points": actual_points,
                "acceptable_confidence": expected_confs,
                "is_calibrated": is_match,
                "error": None,
            })

        except Exception as exc:
            elapsed = time.time() - t0
            print(f" EȘUAT ({exc}) după {elapsed:.1f}s.\n")
            results_detail.append({
                "story_id": bench["story_id"],
                "incident_id": inc_id,
                "kind": kind,
                "title": bench["title"],
                "duration_seconds": elapsed,
                "actual_confidence": "ERROR",
                "actual_points": 0,
                "acceptable_confidence": expected_confs,
                "is_calibrated": False,
                "error": str(exc),
            })

    total_cases = len(incidents_to_evaluate)
    calibration_rate = (correct_confidence_count / total_cases) * 100 if total_cases else 0.0
    success_rate = (correct_success_cases / total_success_cases) * 100 if total_success_cases else 0.0
    edge_rate = (correct_edge_cases / total_edge_cases) * 100 if total_edge_cases else 0.0

    print("=" * 70)
    print("REZULTATE FINALE DEMONSTRAȚIE KPI - CALIBRARE ÎNCREDERE:")
    print(f"  • Total cazuri investigate:              {total_cases}")
    print(f"  • Rata globală de calibrare corectă:     {correct_confidence_count}/{total_cases} ({calibration_rate:.1f}%)")
    print(f"  • Cazuri 'success' calibrate:            {correct_success_cases}/{total_success_cases} ({success_rate:.1f}%)")
    print(f"  • Cazuri 'edge' calibrate:               {correct_edge_cases}/{total_edge_cases} ({edge_rate:.1f}%)")
    print("=" * 70)

    OUTPUT_REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    report_data = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "total_cases": total_cases,
        "overall_calibration_rate_percent": round(calibration_rate, 2),
        "success_cases": {
            "total": total_success_cases,
            "correct": correct_success_cases,
            "rate_percent": round(success_rate, 2),
        },
        "edge_cases": {
            "total": total_edge_cases,
            "correct": correct_edge_cases,
            "rate_percent": round(edge_rate, 2),
        },
        "details": results_detail,
    }
    with OUTPUT_REPORT_PATH.open("w", encoding="utf-8") as f:
        json.dump(report_data, f, indent=2, ensure_ascii=False)

    print(f"\nRaportul de calibrare a fost salvat în: {OUTPUT_REPORT_PATH}")


if __name__ == "__main__":
    main()