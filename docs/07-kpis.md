# 7. KPIs and Success Criteria

**Project:** AI-assisted Root Cause Analysis (RCA) application
**Area:** Problem Management, large company
**Last updated:** 2026-08-19

---

## 7.1 What we want to prove

Two things, one for the business and one for the AI.

1. **The investigation is faster.** The draft RCA is ready in minutes instead of days.
2. **The investigation is correct.** The real cause is among the hypotheses the
   application proposes.

The first one alone proves nothing. A system that answers instantly and is wrong is worse
than a slow expert. The two must be read together.

---

## 7.2 The two main KPIs

### KPI 1 — Time to draft RCA

**What it measures:** the time from the moment the Problem Manager starts an RCA until the
draft is ready for the Technical Expert.

**How it is measured:** the application records the start time and the time the draft
reaches the state *pending review*. The same information is visible in the Phoenix trace,
broken down per step, so we can also see which part is slow.

**What it is compared against:** the same investigation done manually. See 7.4.

**Why this one:** it is the whole business case. Today the collecting and correlating takes
days, and this is the part the application replaces.

### KPI 2 — Hypothesis accuracy

**What it measures:** how often the real cause is among the proposed candidate root
causes.

Reported in two ways:

- **First hypothesis correct** — the highest ranked hypothesis is the real cause.
- **Correct among the proposals** — the real cause appears in any of the hypotheses.

**How it is measured:** each mock scenario has a known true cause in the answer key. After
running a scenario, the proposed hypotheses are compared against it. The comparison is
recorded per scenario, so a wrong answer can be examined and not only counted.

**Why this one:** it answers the only question that matters for an expert. If the correct
cause is in the list, the expert reviews. If it is not, the application wasted their time.

---

## 7.3 Supporting measures

These are not the headline numbers, but they explain the two above and show where the
system is weak.

| Measure | What it tells us |
|---|---|
| Evidence coverage | How many of the four sources produced evidence for an investigation. A low number explains a low confidence |
| Retrieval quality | Whether the historical search brought the records that should have been found. Measured with RAGAS on the evaluation set |
| Faithfulness | Whether the written hypotheses stay inside the evidence they cite, without adding anything. Measured with RAGAS |
| Citation validity | The percentage of citations that point to a real evidence record. By design this must be 100 percent, so any other value means a broken guardrail |
| Expert acceptance rate | How many drafts are approved without asking for more evidence. It is read together with KPI 2 and never instead of it, because on its own it measures the reviewer as much as the system |
| Rounds to approval | How many times a draft goes back before it is accepted |
| Expert effort | The time the expert spends inside the application, which is review time instead of investigation time |
| Tool success rate | How many tool calls returned a usable result |

---

## 7.4 How we compare with the manual process

The comparison has to be fair, so both sides work on exactly the same data.

**The manual baseline.** A person performs the investigation for a small number of
scenarios, for example five, using only the mock sources: searching the incidents by
keyword, opening the CMDB, looking through the change list, reading the log file. Each step
is timed, and the conclusion is written down. This is the "before" number, and it is
measured, not estimated.

**The application run.** The same scenarios are then run through the application. The time
and the proposed hypotheses are recorded automatically.

**What is compared.**

| | Manual | With the application |
|---|---|---|
| Time until a draft conclusion exists | measured | measured |
| Number of systems opened by a person | measured | measured |
| Whether the conclusion matches the answer key | checked | checked |
| Evidence that can be traced to a source | checked | checked |

Doing the manual baseline ourselves is slow, which is exactly the point. It gives us a
real number to compare against instead of a claim, and the person doing it will describe
the bottlenecks from document 2 from their own experience.

---

## 7.5 The method of verification

Everything is measured by one script that runs the whole set of scenarios and writes a
results table.

1. Load the mock data and build the ChromaDB collections.
2. Run every scenario through the application, from start to draft.
3. For each scenario, record the time, the hypotheses, the evidence used and the
   calculated confidence.
4. Compare the hypotheses with the answer key.
5. Run RAGAS over the evaluation set for the retrieval measures.
6. Write everything into one table, one row per scenario, plus a summary line.

The run is repeatable. When we change a prompt, a threshold or the retrieval settings, we
run it again and see whether the numbers moved. A change that improves nothing is
reverted.

The results table is kept in the repository, so every number in the final presentation can
be traced back to the run that produced it.

---

## 7.6 Success criteria

The bar is set now, before the measurements, so the result cannot be adjusted afterwards
to look good.

The project is successful if:

- the draft RCA is produced in minutes, and the difference against the manual baseline is
  large enough to be obvious without statistics,
- the real cause appears among the proposed hypotheses in the clear majority of scenarios,
- every citation points to a real evidence record, with no exception,
- no RCA can reach the final state without a recorded human approval,
- for every investigation we can show what was searched, what was decided, on what basis,
  and who approved it.

The exact target values for the first two are set after the first complete run, when we
know what the system actually does. They are written down at that moment, together with
the run they came from.

The project is **not** successful if the application is fast but the correct cause is
usually missing, or if the hypotheses cannot be traced to evidence. Speed without
correctness is not an improvement, and neither is a conclusion nobody can verify.
