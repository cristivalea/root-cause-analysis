#!/usr/bin/env python3
"""Evaluare KPI: Acuratețea Ipotezelor pe baza incidentelor reale.

Măsoară Top-1 și Top-K Accuracy comparând ipotezele produse de pipeline
cu datele de referință din answer_key.json.

Utilizare:
    python scripts/eval_kpi_accuracy.py
    python scripts/eval_kpi_accuracy.py --judge manual
    python scripts/eval_kpi_accuracy.py --incident INC-2026-00482
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

from rca import llm
from rca.config import DB_PATH, GROQ_MODEL
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


def verify_with_llm(candidate: str, true_cause: str) -> tuple[bool, str]:
    """Apelează modelul LLM prin Groq pentru a verifica echivalența semantică."""
    user_input = (
        f"CAUZA REALĂ (Ground Truth):\n{true_cause}\n\n"
        f"IPOTEZA CANDIDATĂ:\n{candidate}\n\n"
        "Identifică ipoteza candidată aceeași problemă tehnică de bază?"
    )
    try:
        res: MatchVerdict = llm.ask_json(
            instructions=JUDGE_PROMPT,
            user_input=user_input,
            schema=MatchVerdict,
        )
        return res.is_match, res.reason
    except Exception as exc:
        return False, f"Eroare arbitraj LLM: {exc}"


def verify_manually(candidate: str, true_cause: str, hyp_index: int) -> tuple[bool, str]:
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
        help="Modul de arbitrare: 'auto' (LLM Judge via Groq) sau 'manual' (operator uman)",
    )
    parser.add_argument(
        "--incident",
        type=str,
        default=None,
        help="Rulează un singur incident specific (ex: INC-2026-00482)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if not INCIDENTS_PATH.exists() or not ANSWER_KEY_PATH.exists():
        sys.exit("Eroare: Fișierele data/sources/incidents.json sau data/evaluation/answer_key.json lipsesc.")

    # 1. Încărcăm lista de incidente sursă
    with INCIDENTS_PATH.open(encoding="utf-8") as f:
        all_incidents: list[dict] = json.load(f)

    # 2. Încărcăm cheia de răspunsuri și mapăm cauza reală direct pe incident_id
    with ANSWER_KEY_PATH.open(encoding="utf-8") as f:
        answer_key: dict = json.load(f)

    ground_truth_by_incident: dict[str, str] = {
        data["target_incident"]: data["true_root_cause"]
        for data in answer_key.values()
    }

    # 3. Filtrăm incidentele care au cheie de control documentată
    incidents_to_evaluate = [
        inc for inc in all_incidents
        if inc["incident_id"] in ground_truth_by_incident
        and (args.incident is None or inc["incident_id"] == args.incident)
    ]

    if not incidents_to_evaluate:
        sys.exit("Nu s-au găsit incidente eligibile pentru evaluare.")

    print(f"=== EVALUARE KPI: ACURATEȚEA IPOTEZELOR ({len(incidents_to_evaluate)} incidente) ===")
    print(f"Model: {GROQ_MODEL} | Mod judecător: {args.judge.upper()}\n")

    top1_success = 0
    topk_success = 0
    total_hypotheses_evaluated = 0
    total_hypotheses_correct = 0
    results_detail = []

    for idx, incident in enumerate(incidents_to_evaluate, start=1):
        inc_id = incident["incident_id"]
        title = incident["title"]
        service = incident["service"]
        true_cause = ground_truth_by_incident[inc_id]

        print("=" * 70)
        print(f"[{idx}/{len(incidents_to_evaluate)}] INCIDENT: {inc_id} ({service}) — {title}")
        print(f"   [CAUZA REALĂ]: {true_cause}")
        print("   Rulează investigația...", end="", flush=True)

        t0 = time.time()
        record = run_investigation(
            incident_id=inc_id,
            owner="KPI Evaluator",
            db_path=DB_PATH,
        )
        elapsed = time.time() - t0
        print(f" gata în {elapsed:.1f}s. Evaluare ipoteze:")

        hypotheses = record.hypotheses
        total_hypotheses_evaluated += len(hypotheses)

        is_top1 = False
        is_topk = False
        evaluations = []

        # Evaluăm fiecare ipoteză generată
        for h_idx, hyp in enumerate(hypotheses, start=1):
            cand_text = hyp.candidate_root_cause

            if args.judge == "auto":
                is_match, reason = verify_with_llm(cand_text, true_cause)
                # Afișăm ipoteza și verdictul dat de Groq
                symbol = "✅ CORECT" if is_match else "❌ INCORECT"
                print(f"\n   Ipoteza #{h_idx} [{hyp.confidence} - {hyp.confidence_points} pts]:")
                print(f"   • Text:    {cand_text}")
                print(f"   • Arbitru: {symbol}")
                print(f"   • Motiv:   {reason}")
            else:
                is_match, reason = verify_manually(cand_text, true_cause, h_idx)

            if is_match:
                total_hypotheses_correct += 1
                is_topk = True
                if h_idx == 1:
                    is_top1 = True

            evaluations.append({
                "hypothesis_id": hyp.hypothesis_id,
                "confidence": hyp.confidence,
                "confidence_points": hyp.confidence_points,
                "candidate_root_cause": cand_text,
                "is_match": is_match,
                "reason": reason,
            })

        if is_top1:
            top1_success += 1
        if is_topk:
            topk_success += 1

        print(f"\n   >>> Rezultat Incident {inc_id}: Top-1: {'✅' if is_top1 else '❌'} | Top-K: {'✅' if is_topk else '❌'}\n")

        results_detail.append({
            "incident_id": inc_id,
            "title": title,
            "service": service,
            "true_root_cause": true_cause,
            "duration_seconds": elapsed,
            "top1_match": is_top1,
            "topk_match": is_topk,
            "hypotheses_count": len(hypotheses),
            "evaluations": evaluations,
        })

    # 4. Calcul metrici globale
    total_incidents = len(incidents_to_evaluate)
    top1_pct = (top1_success / total_incidents) * 100 if total_incidents else 0.0
    topk_pct = (topk_success / total_incidents) * 100 if total_incidents else 0.0
    avg_hypotheses = total_hypotheses_evaluated / total_incidents if total_incidents else 0.0

    print("=" * 70)
    print("REZULTATE FINALE DEMONSTRAȚIE KPI:")
    print(f"  • Total incidente investigate:         {total_incidents}")
    print(f"  • Top-1 Accuracy (Ipoteza #1 e corectă): {top1_success}/{total_incidents} ({top1_pct:.1f}%)")
    print(f"  • Top-K Accuracy (Cauza în listă):      {topk_success}/{total_incidents} ({topk_pct:.1f}%)")
    print(f"  • Medie ipoteze per incident:          {avg_hypotheses:.1f}")
    print(f"  • Total ipoteze evaluate:              {total_hypotheses_evaluated} (din care {total_hypotheses_correct} corecte)")
    print("=" * 70)

    # 5. Salvare raport JSON
    OUTPUT_REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    report_data = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "judge_mode": args.judge,
        "total_incidents_evaluated": total_incidents,
        "top1_accuracy_percent": round(top1_pct, 2),
        "topk_accuracy_percent": round(topk_pct, 2),
        "average_hypotheses_per_incident": round(avg_hypotheses, 2),
        "total_hypotheses_evaluated": total_hypotheses_evaluated,
        "total_hypotheses_correct": total_hypotheses_correct,
        "incidents": results_detail,
    }
    with OUTPUT_REPORT_PATH.open("w", encoding="utf-8") as f:
        json.dump(report_data, f, indent=2, ensure_ascii=False)

    print(f"\nRaportul complet a fost salvat în: {OUTPUT_REPORT_PATH}")


if __name__ == "__main__":
    main()