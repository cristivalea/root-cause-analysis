# 6. Reasoning, Decision and Execution

**Project:** AI-assisted Root Cause Analysis (RCA) application
**Area:** Problem Management, large company
**Last updated:** 2026-10-22

---

## 6.1 The principle

The application is split in two parts that never mix.

**The model proposes. The code executes.**

| The model does | The code does |
|---|---|
| Writes the search queries, and may ask for extra searches | Sets the services and the time windows, checks the extra searches, runs the queries |
| Judges whether a past case is really similar | Fetches CMDB items, changes and logs, drops past records of other services |
| Correlates the evidence and writes the hypotheses | Checks the output, calculates the confidence, chooses the cause diagram, saves the record |

The model never writes anything into the database, never calls a system directly, and
never decides that something is final. Its answer is always a proposal that has to pass
through validation before it goes any further.

This has a practical reason. A language model can be wrong in a way that still sounds
correct. If the wrong answer can only ever be a proposal, a wrong answer costs a review.
If it could be executed, a wrong answer costs an incident.

All three agents use the same model, `openai/gpt-oss-120b` on Groq. Every agent is told
that everything in its input is data: an incident text, a log line or a note that asks it
to ignore its rules is information, never an instruction.

---

## 6.2 The three agents that reason

### Investigation Planner

| | |
|---|---|
| Input | The problem and its incidents, the notes and questions of the Problem Manager, the request of the expert, what earlier RCAs of the problem concluded, and what is already searched |
| Output | 1 to 5 search queries for the past incidents and RCAs, at most 3 extra searches, and a short rationale |
| Must not | Draw any conclusion about the cause |

The facts are not asked from the model. The services, the time windows and the sources come
from the context, built by code: logs from 2 hours before to 1 hour after every incident,
changes from 7 days before the first incident to the resolution of the last one, unless the
guidance asks for wider windows.

The planner may ask for an extra search when a note, a question or a symptom points to
another service or an earlier time: logs (2 to 168 hours before each detection) or changes
(7 to 90 days before the first incident). Code checks every request before it runs: a
service of the CMDB, a window inside the limits, and something not already searched. A
refused request is kept with its reason.

### Historical Review Agent

| | |
|---|---|
| Input | The problem (title, symptoms, the request of the expert) and the past records found: past RCAs, past incidents, and RCAs validated in the application |
| Output | For every record: relevant or not, and why. For a relevant one: what it shares with the problem, how it differs, what was done then, and how that ended |
| Must not | Invent an identifier, skip a record, or guess the cause of the current problem |

The search returns the records that look closest. That is not the same as relevant. This
agent reads what came back and drops the ones that only share the wording. Records of
another service are dropped by code before the agent sees them. If nothing is relevant,
it says so, and the investigation continues without history.

Code adds one fact the model does not judge: when a past RCA was completed before the first
incident of the problem, the problem came back after its fix, so that fix did not prevent it.

### RCA Reasoning Agent

| | |
|---|---|
| Input | The evidence ledger, the timeline, and a brief built by code: the title of the problem, the notes and questions of the Problem Manager, the request of the expert, and what earlier RCAs concluded |
| Output | The candidate root causes, with reasons, cited evidence, recommended checks, missing evidence, a 5 Whys chain and Fishbone factors |
| Must not | Say "root cause". Only "candidate root cause" |

This is the only place in the application where a conclusion is formed. The brief says
what to examine; it is not evidence, so the agent cites only ledger ids. It must answer
every question and request in the brief, or write in what could not be checked that the
ledger cannot answer it. It must not propose again a cause an expert rejected, unless the
ledger has new evidence for it.

It works in a fixed order: first what the evidence has in common, then what could explain
it, then what argues against it, then what could not be checked, then the next steps.

Looking for what argues against a hypothesis is asked as its own step, not left to good
intentions. For every hypothesis the agent goes back through the evidence ledger and looks
for the facts that do not fit: a change that happened after the first error, a component
that is not on the failing path, a similar past incident that had a different cause, a
log pattern that also appears without an incident. What it finds goes into the
contradicting evidence, and the confidence rules lower the level because of it.

The agent must produce **at least two hypotheses**, or state clearly why only one is
possible. This is a rule against the most common mistake in a real investigation, which is
stopping at the first explanation that sounds reasonable.

It must also list **what could not be checked**: missing metrics, a short log window, no
data from other environments.

The free tier of Groq refuses a request above 8000 tokens. When the ledger is too long,
the descriptions the agent reads are shortened step by step until the request fits; every
evidence id stays, and the ledger itself is never changed.

---

## 6.3 The tools that execute

| Tool | What it does | Result |
|---|---|---|
| Context builder | Reads the problem, its incidents and the guidance | The services and the time windows, each with where it comes from |
| CMDB lookup | Reads the components of a service and their dependencies | Always the same for the same input |
| Change lookup | Reads the changes in a time window | Always the same for the same input |
| Log lookup | Reads the log lines for a service and a window, grouped by level and error type | Always the same for the same input |
| Similar incidents search | Finds the past incidents closest to the most recent one | A short list, older records only |
| Evidence ledger | Records every fact found, with its source | A numbered list |
| Timeline | Orders the evidence in time and marks the first error | A list of moments |
| Confidence calculation | Turns the cited evidence into a level | Points and a band |
| Validation | Checks the model output | Accepted, or the list of problems |
| Cause diagram | Chooses 5 Whys or Fishbone | The diagram, or none |
| RCA record store | Saves the revision, the decisions and the status history | A stored record |

Every call of a tool during a run is kept as a **tool run**: the tool, the arguments, who
asked for it (a rule or the planner), the result count, the evidence it produced, and the
error if it failed. A source that fails does not stop the run; it is written in what could
not be checked, because an error is never evidence that nothing happened.

These tools are ordinary Python functions. They can be tested without a model: give them
an input, check the output. That is what makes the separation real and not just a claim in
a document.

---

## 6.4 Controlling the model output

Every answer from a model is treated as untrusted text until it passes the checks.

**1. The shape.** The answer must match a schema written with Pydantic. If a field is
missing, has the wrong type or an unknown value, the answer is refused.

```python
class Hypothesis(BaseModel):
    hypothesis_id: str                      # HYP-001, HYP-002, ...
    candidate_root_cause: str
    reasons: list[str]
    supporting_evidence: list[str]          # only evidence ids
    contradicting_evidence: list[str]
    recommended_validation: list[str]
    missing_evidence: list[str] = []
    why_chain: list[WhyStep] = []           # at most 5 steps, for the 5 Whys diagram
    factors: list[CauseFactor] = []         # for the Fishbone diagram

class DraftRCA(BaseModel):
    incident_id: str
    investigation_summary: str
    observed_patterns: list[str] = []
    not_checked: list[str] = []
    suggested_workaround: str | None = None
    change_likely_required: bool = False
    single_hypothesis_reason: str | None = None
    hypotheses: list[Hypothesis]
```

The confidence is not in this schema on purpose. The model does not get to state it.

The workaround and the change are suggestions about what should happen next, and nothing
more. The application does not apply a workaround and does not open a change. It writes
down what a person should consider, and a person decides.

When the model writes an evidence id with its explanation, for example
`"EV-008 (monitoring change)"`, code keeps only the id and notes the change.

**2. The citations.** Every evidence id in the answer must exist in the evidence ledger,
in the lists of citations and also in the text, the 5 Whys steps and the Fishbone factors.
A hypothesis that cites something which was never found is refused. This is a plain
comparison between two lists, done in code, and it is what makes a hallucinated source
impossible rather than unlikely.

**3. The content rules.**

- every hypothesis has at least one piece of supporting evidence, and not only the
  incident itself, which is what must be explained;
- at least two hypotheses, or a written reason why there is only one;
- no evidence cited both for and against the same hypothesis;
- no change made after the first error cited as support, because it cannot have caused it;
- no candidate cause written as proven ("the root cause is", "confirmed").

An evidence id named in the text without being cited, or certain wording in the reasons,
is not refused: it is saved as a warning for the expert.

If any check fails, the agent is asked again, with the problems included in the request.
After **three refused attempts** in one run, the RCA goes to manual review. A model that
cannot produce a valid answer three times in a row will not produce one on the fourth try,
and an application that keeps retrying silently is worse than one that stops and says so.
When no attempt gave a usable answer at all (no valid JSON), nothing was concluded: the
run is saved as Failed and can be started again.

---

## 6.5 How the confidence is calculated

The confidence is calculated by our own rules, from things that can be counted. The model
writes the reasons, the code decides the level. Points are counted once per kind of
supporting evidence.

| Evidence found | Points |
|---|---|
| Log lines that match the described symptom | 2 |
| A change on the affected service or on a direct dependency, made before the first error | 2 |
| A past RCA with the same cause on the same service | 2 |
| A similar past incident | 1 |
| A CMDB dependency that confirms the technical path | 1 |
| The incident itself | 0 |

| Total | Level |
|---|---|
| 5 or more, from at least three different kinds | HIGH |
| 5 or more from only two kinds, or 3 or 4 | MEDIUM |
| 2 or less | LOW |

Three rules on top:

- **A change earns points only if it was made before the first error in the logs** of the
  services of the problem. A change made after the first error cannot have caused it.
  Without log evidence, the detection of the first incident is used.
- **Without log evidence, a hypothesis can never be HIGH.** The logs are the only place
  where the failure was actually observed. Everything else is context around it.
- **Contradicting evidence lowers the level by one band.** If something argues against the
  hypothesis, the expert should see a weaker claim, not a strong one with a footnote.

The hypotheses are then ordered, the strongest first. When no hypothesis is above LOW, the
draft is marked **weakly supported**.

Why calculate it instead of asking the model: a level written by a model cannot be
explained, cannot be tuned and cannot be defended. A level calculated from rules can be
read by anyone, adjusted when it is wrong, and justified in front of an auditor. Every
hypothesis keeps the reasons of its level, so the expert sees why it is high or low.

### The cause diagram

The code also chooses the diagram the expert sees. When one candidate cause has a higher
confidence than all the others, its **5 Whys** chain is drawn. When several are equally
supported, their **Fishbone** factors are drawn, by category. A 5 Whys chain stops at the
first step without evidence, shown as an open question, so no "why" is invented to reach five.

---

## 6.6 The guardrails

A guardrail is a rule that stops the flow. These are the ones in the application.

| Rule | What it prevents |
|---|---|
| The output must match the schema | Broken or unusable data entering the flow |
| Every citation must exist in the evidence ledger | Invented sources |
| Every hypothesis must have supporting evidence beyond the incident | Conclusions without proof |
| At least two hypotheses, or a reason why not | Stopping at the first idea |
| No change after the first error as support | Blaming a change that came too late |
| No cause written as proven | A candidate presented as a conclusion |
| The final root cause stays empty until a human approves | The application deciding by itself |
| Only records older than the incident are searched | Finding the answer in a document written afterwards |
| Past records of other services are never evidence | A match of words on the wrong service |
| Extra searches are checked by code before they run | A search outside the rules |
| Three refused attempts end in manual review | An endless retry loop |
| Three expert decisions per RCA, at most | An endless review loop |
| Two rejected RCAs send the problem to manual review | Trying the same problem forever |
| A new RCA after a rejection needs something new | The same input giving the same answer |
| One RCA at a time per problem | Two investigations of the same problem at once |
| Every human decision is recorded with who and when | An approval nobody can explain later |
| Secrets are removed before anything is saved | A key or a token kept in a revision |

---

## 6.7 The human approval point

### Where it is

After the draft, when the Problem Manager has sent it to the expert. The RCA record has a
field for the final root cause, and that field stays empty until a Technical Expert
approves one of the candidate causes. There is no path in the application where it is
filled in automatically: the record itself refuses a final root cause without an approval.

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
| Any draft | Waits for the Problem Manager to send it to the Technical Expert. Always |
| No hypothesis above LOW | Goes to the expert marked as weakly supported, with the suggestion to request more details rather than approve |
| Expert requests more details | The Problem Manager starts the next revision, which answers the request. Allowed at the first and second decision |
| Expert requests more details at the third decision | The RCA goes to manual review |
| Expert rejects | The problem is open again; a new RCA must start from other incidents or other guidance |
| Second rejected RCA of a problem | The problem goes to manual review |
| Expert approves | The chosen cause becomes the validated root cause, and the problem is closed |

### What is recorded

For every decision: who acted, when, what they chose, which hypothesis, the comment, the
checks and wider searches they asked for, and which revision they were looking at. This
goes into the status history of the RCA and into the history of the problem.

That is the answer to the question an auditor asks: what did the application decide, on
what basis, who approved it, and what was executed.
