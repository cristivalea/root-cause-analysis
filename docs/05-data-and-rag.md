# 5. Data Design and RAG

**Project:** AI-assisted Root Cause Analysis (RCA) application
**Area:** Problem Management, large company
**Last updated:** 2026-10-22

---

## 5.1 What data the application needs

The investigation answers four questions, and each one needs its own source.

| Question | Source | Type |
|---|---|---|
| Did something similar happen before? | Past incidents and past RCA documents | Text, searched by meaning |
| What does this service depend on? | CMDB | Structured, direct lookup |
| What changed before the incidents? | Change records | Structured, direct lookup |
| What do the logs show? | Log entries | Structured, direct lookup |

The application also produces its own data: the problems and their history, the RCAs with
their revisions and decisions, the evidence, and the user accounts.

All source data is mock data, built to look realistic. Everything structured is kept in
one SQLite file (`data/rca_sources.sqlite3`); the vectors are kept in ChromaDB
(`chroma_db/`).

---

## 5.2 Entities

### Incident

The incidents that make up a problem, and the past incidents used for comparison.

| Field | Meaning |
|---|---|
| incident_id | Identifier, for example INC-2026-00482 |
| title | Short description |
| description | What the users experienced |
| severity | SEV-1 to SEV-4 |
| status | Resolved, closed |
| service | The affected technical service |
| business_service | The business service on top of it |
| environment | Production, test |
| detected_at, resolved_at | Start and end of the incident |
| duration_minutes | Calculated |
| affected_regions | List of regions |
| impact | Failed transactions, affected customers, peak error rate |
| symptoms | List of observed symptoms |
| initial_mitigation | What was done to restore the service |
| reported_by | Who reported it |
| ci_id | The CMDB item where the symptoms were seen |
| assignment_group, reassignment_count, reopen_count | Which team owned the ticket, how often it moved between teams, how often it was reopened |
| rca_required, rca_reason | Whether an analysis is needed, and why |

An incident never carries the answer: a record with an unknown field is refused when it is
loaded.

### Incident event

One step in the life of an incident ticket. The events give the timeline of the incident.

| Field | Meaning |
|---|---|
| event_id | Identifier, for example EVT-2026-00482-01 |
| incident_id | The incident |
| timestamp | When it happened |
| action | Opened, assigned, reassigned, waiting for the caller or a vendor, resumed, workaround, resolved, reopened, closed |
| state | New, In Progress, On Hold, Resolved, Closed |
| assignment_group | The team at that moment |
| note | What was done |

### Problem

The unknown cause behind one or more incidents. Every RCA starts from a problem.

| Field | Meaning |
|---|---|
| problem_id | Identifier, for example PRB-2026-00106 |
| title, description | Taken from the most recent incident, unless the Problem Manager writes them |
| status | Open, In investigation, Manual review, Closed |
| priority | P1 to P4, from the most severe incident: SEV-1 is P1 |
| services | The services of its incidents |
| incidents | Its incidents, each with who linked it and when |
| guidance | The saved guidance for the investigation: notes, questions, more services, wider windows |
| created_at, created_by | When and by whom |
| closed_at, close_reason, rca_id | When and why it was closed, and the RCA that closed it |

An incident belongs to one problem at most, and a problem always has at least one incident.

### Past RCA document

The knowledge the company already has. Each one is a Markdown file in
`data/knowledge_base/rcas/`.

| Field | Meaning |
|---|---|
| rca_id | Identifier, for example RCA-2025-00114 |
| service | The service investigated |
| completion date | When the RCA was finished |
| linked incidents | The incidents it covers |
| investigation owner | The team that wrote it |
| root cause category | Software defect, configuration error, capacity, certificate or credential expiry, infrastructure, vendor, process gap |
| business impact | Estimated cost in EUR |
| Summary | What happened |
| Timeline | The sequence of events |
| Root Cause | The confirmed cause |
| Five Whys | The chain of "why" questions from the symptom to the cause |
| Contributing Factors | What made it worse, grouped by the Fishbone categories |
| Corrective Actions | What was done afterwards |
| Preventive Actions | What stops it from happening again |

### CMDB configuration item

| Field | Meaning |
|---|---|
| ci_id | Identifier, for example CI-PAYMENT-API |
| name | Name of the component |
| type | Application, database, queue, gateway, host, cache, storage |
| service | The technical service it belongs to |
| environment | Production, test |
| owner_team | The team responsible |
| criticality | High, medium, low |

### CMDB relationship

| Field | Meaning |
|---|---|
| source_ci | The component that depends |
| target_ci | The component it depends on |
| relationship_type | Depends on, hosted on, connects to |

### Change record

| Field | Meaning |
|---|---|
| change_id | Identifier, for example CHG-2026-00871 |
| title, description | What was changed |
| type | Standard, normal, emergency |
| service, ci_id | What it touched |
| version | The deployed version |
| implemented_at | When it was executed |
| implemented_by | Team |
| risk | High, medium, low |
| rollback | Whether it was rolled back |

### Log entry

| Field | Meaning |
|---|---|
| log_id | Identifier, for example LOG-PAY-20260714-14 |
| timestamp | Exact time |
| service, host | Where it came from |
| level | ERROR, WARN, INFO |
| message | The log line |
| error_type | Normalised type, for example ConnectionTimeout |

### Application data

| Entity | What it holds |
|---|---|
| Problem event | Every change to a problem, kept forever: who, when, what, why |
| Proposal decision | A proposed problem the Problem Manager accepted or rejected, so it is not proposed again |
| RCA | One investigation of a problem: its status, number of revisions, number of expert decisions, whether it was sent to the expert |
| Revision | One run of the investigation: the context, the plan, the evidence, the timeline, the tool runs, the steps, the hypotheses with their confidence, what was not checked, the suggestions. Never changed once the run ended |
| Evidence record | One fact found during a run: id, type, source, description, citation, when it happened, when it was found, the tool run that found it |
| Status change | Every change of the status of an RCA, with who, when, the comment, and the decision of the expert |
| User | Username, password hash, role, active or not |

---

## 5.3 Mock data strategy

### How much

| Data | Records |
|---|---|
| Incidents | 500 (89 need an analysis) |
| Incident events | about 3300 |
| Past RCA documents | 21 |
| Problems at the start | 34 (13 open, one per story; 21 closed, one per past RCA) |
| CMDB items | 54 |
| CMDB relationships | 49 |
| Change records | about 550 |
| Log entries | about 8200 |

This is above the required minimum, and the numbers are chosen so the searches return
realistic results instead of always finding the same few records.

### How it is built

The data is generated by `scripts/build_mock_data.py`, always with the same result (fixed
random seed). It is built around **13 problem stories**, spread over January 2024 to
September 2026 and 10 services. A story is a real failure pattern, for example a connection
leak after a deployment, a certificate that expires, a disk that fills up during a
campaign, or DNS timeouts after a scale-down. Each story has its own random generator, so
changing one story never changes the others.

For each story we generate:

- the incidents of the open problem and older incidents of the same failure, with different wording,
- the changes that happened before some of them,
- the log lines from the incident windows,
- the CMDB components and dependencies involved,
- a past RCA document for some of the older incidents, but not for all of them.

Seven stories are meant to be solved. Six are edge cases on purpose: no useful history, a
misleading past RCA (same symptoms, different cause), an innocent change made just before
the incident, missing logs, or a cause outside the sources. They show the application
reporting weak support instead of inventing a cause.

Everything else is background: incidents from 52 families of ordinary failures (vendor
outages, WAF rules, feature flags, full queues), ordinary changes and their log lines. The
realistic proportions come from a real, anonymised ServiceNow event log of 24,918
incidents: how often a ticket moves between teams (half never does), how often it is
reopened (1%) and how long it stays resolved before it is closed (5 days). Only these
statistics are used, not the records.

After the files are built, `scripts/load_sources_sqlite.py --reset` reloads the sources
into SQLite and keeps the work done in the application; `--reset-app` also starts the
problems and the RCAs again, after a backup copy. `scripts/ingest_chroma.py --reset`
rebuilds the vector index.

### The rules that make the data realistic

- **The wording changes between incidents of the same story.** One says "database
  timeouts", another says "connection pool exhausted", another says "payments failing
  slowly". If they all used the same words, the search would look better than it is.
- **Not every story has a past RCA.** The application must also work when the history
  contains nothing useful, and must say so.
- **Some changes are innocent.** In several time windows there are two or three changes,
  and only one is related. Otherwise the correct answer would always be the last change.
- **Some incidents have no change at all.** Not every failure comes from a deployment.
- **Timestamps must agree.** A change that caused an incident happens before it is
  detected, the logs exist inside the incident window, and the past RCA is older than the
  incident being investigated.
- **The incident never contains the answer.** The input has symptoms and context only. If
  the incident text said "root cause: connection pool exhaustion", the application would
  only repeat what we gave it.
- **Three stories follow a clock.** One repeats every Monday morning during the payroll
  batch, one at the end of the month during the billing run, and one every night when the
  report batch starts. Without a time signature in the data there is no time pattern to
  find.

### Two scenarios chosen on purpose

Two kinds of stories are built for a specific reason, and both are used in the demo.

**A story with a clear time pattern.** The failures happen on the same weekday, in the
same hour, always during the same batch. A person needs to read a lot of tickets to see
that. The application groups them and states the pattern in one sentence. This is the
easiest thing to show and the hardest thing to do by hand.

**A story with no useful history.** No past RCA, no similar incident, and an innocent
change in the time window. The correct behaviour here is not to find a cause. It is to
report weak support, list what could not be checked, and suggest asking for more details
instead of approving. Almost no project shows its system correctly saying "I do not know".
For an application whose whole premise is that a human decides, that is the more
convincing of the two.

### The answer key

A separate file (`data/evaluation/answer_key.json`) holds the truth for each story: the real
root cause, the acceptable confidence, the red herrings, the expected citations, and the
correct 5 Whys chain, Fishbone factors and timeline, each step with the records that prove it.

This file is **never loaded into SQLite or ChromaDB and never shown to the agents**. It is
used only when measuring the results, to compare what the application proposed with what
was really true.

---

## 5.4 What needs search and what does not

Not everything needs a vector database. Using one where a normal query is enough only adds
uncertainty.

| Data | How it is accessed | Why |
|---|---|---|
| Past incidents | Search by meaning | The same failure is described in different words |
| Past RCA documents | Search by meaning, and by their linked incidents | Free text, written by different people |
| RCAs validated in the application | Direct query, same services, older problems only | Already structured: the validated cause and the decision |
| CMDB | Direct query | The service name is known, the answer is exact |
| Change records | Direct query by services and time window | A date range, not a question of meaning |
| Log entries | Direct query by service, time window and level, grouped by error type | Filtering, not interpretation |

So the RAG part covers the history, which is the part where the knowledge is hidden. The
technical evidence is fetched with plain queries, which are fast, cheap and always
correct.

---

## 5.5 ChromaDB design

### Two collections

| Collection | What it holds | One entry is |
|---|---|---|
| historical_incidents | All 500 incidents | One incident |
| historical_rcas | The 21 past RCA documents | One section of a document |

They are kept separate because they answer different questions. "Has this happened
before?" is answered by the incidents. "Do we already know the cause?" is answered by the
RCAs.

### What text is embedded

For an incident: the title, the description, the service, the business service and the
symptoms, joined into one short text.

For an RCA document: each section separately, because a document is too long for one
vector. Splitting by section keeps each piece about one subject. The search can find any
section, but the past RCA is judged and cited as a whole: the Historical Review Agent reads
its Summary, Root Cause and Corrective Actions.

### Metadata stored with every entry

For an incident: its id, service, business service, environment, severity and detection
date. For an RCA section: the document id, the section name, the service, the completion
date and the linked incidents.

The metadata is what allows filtering before the search, for example only records older
than the current incident. Filtering first and searching after gives better results than
searching everything and hoping the right record appears.

### Search settings

| Setting | Value | Why |
|---|---|---|
| Embedding model | nomic-embed-text, run locally in Ollama | Open source, free, fast enough on a CPU |
| Distance | Cosine | Standard for text similarity |
| Results kept | 5 similar incidents, and at most 5 past RCAs over all the search queries | Enough context without flooding the model |
| Maximum distance | 0.45; a result further away is dropped | A weak match is worse than no match |
| Mandatory filter | Only records older than the incident being investigated | Otherwise the system could learn the answer from the future |
| Same service | Past records of another service are dropped by code before the agent sees them | Similar words on another service are not evidence |

The threshold was measured with RAGAS on the 26 evaluation questions (`scripts/evaluate_ragas.py
calibrate`), from 0.25 to 0.45. At 0.45 the search finds 96% of the incidents and all the
past RCAs that should be found. The agent then removes the records that only share the
wording. The results are kept in `results/ragas/`.

A past RCA is also found by its **linked incidents**: when it links an incident of the
problem, or a similar incident, it is a candidate whatever its wording.

### The same vectors for the proposals

The incident vectors are also used to propose problems. Two incidents count as alike when
they are on the same service and their cosine similarity is at least 0.88, or at least 0.85
when they are on the same CMDB item. These values were measured on the mock data
(`data/evaluation/grouping_truth.json`): the first suggestion was right for 443 of the 445
incidents in no problem. The score ranks the proposals; it is not a probability that the
incidents share a cause.

---

## 5.6 Citations

Every result that comes back from a search or a tool becomes an evidence record before it
is used.

| Field | Example |
|---|---|
| evidence_id | EV-001 |
| type | INCIDENT, LOG, CHANGE, CMDB, HISTORICAL_RCA, HISTORICAL_INCIDENT |
| source | the hosts of a log, CHG-2026-00871 |
| description | Short summary of what was found, with its time compared with the detection |
| citation | The identifier of the original record |
| timestamp | When it happened, as the source says |
| related_ids | The other records it stands for, for example every line of a log group |

The ledger starts with the incident being investigated (type INCIDENT): its symptoms are
what the hypotheses must explain. The same original record is recorded only once, so it
cannot count twice in the confidence.

The reasoning agent can only cite evidence identifiers that exist in this list. A check in
plain code compares the citations against the ledger, and a hypothesis that cites
something which does not exist is refused.

This is what turns a citation from a promise into a rule. It also means that any sentence
in the RCA can be followed back to the exact incident, change, log line or past RCA that
produced it.

---

## 5.7 Evaluation data

Three sets are prepared together with the mock data, in `data/evaluation/`.

**For the retrieval quality.** 26 questions (`retrieval_questions.json`) of the type "which
past records are relevant for this incident", each with the records that should be found.
This is what RAGAS uses to measure whether the search brings the right context, and
whether the hypotheses stay faithful to the evidence they cite.

**For the end result.** The 13 stories of the answer key, used to check whether the
proposed candidate root cause matches the real one, and whether the confidence is the one
the story allows.

**For the grouping.** `grouping_truth.json` says which problem or failure family every
incident really belongs to, to score the proposals.

All sets stay outside SQLite, outside ChromaDB and outside everything the agents can read.
