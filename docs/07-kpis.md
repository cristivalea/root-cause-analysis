# 7. KPIs and Success Criteria

**Project:** AI-assisted Root Cause Analysis (RCA) application
**Area:** Problem Management, large company
**Last updated:** 2026-10-22

---

## 7.1 What we want to prove

Two things, one for the business and one for the AI.

1. **The investigation needs less human work.** The draft RCA is ready in minutes, a person
   makes far fewer steps, and the runs finish without help.
2. **The investigation is correct.** The real cause is among the hypotheses the
   application proposes, and the confidence it shows can be trusted.

The first one alone proves nothing. A system that answers instantly and is wrong is worse
than a slow expert. The two must be read together.

---

## 7.2 The four main KPIs

The full definitions and calculations are in `docs/KPIS.md`. Each KPI is measured in two
ways:

- **live**, on the real RCAs of the application, where the Technical Expert is the judge;
- **benchmark**, on the 13 stories of the answer key, where the true cause is known.

The KPIs page of the application shows both, for a chosen period (last 7, 30 or 90 days,
or all time), with how each value is calculated and how to read it.

### KPI 1 — Less manual work

**What it measures:** how many steps a person still makes for one RCA, compared with the
11 steps of the manual process.

**How it is measured:** for every RCA the expert decided, the steps are counted from its
history: starting the RCA, every sending to the expert, every decision of the expert,
every further revision started, and reading the final decision. The ideal path is 4 steps.
Reduction = (11 − average) ÷ 11. On the ideal path this is 63.6%.

**Why this one:** it is the business case. Today the collecting and correlating takes days
of human work, and this is the part the application replaces.

### KPI 2 — Investigations that finish on their own

**What it measures:** how often a run reaches a usable analysis without a person stepping in.

**How it is measured:** every run (every revision) that ended is counted. It finished on
its own when it produced an analysis. It needed a person when it stopped on a technical
error, or when the guardrail refused the draft in every attempt. By design, 5 of the 8
stages of an RCA are automatic (62.5%).

### KPI 3 — The right cause is found

**What it measures:** how often the real cause is among the proposed candidate causes.

Reported in two ways:

- **Top-1** — the highest ranked hypothesis is the real cause.
- **Top-K** — the real cause appears in any of the hypotheses.

**How it is measured:** live, of the RCAs the expert decided (validated, rejected, or sent
to manual review after the last request): Top-K = validated ÷ decided; Top-1 = validated
with the hypothesis that was first in that revision ÷ decided. In the benchmark, an LLM
judge of another model family (Gemini by default) compares each hypothesis with the true
cause of the answer key: the same component and the same failure mechanism.

**Why this one:** it answers the only question that matters for an expert. If the correct
cause is in the list, the expert reviews. If it is not, the application wasted their time.

### KPI 4 — Confidence you can trust

**What it measures:** whether HIGH, MEDIUM and LOW mean what they say.

**How it is measured:** live, every decision of the expert is grouped by the confidence of
the first hypothesis of the revision it was taken on, and the share approved is computed
per level. It is well calibrated when HIGH is approved more often than MEDIUM, and MEDIUM
more often than LOW. In the benchmark, the confidence of the first hypothesis must be one
the answer key allows for that story, for example LOW for a story with little evidence.

**Why this one:** an overconfident system is as harmful as a wrong one. The expert must be
able to rely on the label.

---

## 7.3 Supporting measures

These are not the headline numbers, but they explain the four above and show where the
system is weak.

| Measure | What it tells us |
|---|---|
| Duration of a run | The time from Start RCA to the draft, saved on every revision |
| Median time to the expert's decision | Shown on the KPIs page, for the RCAs decided in the period |
| Current situation | Open problems, problems in investigation, in manual review, RCAs awaiting the expert |
| RCAs started per week | Validated, rejected, still in progress |
| Retrieval quality | Whether the historical search brought the records that should have been found. Measured with RAGAS on the 26 evaluation questions |
| Faithfulness | Whether the written hypotheses stay inside the evidence they cite. Measured with RAGAS |
| Citation validity | The percentage of citations that point to a real evidence record. By design this must be 100 percent, so any other value means a broken guardrail |
| Citation tracing | For every expected citation of the answer key: did it reach the ledger, and was it cited by the main hypothesis |
| Tool runs | How many tool calls returned a usable result, and which failed |
| Model usage | Requests, tokens and time per step, saved on every revision |

---

## 7.4 How we compare with the manual process

The comparison has to be fair, so both sides work on the same process.

**The manual baseline.** The manual RCA is described step by step in document 2 and in
`docs/KPIS.md`: 11 human interactions, from reading the reports to the final approval, in
one to four weeks. In the manual process no stage completes without a person, so its
self-resolution rate is 0%.

**The application.** The same work needs 4 human interactions on the ideal path: start the
analysis, send the draft to the expert, the decision of the expert, and reading the
decision. The investigation itself runs without a person.

**What is compared.**

| | Manual | With the application |
|---|---|---|
| Human interactions for one RCA | 11 | 4 on the ideal path, measured on every RCA |
| Stages done without a person | 0 of 8 | 5 of 8 by design, measured on every run |
| Whether the conclusion matches the true cause | not measured | Top-1 and Top-K |
| Evidence that can be traced to a source | not always | every citation, checked by code |

The 11 manual steps are the team's description of the old process, not a measurement.
The values of the application are measured on its own records.

---

## 7.5 The method of verification

Two kinds of measurement, both repeatable.

**Live, inside the application.** The KPIs are calculated by `rca/kpis.py` from what is
stored: the problems, the RCAs, their revisions and their status history. Nothing is
changed. The API returns them at `GET /api/v1/kpis`.

**Benchmark, with scripts.** Each script runs the 13 stories on a temporary copy of the
database, so the application data is untouched, and writes a JSON report after every story:

| Script | What it measures | Report |
|---|---|---|
| `scripts/eval_kpi_accuracy.py` | KPI 3, Top-1 and Top-K, with the LLM judge (`--judge auto`) or a person (`--judge manual`) | `data/evaluation/kpi_accuracy_report.json` |
| `scripts/eval_kpi_confidence.py` | KPI 4, the calibration of the confidence | `data/evaluation/kpi_confidence_report.json` |
| `scripts/evaluate_ragas.py` | Retrieval quality, threshold calibration, faithfulness | `results/ragas/` |
| `scripts/baseline_agents.py` | The agents on every story and on the expert follow-ups | `results/baseline/` |
| `scripts/trace_citations.py` | Where each expected citation got lost | `results/citations/` |
| `scripts/compare_variants.py` | A change to the agents against the code without it, on the same model | `results/baseline/` |

A run that fails on a technical error is not counted, and is listed in the report. A run
that ends in manual review counts as a miss. The KPIs page shows a benchmark only when its
report was written by the current version of the scripts.

When we change a prompt, a threshold or the retrieval settings, we run the scripts again
and see whether the numbers moved. A change that improves nothing is reverted. The results
are kept in the repository, so every number in the final presentation can be traced back
to the run that produced it.

---

## 7.6 Success criteria

The bar is set before the measurements, so the result cannot be adjusted afterwards to
look good.

The project is successful if:

- the draft RCA is produced in minutes, and the human steps go down from 11 to close to 4,
- most runs finish on their own,
- the real cause appears among the proposed hypotheses in the clear majority of scenarios,
- a HIGH confidence is approved more often than a MEDIUM, and a MEDIUM more often than a LOW,
- every citation points to a real evidence record, with no exception,
- no RCA can be validated without a recorded human approval,
- for every investigation we can show what was searched, what was decided, on what basis,
  and who approved it.

The project is **not** successful if the application is fast but the correct cause is
usually missing, or if the hypotheses cannot be traced to evidence. Speed without
correctness is not an improvement, and neither is a conclusion nobody can verify.
