#!/usr/bin/env python3
"""Evaluare KPI: Acuratețea Ipotezelor pe baza incidentelor reale.

Măsoară Top-1 și Top-K Accuracy comparând ipotezele produse de pipeline
cu datele de referință din answer_key.json.

Utilizare:
    python scripts/eval_kpi_accuracy.py
    python scripts/eval_kpi_accuracy.py --judge manual
    python scripts/eval_kpi_accuracy.py --incident INC-2026-00482

Reguli de numărare:
- Judecătorul automat este rca/judge.py (config.JUDGE_MODEL), nu modelul agenților.
- O investigație oprită de eroare sau terminată FAILED (eroare tehnică) nu intră în calcul: apare în raport
  la "run_errors". Una terminată ESCALATED_MANUAL (guardrail-ul a refuzat draftul) intră în calcul ca ratată.
- Un incident la care judecătorul nu a putut da verdictul (eroare) nu intră în calcul: apare la "judge_errors".
- Raportul se scrie după fiecare incident.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from rca import judge
from rca.config import DB_PATH, GROQ_MODEL, JUDGE_MODEL
from rca.pipeline import run_investigation

INCIDENTS_PATH = ROOT / "data" / "sources" / "incidents.json"
ANSWER_KEY_PATH = ROOT / "data" / "evaluation" / "answer_key.json"
OUTPUT_REPORT_PATH = ROOT / "data" / "evaluation" / "kpi_accuracy_report.json"


class MatchVerdict(BaseModel):
    is_match: bool = Field(
        description="True dacă ipoteza identifică corect aceeași componentă și același mecanism tehnic ca și cauza reală."
    )
    reason: str = Field(description="Scurtă justificare a deciziei arbitrului.")


JUDGE_PROMPT = """Ești un expert SRE și evaluator Problem Management ITIL.
Sarcina ta este să compari o cauză rădăcină REALĂ (Ground Truth) cu o IPOTEZĂ CANDIDATĂ generată de pipeline-ul RCA pentru un incident.

Reguli de decizie (ECHIVALENȚĂ TEHNICĂ):
1. Răspunde cu is_match = true dacă ipoteza indică aceeași COMPONENTĂ tehnică și același MECANISM de defectare (chiar dacă formularea diferă sau include detalii contextuale adiționale).
2. Răspunde cu is_match = false dacă ipoteza acuză o componentă greșită, un factor secundar/nevinovat (red herring) sau un mecanism eronat.
"""


def verify_with_llm(candidate: str, true_cause: str) -> tuple[bool | None, str]:
    """Judecătorul (rca/judge.py). None = nu a putut da verdictul (eroare), diferit de "incorect"."""
    user_input = (
        f"CAUZA REALĂ (Ground Truth):\n{true_cause}\n\n"
        f"IPOTEZA CANDIDATĂ:\n{candidate}\n\n"
        "Identifică ipoteza candidată aceeași problemă tehnică de bază?"
    )
    try:
        res: MatchVerdict = judge.ask_json(JUDGE_PROMPT, user_input, MatchVerdict)
        return res.is_match, res.reason
    except Exception as exc:
        return None, f"Eroare arbitraj LLM: {exc}"


def verify_manually(candidate: str, true_cause: str, hyp_index: int) -> tuple[bool | None, str]:
    """Interfață de consolă pentru validare umană (DA / NU)."""
    print(f"\n   [Verificare Manuală - Ipoteză #{hyp_index}]")
    print(f"   • Cauza reală:   {true_cause}")
    print(f"   • Ipoteza AI:    {candidate}")
    while True:
        ans = input("   Este corectă tehnic? (d/n sau y/n): ").strip().lower()
        if ans in ("d", "da", "y", "yes"):
            note = input("   Comentariu (opțional): ").strip()
            return True, note or "Aprobat manual"
        if ans in ("n", "nu", "no"):
            note = input("   Comentariu (opțional): ").strip()
            return False, note or "Respins manual"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Măsurare KPI: Acuratețe Ipoteze per Incident.")
    parser.add_argument(
        "--judge",
        choices=["auto", "manual"],
        default="auto",
        help="Modul de arbitrare: 'auto' (rca/judge.py, config.JUDGE_MODEL) sau 'manual' (operator uman)",
    )
    parser.add_argument(
        "--incident",
        type=str,
        default=None,
        help="Rulează un singur incident specific (ex: INC-2026-00482)",
    )
    return parser.parse_args()


def evaluation_db() -> Path:
    """A temporary copy of the database: the investigations of the evaluation never reach the application."""
    import shutil
    import tempfile

    copy = Path(tempfile.mkdtemp()) / "evaluation.sqlite3"
    shutil.copy(DB_PATH, copy)
    return copy


def percent(part: int, whole: int) -> float:
    return round(part / whole * 100, 2) if whole else 0.0


def build_report(judge_mode: str, results: list[dict]) -> dict:
    """Metrics over the incidents that count: run completed (not an error or FAILED) and judged."""
    counted = [item for item in results if item["counted"]]
    top1 = sum(1 for item in counted if item["top1_match"])
    topk = sum(1 for item in counted if item["topk_match"])
    hypotheses = sum(item["hypotheses_count"] for item in counted)
    return {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "judge_mode": judge_mode,
        "agent_model": GROQ_MODEL,
        "judge_model": JUDGE_MODEL if judge_mode == "auto" else "human",
        "total_incidents_selected": len(results),
        "total_incidents_evaluated": len(counted),
        "run_errors": [item["incident_id"] for item in results if item["outcome"] == "run_error"],
        "judge_errors": [item["incident_id"] for item in results if item["outcome"] == "judge_error"],
        "without_hypotheses": [item["incident_id"] for item in counted if not item["hypotheses_count"]],
        "top1_matches": top1,
        "topk_matches": topk,
        "top1_accuracy_percent": percent(top1, len(counted)),
        "topk_accuracy_percent": percent(topk, len(counted)),
        "average_hypotheses_per_incident": round(hypotheses / len(counted), 2) if counted else 0.0,
        "total_hypotheses_evaluated": hypotheses,
        "total_hypotheses_correct": sum(
            1 for item in counted for evaluation in item["evaluations"] if evaluation["is_match"]
        ),
        "incidents": results,
    }


def save_report(report: dict) -> None:
    OUTPUT_REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_REPORT_PATH.open("w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)


def main() -> None:
    args = parse_args()

    if not INCIDENTS_PATH.exists() or not ANSWER_KEY_PATH.exists():
        sys.exit("Eroare: Fișierele data/sources/incidents.json sau data/evaluation/answer_key.json lipsesc.")

    with INCIDENTS_PATH.open(encoding="utf-8") as f:
        all_incidents: list[dict] = json.load(f)

    with ANSWER_KEY_PATH.open(encoding="utf-8") as f:
        answer_key: dict = json.load(f)

    ground_truth_by_incident: dict[str, str] = {
        data["target_incident"]: data["true_root_cause"]
        for data in answer_key.values()
    }

    incidents_to_evaluate = [
        inc for inc in all_incidents
        if inc["incident_id"] in ground_truth_by_incident
        and (args.incident is None or inc["incident_id"] == args.incident)
    ]

    if not incidents_to_evaluate:
        sys.exit("Nu s-au găsit incidente eligibile pentru evaluare.")

    eval_db = evaluation_db()  # the investigations stay out of the application
    judge_name = JUDGE_MODEL if args.judge == "auto" else "operator uman"
    print(f"=== EVALUARE KPI: ACURATEȚEA IPOTEZELOR ({len(incidents_to_evaluate)} incidente) ===")
    print(f"Model agenți: {GROQ_MODEL} | Judecător: {judge_name}\n")

    results: list[dict] = []

    for idx, incident in enumerate(incidents_to_evaluate, start=1):
        inc_id = incident["incident_id"]
        title = incident["title"]
        service = incident["service"]
        true_cause = ground_truth_by_incident[inc_id]
        entry = {
            "incident_id": inc_id,
            "title": title,
            "service": service,
            "true_root_cause": true_cause,
            "rca_status": None,
            "outcome": "run_error",
            "counted": False,
            "duration_seconds": 0.0,
            "top1_match": False,
            "topk_match": False,
            "hypotheses_count": 0,
            "evaluations": [],
            "error": None,
        }
        results.append(entry)

        print("=" * 70)
        print(f"[{idx}/{len(incidents_to_evaluate)}] INCIDENT: {inc_id} ({service}) — {title}")
        print(f"   [CAUZA REALĂ]: {true_cause}")
        print("   Rulează investigația...", end="", flush=True)

        t0 = time.time()
        try:
            record = run_investigation(incident_id=inc_id, owner="KPI Evaluator", db_path=eval_db)
        except Exception as exc:
            entry["duration_seconds"] = time.time() - t0
            entry["error"] = f"{type(exc).__name__}: {exc}"
            print(f" EȘUAT ({exc}) după {entry['duration_seconds']:.1f}s.\n")
            save_report(build_report(args.judge, results))
            continue
        entry["duration_seconds"] = time.time() - t0
        entry["rca_status"] = record.status
        print(f" gata în {entry['duration_seconds']:.1f}s (status {record.status}).")

        if record.status == "FAILED":  # a technical failure, not a judgement of the application
            entry["error"] = "FAILED: no usable answer from the agents"
            save_report(build_report(args.judge, results))
            continue

        hypotheses = record.hypotheses
        entry["hypotheses_count"] = len(hypotheses)
        verdicts: list[bool | None] = []

        for h_idx, hyp in enumerate(hypotheses, start=1):
            cand_text = hyp.candidate_root_cause

            if args.judge == "auto":
                is_match, reason = verify_with_llm(cand_text, true_cause)
                symbol = {True: "✅ CORECT", False: "❌ INCORECT", None: "⚠️ FĂRĂ VERDICT"}[is_match]
                print(f"\n   Ipoteza #{h_idx} [{hyp.confidence} - {hyp.confidence_points} pts]:")
                print(f"   • Text:    {cand_text}")
                print(f"   • Arbitru: {symbol}")
                print(f"   • Motiv:   {reason}")
            else:
                is_match, reason = verify_manually(cand_text, true_cause, h_idx)

            verdicts.append(is_match)
            entry["evaluations"].append({
                "hypothesis_id": hyp.hypothesis_id,
                "confidence": hyp.confidence,
                "confidence_points": hyp.confidence_points,
                "candidate_root_cause": cand_text,
                "is_match": is_match,
                "reason": reason,
            })

        top1 = bool(verdicts) and verdicts[0] is True
        topk = any(verdict is True for verdict in verdicts)
        # Without a verdict for a hypothesis that could still change the result, the incident is not counted.
        undetermined = None in verdicts and not top1
        entry["top1_match"] = top1
        entry["topk_match"] = topk
        entry["outcome"] = "judge_error" if undetermined else "evaluated"
        entry["counted"] = not undetermined

        label = "FĂRĂ VERDICT" if undetermined else f"Top-1: {'✅' if top1 else '❌'} | Top-K: {'✅' if topk else '❌'}"
        print(f"\n   >>> Rezultat Incident {inc_id}: {label}\n")
        save_report(build_report(args.judge, results))

    report = build_report(args.judge, results)
    save_report(report)

    counted = report["total_incidents_evaluated"]
    print("=" * 70)
    print("REZULTATE FINALE DEMONSTRAȚIE KPI:")
    print(f"  • Incidente selectate / evaluate:      {report['total_incidents_selected']} / {counted}")
    print(f"  • Top-1 Accuracy (Ipoteza #1 e corectă): {report['top1_matches']}/{counted} ({report['top1_accuracy_percent']:.1f}%)")
    print(f"  • Top-K Accuracy (Cauza în listă):      {report['topk_matches']}/{counted} ({report['topk_accuracy_percent']:.1f}%)")
    print(f"  • Medie ipoteze per incident:          {report['average_hypotheses_per_incident']:.1f}")
    print(f"  • Total ipoteze evaluate:              {report['total_hypotheses_evaluated']} (din care {report['total_hypotheses_correct']} corecte)")
    if report["run_errors"]:
        print(f"  • Excluse (eroare la rulare/FAILED):   {', '.join(report['run_errors'])}")
    if report["judge_errors"]:
        print(f"  • Excluse (judecătorul fără verdict):  {', '.join(report['judge_errors'])}")
    if report["without_hypotheses"]:
        print(f"  • Fără ipoteze (numărate ca ratate):   {', '.join(report['without_hypotheses'])}")
    print("=" * 70)
    print(f"\nRaportul complet a fost salvat în: {OUTPUT_REPORT_PATH}")


if __name__ == "__main__":
    main()
