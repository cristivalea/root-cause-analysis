# 5. Data Design and RAG

**Project:** AI-assisted Root Cause Analysis (RCA) application
**Area:** Problem Management, large company
**Last updated:** 2026-08-18

---

## 5.1 What data the application needs

The investigation answers four questions, and each one needs its own source.

| Question | Source | Type |
|---|---|---|
| Did something similar happen before? | Past incidents and past RCA documents | Text, searched by meaning |
| What does this service depend on? | CMDB | Structured, direct lookup |
| What changed before the incident? | Change records | Structured, direct lookup |
| What do the logs show? | Log store | Structured, direct lookup |

The application also produces its own data: the RCA records, the evidence, and the audit
trail.

All source data is mock data, built to look realistic.

---

## 5.2 Entities

### Incident

The incident that starts the investigation, and the past incidents used for comparison.

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
| rca_required | Whether an RCA is needed |

### Past RCA document

The knowledge the company already has.

| Field | Meaning |
|---|---|
| rca_id | Identifier, for example RCA-2025-00114 |
| incident_ids | The incidents it covers |
| title | Short description |
| service | The service investigated |
| summary | What happened |
| timeline | The sequence of events |
| root_cause | The confirmed cause |
| contributing_factors | What made it worse |
| corrective_actions | What was done afterwards |
| created_at | Date |

### CMDB configuration item

| Field | Meaning |
|---|---|
| ci_id | Identifier, for example CI-PAYMENT-API |
| name | Name of the component |
| type | Application, database, queue, gateway, host |
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
| title | What was changed |
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
| log_id | Identifier |
| timestamp | Exact time |
| service, host | Where it came from |
| level | ERROR, WARN, INFO |
| message | The log line |
| error_type | Normalised type, for example ConnectionTimeout |

### Application data

| Entity | What it holds |
|---|---|
| RCA record | The investigation and its result: status, hypotheses, final root cause, owner, dates |
| Evidence record | One fact found during the investigation: id, type, source, timestamp, content, citation |
| Decision record | Every human decision: who, when, what they chose, the comment |
| Audit entry | Every step the application executed, with its input and its result |

---

## 5.3 Mock data strategy

### How much

| Data | Records |
|---|---|
| Incidents | 300 |
| Past RCA documents | 60 |
| CMDB items | 80 |
| CMDB relationships | 150 |
| Change records | 200 |
| Log entries | around 5000 |

This is above the required minimum, and the numbers are chosen so the searches return
realistic results instead of always finding the same few records.

### How it is built

The data is generated around **10 recurring problem stories**, spread over 18 months and
8 business services. A story is a real failure pattern, for example a connection pool that
runs out after a deployment, a certificate that expires, a queue that fills up during peak
hours, or a slow query after an index was dropped.

For each story we generate:

- between 4 and 12 incidents, at different dates, with different wording,
- the changes that happened before some of them,
- the log lines from the incident windows,
- the CMDB components and dependencies involved,
- a past RCA document for some of the older incidents, but not for all of them.

Everything else is background noise: unrelated incidents, ordinary changes, normal log
lines.

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

### The answer key

A separate file holds the truth for each story: the real root cause and the evidence that
should be found for it.

This file is **never loaded into ChromaDB and never shown to the agents**. It is used only
when measuring the results, to compare what the application proposed with what was really
true. Without it we cannot measure accuracy at all, so it is built together with the mock
data, not later.

---

## 5.4 What needs search and what does not

Not everything needs a vector database. Using one where a normal query is enough only adds
uncertainty.

| Data | How it is accessed | Why |
|---|---|---|
| Past incidents | Search by meaning | The same failure is described in different words |
| Past RCA documents | Search by meaning | Free text, written by different people |
| CMDB | Direct query | The service name is known, the answer is exact |
| Change records | Direct query by service and time window | A date range, not a question of meaning |
| Log entries | Direct query by service, time window and level | Filtering, not interpretation |

So the RAG part covers the history, which is the part where the knowledge is hidden. The
technical evidence is fetched with plain queries, which are fast, cheap and always
correct.

---

## 5.5 ChromaDB design

### Two collections

| Collection | What it holds | One entry is |
|---|---|---|
| historical_incidents | The 300 incidents | One incident |
| historical_rcas | The 60 past RCA documents | One section of a document |

They are kept separate because they answer different questions. "Has this happened
before?" is answered by the incidents. "Do we already know the cause?" is answered by the
RCAs.

### What text is embedded

For an incident: the title, the description and the symptoms, joined into one short text.

For an RCA document: each section separately, because a document is too long for one
vector. The sections are the summary, the timeline, the root cause and the corrective
actions. Splitting by section keeps each piece about one subject and makes the citation
precise, since we can point to the exact section.

### Metadata stored with every entry

Service, business service, environment, severity, date, and the identifier of the original
record. For RCA sections we also store the section name.

The metadata is what allows filtering before the search, for example only incidents from
production, or only records older than the current incident. Filtering first and searching
after gives better results than searching everything and hoping the right record appears.

### Search settings

| Setting | Value | Why |
|---|---|---|
| Embedding model | nomic-embed-text, run locally in Ollama | Open source, free, fast enough on a CPU |
| Distance | Cosine | Standard for text similarity |
| Results returned | 5 per collection | Enough context without flooding the model |
| Minimum similarity | A threshold below which a result is dropped | A weak match is worse than no match |
| Mandatory filter | Only records older than the incident being investigated | Otherwise the system could learn the answer from the future |

The exact threshold is decided by testing it against the answer key, not by guessing. It
is written down together with the reason, because a number without a justification cannot
be defended.

---

## 5.6 Citations

Every result that comes back from a search or a tool becomes an evidence record before it
is used.

| Field | Example |
|---|---|
| evidence_id | EV-001 |
| type | LOG, CHANGE, CMDB, HISTORICAL_RCA, HISTORICAL_INCIDENT |
| source | payment-api-prod, CHG-2026-00871 |
| description | Short summary of what was found |
| citation | The identifier of the original record |

The reasoning agent can only cite evidence identifiers that exist in this list. A check in
plain code compares the citations against the ledger, and a hypothesis that cites
something which does not exist is refused.

This is what turns a citation from a promise into a rule. It also means that any sentence
in the final RCA can be followed back to the exact incident, change, log line or RCA
section that produced it.

---

## 5.7 Evaluation data

Two small sets are prepared together with the mock data.

**For the retrieval quality.** Around 30 questions of the type "which past records are
relevant for this incident", each with the records that should be found. This is what
RAGAS uses to measure whether the search brings the right context and whether the answer
stays faithful to it.

**For the end result.** The 10 stories from the answer key, used to check whether the
proposed candidate root cause matches the real one.

Both sets stay outside ChromaDB and outside everything the agents can read.
