# 6. Reasoning, Decision and Execution

**Project:** AI-assisted Root Cause Analysis (RCA) application
**Area:** Problem Management, large company
**Last updated:** 2026-08-19

---

## 6.1 The principle

The application is split in two parts that never mix.

**The model proposes. The code executes.**

| The model does | The code does |
|---|---|
| Reads the incident and decides what to look for | Runs the queries |
| Judges whether a past case is really similar | Fetches CMDB items, changes and logs |
| Correlates the evidence and writes the hypotheses | Checks the output, calculates the confidence, saves the record |

The model never writes anything into the database, never calls a system directly, and
never decides that something is final. Its answer is always a proposal that has to pass
through validation before it goes any further.

This has a practical reason. A language model can be wrong in a way that still sounds
correct. If the wrong answer can only ever be a proposal, a wrong answer costs a review.
If it could be executed, a wrong answer costs an incident.

---

## 6.2 The three agents that reason

### Investigation Planner

| | |
|---|---|
| Input | The incident and the incidents that look similar to it |
| Output | The investigation plan: the service, the time window to search, the sources to check, the search queries |
| Must not | Draw any conclusion about the cause |

The time window is the important part of the plan. It usually starts a few hours before
the incident was detected, but a slow failure needs a wider window than a sudden one. This
is a judgement, which is why it is done by the model and not by a fixed rule.

### Historical RCA Agent

| | |
|---|---|
| Input | The plan and the search queries |
| Output | The past incidents and past RCAs that are relevant, each with a short reason |
| Must not | Invent an identifier, or keep a record it cannot justify |

The search returns the records that look closest. That is not the same as relevant. This
agent reads what came back and drops the ones that only share the wording. If nothing is
relevant, it says so, and the investigation continues without history.

### RCA Reasoning Agent

| | |
|---|---|
| Input | The evidence ledger, and nothing else |
| Output | The candidate root causes, with reasons, cited evidence and recommended checks |
| Must not | Say "root cause". Only "candidate root cause" |

This is the only place in the application where a conclusion is formed.

It is asked to think step by step before answering: first what the evidence has in common,
then what could explain it, then what argues against it. That reasoning is recorded in
Phoenix, because it explains how the answer was reached, but it does not go into the RCA
record. The record keeps only the structured conclusions.

Looking for what argues against a hypothesis is asked as its own step, not left to good
intentions. For every hypothesis the agent goes back through the evidence ledger and looks
for the facts that do not fit: a change that happened after the first symptom, a similar
past incident that had a different cause, a log pattern that also appears on days without
an incident. What it finds goes into the contradicting evidence, and the confidence rules
lower the level because of it. An empty list is allowed, but it has to be the result of
looking.

The agent must produce **at least two hypotheses**, or state clearly why only one is
possible. This is a rule against the most common mistake in a real investigation, which is
stopping at the first explanation that sounds reasonable.

It must also list **what could not be checked**: missing metrics, a short log window, no
data from other environments.

---

## 6.3 The tools that execute

| Tool | What it does | Result |
|---|---|---|
| CMDB lookup | Reads the dependencies of a service | Always the same for the same input |
| Change lookup | Reads the changes in a time window | Always the same for the same input |
| Log lookup | Reads the log lines for a service and a window | Always the same for the same input |
| Evidence ledger | Records every fact found, with its source | A numbered list |
| Confidence calculation | Turns the evidence into a level | A number and a band |
| Validation | Checks the model output | Accepted or refused |
| RCA record store | Saves the draft, the decisions and the final RCA | A stored record |

These tools are ordinary Python functions. They can be tested without a model: give them
an input, check the output. That is what makes the separation real and not just a claim in
a document.

---

## 6.4 Controlling the model output

Every answer from a model is treated as untrusted text until it passes three checks.

**1. The shape.** The answer must match a schema written with Pydantic. If a field is
missing, has the wrong type or an unknown value, the answer is refused.

```python
class Hypothesis(BaseModel):
    hypothesis_id: str
    candidate_root_cause: str
    reasons: list[str]
    supporting_evidence: list[str]      # only evidence ids
    contradicting_evidence: list[str]
    recommended_validation: list[str]

class DraftRCA(BaseModel):
    incident_id: str
    investigation_summary: str
    observed_patterns: list[str]
    hypotheses: list[Hypothesis]
    not_checked: list[str]
    suggested_workaround: str | None
    change_likely_required: bool
```

The confidence is not in this schema on purpose. The model does not get to state it.

The last two fields are suggestions about what should happen next, and nothing more. The
application does not apply a workaround and does not open a change. It writes down what a
person should consider, and a person decides.

**2. The citations.** Every evidence id in the answer must exist in the evidence ledger. A
hypothesis that cites something which was never found is refused. This is a plain
comparison between two lists, done in code, and it is what makes a hallucinated source
impossible rather than unlikely.

**3. The content rules.** The answer must contain at least two hypotheses or an
explanation, and every hypothesis must have at least one piece of supporting evidence. A
hypothesis with no evidence is an opinion, and an opinion is not an RCA.

If any check fails, the agent is asked again, with the error included in the request. After
**three failed attempts** the RCA is escalated to a human investigation. A model that
cannot produce a valid answer three times in a row will not produce one on the fourth try,
and an application that keeps retrying silently is worse than one that stops and says so.

---

## 6.5 How the confidence is calculated

The confidence is calculated by our own rules, from things that can be counted. The model
writes the reasons, the code decides the level.

| Evidence found | Points |
|---|---|
| Log lines that match the described symptom | 2 |
| A change on the affected service or on a direct dependency, inside the window, before detection | 2 |
| A past RCA with the same cause on the same service | 2 |
| A similar past incident, without an RCA | 1 |
| A CMDB dependency that confirms the technical path | 1 |

| Total | Level |
|---|---|
| 5 or more, from at least three different sources | HIGH |
| 3 or 4 | MEDIUM |
| 2 or less | LOW |

Two rules on top:

- **Without log evidence, a hypothesis can never be HIGH.** The logs are the only place
  where the failure was actually observed. Everything else is context around it.
- **Contradicting evidence lowers the level by one band.** If something argues against the
  hypothesis, the expert should see a weaker claim, not a strong one with a footnote.

Why calculate it instead of asking the model: a level written by a model cannot be
explained, cannot be tuned and cannot be defended. A level calculated from rules can be
read by anyone, adjusted when it is wrong, and justified in front of an auditor. The point
values above are the starting point and are tuned against the answer key, and any change
is written down with the reason.

---

## 6.6 The guardrails

A guardrail is a rule that stops the flow. These are the ones in the application.

| Rule | What it prevents |
|---|---|
| The output must match the schema | Broken or unusable data entering the flow |
| Every citation must exist in the evidence ledger | Invented sources |
| Every hypothesis must have supporting evidence | Conclusions without proof |
| At least two hypotheses, or a reason why not | Stopping at the first idea |
| The final root cause stays empty until a human approves | The application deciding by itself |
| Only records older than the incident are searched | Finding the answer in a document written afterwards |
| Three failed validations end in escalation | An endless retry loop |
| Two rounds of extra evidence end in escalation | An endless review loop |
| Every human decision is recorded with who and when | An approval nobody can explain later |

---

## 6.7 The human approval point

### Where it is

Between the draft and the validated RCA. The RCA record has a field for the final root
cause, and that field stays empty until a Technical Expert approves. There is no path in
the application where it is filled in automatically.

### Why it is always required

The risky action here is not writing a database row. It is **declaring a cause**. An RCA
decides what the company fixes next: a configuration change, a code change, money and
people assigned to a problem. If the cause is wrong, the corrective action is wrong, the
real problem stays, and the incident comes back after everyone believed it was solved.

The cost of a wrong approval is a repeated production incident. The cost of a review is a
few minutes of an expert who was going to be involved anyway. That is why there is no
confidence level, however high, that lets the application approve on its own. A HIGH
confidence draft is a well-supported proposal, not a decision.

### The thresholds

| Situation | What the application does |
|---|---|
| Any draft | Goes to the Technical Expert. Always |
| No hypothesis above LOW | Goes to the expert, marked as weakly supported, with the suggestion to request more evidence rather than approve |
| Expert requests more evidence | A narrow, targeted investigation runs, then back to the expert. Allowed twice |
| Expert rejects | A new investigation runs, using the reason given |
| Two rounds of extra evidence are not enough | Escalated to a manual investigation |
| Expert approves | The root cause is filled in, and the RCA moves to the Problem Manager |

### What is recorded

For every decision: who acted, in which role, when, what they chose, the comment they
wrote, and which version of the draft they were looking at. This goes into the audit trail
in the database and into the Phoenix trace.

That is the answer to the question an auditor asks: what did the application decide, on
what basis, who approved it, and what was executed.
