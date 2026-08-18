# Project Context — Root Cause Analysis (RCA) Application

**Status:** living document · **Last updated:** 2026-08-19 · **Language:** English

---

## 0. How to use this file

This file is the single source of truth for the project. It holds every requirement,
note and decision we have.

Rules:

- If this file and anything else disagree (README, old code, memory), **this file wins**.
- `README.md` in the repo root is a colleague's early draft. **Do not use it** as
  requirements or design.
- Update this file whenever a decision changes.

---

## 1. What we are building

An **AI-assisted Root Cause Analysis application** for the Problem Management area of a
large company.

The application takes a recurring incident, lets AI agents automatically search and
correlate evidence from several sources (past RCAs, CMDB, changes, logs), and produces a
**candidate root cause with evidence and citations**. A human Technical Expert then
validates or rejects it. Only after human approval does the RCA become final.

One sentence for the story:

> We are not replacing the expert who does the RCA. We are removing the manual work of
> searching, aggregating and correlating information, so the expert can focus on
> validating the case.

---

## 2. Scope

### In scope

- Root Cause Analysis only, inside Problem Management.
- One RCA investigation at a time, started from an incident that needs an RCA.
- AI investigation, hypotheses with evidence, human validation, final RCA record.
- Mock data for all source systems.

### Out of scope

- A complete Problem Management system (colleagues build other parts, for example a
  Known Error DB Curator).
- Incident Management, Change Management, Known Error records, Change Requests.
- Real integrations with real ITSM tools. Everything is mocked.
- Automatic remediation or any action on production systems.

### Assumptions

- Incidents, CMDB, changes and logs already exist as mock data.
- The company already has a history of past RCAs, used for retrieval.
- The AI never decides the root cause by itself.

---

## 3. Users and roles

| Role | Who | What they do in the app |
|---|---|---|
| **Problem Manager** | Primary user | Sees the incidents that need an RCA, starts an RCA, follows the investigation, sends the draft to the expert, accepts the final RCA or sends it back for clarification. |
| **Technical Expert** | Reviewer / validator | Reads the AI investigation and the hypotheses, then approves, rejects, or requests more evidence. Adds technical knowledge. |
| Incident Manager | Not a user | Incidents arrive as mock data. No screen for this role. |

Both roles can open the final RCA page. The RCA is the result of their collaboration:
the AI investigates and proposes, the Technical Expert validates the technical part, the
Problem Manager owns the process and the final result.

---

## 4. Mandatory requirements (from the academy)

| # | Requirement |
|---|---|
| 1 | **Documented architecture**: agent roles, tools, handoffs, states, diagram. |
| 2 | **Separation of reasoning and execution**: the LLM proposes (JSON validated with Pydantic), execution goes through deterministic tools with validations. |
| 3 | **Open source model** through Ollama or Groq free tier — zero cost. |
| 4 | **RAG with ChromaDB** on mock data, with citations. Where there is RAG, evaluate with RAGAS. |
| 5 | **Human-in-the-loop through guardrails**: at least one human approval point for risky actions, with justified thresholds. |
| 6 | **Audit and observability with Arize Phoenix**: what the agent decided, on what basis, who approved, what was executed. |
| 7 | **Realistic mock data**: minimum 200–500 records relevant to the topic. |
| 8 | **Minimum 1–2 measured KPIs**: simulated MTTR, self-resolution rate, % human intervention, classification accuracy, fulfillment time. Basic manual vs agentic comparison. |
| 9 | **Product delivery**: FastAPI API in Docker + Streamlit interface, end-to-end demo. |

---

## 5. Notes taken during the explanations

These are the spoken explanations behind the requirements. They are as important as the
requirements themselves.

1. **Mock data must look real.** We simulate data close to reality so we can show the
   application works in realistic scenarios. The data, the accounts and the documents we
   give to the RAG all matter.
2. **Everything must be very well documented.** We need a data workflow (how data flows
   and where it goes) and a diagram for the user flow.
3. **Programming is not the most important part.** Optimisation, system design and
   scalability matter more: how we design the application, how we connect everything. AI
   can help, but we must define the whole context, explain the application, name the
   pattern we use, and state our hardware (OS, GPU, CPU). Architecture and documentation
   are very important.
4. **The code must be modular**, not a mess. Use coding principles such as single
   responsibility: each component does one thing.
5. **Open source models** through Ollama or Groq. If we want something better, a free
   trial is acceptable, then cancel the subscription.
6. **At least 1–2 KPIs** that measure the performance of the application / agent system.
   They want to see what advantage AI brings.
7. **How the product is delivered to the client matters.** It shows we are not only
   developers who write code: we understand business logic, the application and its
   functionality, and we can discuss the project.
8. **Business KPIs are advisable** (what we reduced, what we improved, how we prove it,
   how we improved the department), plus more KPIs on the AI side (accuracy, generation
   quality). The more we can show, the better.

---

## 6. Key project decisions already taken

1. We build an **RCA application**, not a full Problem Management system.
2. The application improves the current RCA process in a large company using AI agents,
   RAG and tools, to reduce manual work, investigation time and expert effort — **without
   the AI deciding the root cause itself**.
3. The documentation must explain the **current RCA process without AI**, where it has
   problems, and how AI improves it. Today this process is manual and can take weeks.
4. Primary user is the **Problem Manager**; reviewer is the **Technical Expert**.
5. The **Incident Manager is not a user**; incidents, CMDB and logs are mocked.
6. The AI does the research and correlation that used to be manual; the human approves.
7. The output is a **structured final RCA backed by evidence**. It may recommend a
   workaround and say that a change is likely needed, but it never creates a Known Error
   and never opens a Change Request.
8. The AI output must always say **"Candidate Root Cause / Hypothesis"**, never "Root
   Cause". `final_root_cause` stays `null` until the Technical Expert validates.

---

## 7. Reference flow (user flow)

```
Problem Manager
      │
      │ Start RCA
      ▼
AI Investigation
      │
      ▼
  Draft RCA
      │
      ▼
Technical Expert
      ├── Confirm
      ├── Reject
      └── Request additional evidence
      │
      ▼
 Updated RCA
      │
      ▼
Problem Manager
      ├── Accept
      └── Send back for clarification
      │
      ▼
  FINAL RCA
      │
      ├──────────────┐
      ▼              ▼
Problem Manager   Technical Expert
     VIEW              VIEW
```

After completion there is **one official version** of the RCA that both roles can open.
That page shows: status, root cause, evidence, technical validation, RCA owner, creation
date and completion date.

---

## 8. Agent architecture (reference proposal)

Simple version — orchestrator plus specialised investigators:

```
                     ┌──────────────────┐
                     │  Problem Manager │
                     └────────┬─────────┘
                              │ Start RCA
                              ▼
                  ┌─────────────────────┐
                  │   RCA ORCHESTRATOR  │
                  └──────────┬──────────┘
             ┌───────────────┼────────────────┐
             ▼               ▼                ▼
       Historical        Technical        Change / CMDB
       RCA Agent          Evidence            Agent
             └───────────────┼────────────────┘
                             ▼
                       Log Analysis Agent
                             ▼
                    Correlation / RCA Reasoning
                             ▼
                         Hypotheses
                             ▼
                       Candidate RCA
                             ▼
                   ┌─────────────────┐
                   │ Technical Expert│
                   └────────┬────────┘
                            │ Validate / Reject / Request evidence
                            ▼
                        FINAL RCA
```

Full version, including the mandatory requirements:

```
                         ┌───────────────────┐
                         │  Problem Manager  │
                         └─────────┬─────────┘
                                   │ Start RCA
                                   ▼
                         ┌───────────────────┐
                         │   FastAPI / API   │
                         └─────────┬─────────┘
                                   ▼
                         ┌───────────────────┐
                         │  RCA Orchestrator │
                         └─────────┬─────────┘
                 ┌─────────────────┼──────────────────┐
                 ▼                 ▼                  ▼
        Historical RCA      CMDB Investigation   Change Investigation
             Agent                Agent                Agent
                 └────────────┬────┴───────┬──────────┘
                              ▼            ▼
                        Log Analysis   RAG / ChromaDB
                              │            │
                              ▼            │
                      Evidence Context     │
                              ▼            │
                      ┌───────────────┐    │
                      │ RCA Reasoning │◄───┘
                      │     Agent     │
                      └───────┬───────┘
                              │ Pydantic output
                              │ Guardrails
                              ▼
                        Candidate RCA
                              ▼
                   ┌────────────────────┐
                   │  Technical Expert  │
                   └─────────┬──────────┘
           ┌─────────────────┼─────────────────┐
           ▼                 ▼                 ▼
        APPROVE           REJECT         MORE EVIDENCE
           │                 │                 │
           │                 │                 └──► back to Orchestrator
           ▼                 ▼
     Validated RCA      New investigation
           ▼
      FINAL RCA
           │
     ┌─────┴──────┐
     ▼            ▼
Problem Manager  Technical Expert

┌────────────────────────────────────────────┐
│              Arize Phoenix                 │
│ traces / decisions / retrieval / tools /   │
│ approvals / execution / latency            │
└────────────────────────────────────────────┘
```

### What each agent does

| Agent | Question it answers | Output |
|---|---|---|
| **RCA Orchestrator** | "We received INC-1234. Investigate the cause." Coordinates the investigation. | Investigation plan and control of the flow |
| **Historical RCA Agent** | Have there been similar incidents? Were the same services affected? Were there similar root causes? Are there relevant past RCAs? | Similar incidents and past RCAs, with citations (RAG / ChromaDB) |
| **CMDB Agent** | What components are related to the affected service? | Dependencies of the affected service |
| **Change Agent** | What changes or deployments happened before the incident? | Recent changes in the time window |
| **Log Analysis Agent** | What do the logs show around the incident window? | Relevant log lines and patterns |
| **Correlation / RCA Reasoning** | What explains all the evidence together? | Ranked hypotheses with confidence and evidence |

The reasoning step must not only list what it found. It must produce: **observed
pattern, historical correlation, log evidence, hypothesis, confidence, evidence**. It
must never state a final root cause — only a candidate. This is what keeps the human in
the loop.

### Confirmed structure (decided 2026-08-18)

The diagrams above stay as the reference picture of the flow. The decided internal
structure is this:

**Three LLM agents only.** Everything else is a deterministic tool.

| Part | Type | What it does |
|---|---|---|
| Investigation Planner | LLM agent | Reads the incident and decides what to look for: which service, which time window, which sources. |
| Historical RCA Agent | LLM agent + RAG | Writes the search queries, retrieves past incidents and RCAs from ChromaDB, judges whether they are really similar. |
| RCA Reasoning Agent | LLM agent | The only place where hypotheses are formed. Correlates all the evidence. |
| CMDB lookup | Deterministic tool | Returns the dependencies of a service. |
| Change lookup | Deterministic tool | Returns the changes in a time window. |
| Log lookup | Deterministic tool | Returns the log lines in a time window, filtered by service and level. |
| Orchestrator | Deterministic state machine | Controls the flow only. It does not reason. |

**Other decided rules:**

1. **Evidence Ledger.** Every fact returned by any tool becomes a record with
   `evidence_id`, type, source, timestamp and content. Hypotheses may only cite
   `evidence_id` values that exist in the ledger. A plain Python check rejects a
   hypothesis that cites an unknown ID.
2. **Confidence is calculated, not written by the LLM.** The LLM writes the reasons. Our
   own rules compute HIGH / MEDIUM / LOW from countable facts: how many evidence types
   support the hypothesis, how close in time the change was, how similar the historical
   RCA was. This gives the justified thresholds that requirement 5 asks for.
3. **At least two hypotheses**, or an explicit reason why only one exists. This avoids
   stopping at the first plausible cause.
4. **The output must list what could not be checked** — missing metrics, short log
   window, no data from other environments.
5. **The "request more evidence" loop is limited to 2 rounds.** After that the case is
   escalated.
6. **The investigation starts by building an incident cluster** — the current incident
   plus the past incidents that look like it. That cluster is the problem being
   analysed, which is what Problem Management actually means.

---

## 9. Tools and handoffs

### Tool groups

Incident tools · Historical RCA / RAG tools · CMDB tools · Change tools · Log tools ·
Evidence tools · RCA tools · Review tools · Finalisation tools · Audit tools

### Handoffs, orchestrator to agents

| # | Handoff | Instruction |
|---|---|---|
| 1 | Orchestrator → Historical RCA Agent | "Investigate historical similarity." |
| 2 | Orchestrator → CMDB Agent | "Investigate affected service dependencies." |
| 3 | Orchestrator → Change Agent | "Investigate recent changes / deployments." |
| 4 | Orchestrator → Log Agent | "Investigate log patterns around the incident window." |

### Handoff to the human

```
RCA Reasoning → RCA candidates → Guardrail → submit_for_review → Technical Expert
```

### The three human decisions

```
APPROVE:
Technical Expert → APPROVED → Technically Validated RCA

REJECT:
Technical Expert → REJECTED → New investigation / alternative hypothesis

REQUEST EVIDENCE:
Technical Expert → MORE_EVIDENCE_REQUIRED → Orchestrator → Targeted investigation
                 → Updated Candidate RCA → Technical Expert
```

### Targeted investigation

The orchestrator must be able to run a narrow, second investigation:

```
Expert request → (e.g.) Change Agent → new evidence → RCA Reasoning → updated hypothesis
```

---

## 10. Example input

A recurring incident on a payment service. Important: the input contains **symptoms and
context, not the answer**. It must not contain "Root Cause = database connection pool
exhaustion", otherwise the application only confirms what we gave it.

```json
{
  "incident_id": "INC-2026-00482",
  "title": "Payment API intermittent failures",
  "description": "Customers experienced intermittent failures when attempting to complete card payments.",
  "severity": "SEV-1",
  "status": "Resolved",
  "service": "Payment API",
  "business_service": "Online Payments",
  "environment": "production",
  "detected_at": "2026-07-14T14:32:00Z",
  "resolved_at": "2026-07-14T15:17:00Z",
  "duration_minutes": 45,
  "affected_regions": ["EU", "UK"],
  "impact": {
    "failed_transactions": 18420,
    "estimated_customers_affected": 12750,
    "error_rate_peak": "18.7%"
  },
  "symptoms": [
    "HTTP 500 responses from Payment API",
    "increased database connection timeout errors",
    "latency above 5 seconds"
  ],
  "initial_mitigation": "Payment API pods were restarted and traffic was partially redirected to secondary instances.",
  "reported_by": "Incident Management",
  "rca_required": true,
  "rca_reason": "Recurring incident affecting a critical business service"
}
```

---

## 11. Example output of the AI investigation

```json
{
  "rca_id": "RCA-2026-00137",
  "incident_id": "INC-2026-00482",
  "status": "PENDING_TECHNICAL_REVIEW",

  "investigation_summary": "The investigation identified a strong correlation between the deployment of Payment API v4.18.2 and a subsequent increase in database connection acquisition timeouts.",

  "observed_patterns": [
    "Database connection timeout errors increased immediately before the incident.",
    "Payment API latency increased significantly.",
    "HTTP 500 responses increased during the same time window.",
    "A production deployment occurred 34 minutes before incident detection."
  ],

  "hypotheses": [
    {
      "hypothesis_id": "HYP-001",
      "candidate_root_cause": "Database connection pool exhaustion or abnormal connection consumption introduced or amplified by Payment API v4.18.2.",
      "confidence": "HIGH",
      "confidence_reason": [
        "Strong temporal correlation with deployment CHG-2026-00871.",
        "Log evidence shows repeated database connection acquisition timeouts.",
        "Two historical RCAs describe similar failure patterns.",
        "Payment API has a direct dependency on the affected database."
      ],
      "supporting_evidence": [
        {
          "evidence_id": "EV-001",
          "type": "LOG",
          "source": "payment-api-prod",
          "description": "Repeated HikariPool connection acquisition timeouts.",
          "citation": "LOG-2026-00482-14"
        },
        {
          "evidence_id": "EV-002",
          "type": "CHANGE",
          "source": "CHG-2026-00871",
          "description": "Payment API v4.18.2 deployed 34 minutes before incident.",
          "citation": "CHG-2026-00871"
        },
        {
          "evidence_id": "EV-003",
          "type": "HISTORICAL_RCA",
          "source": "RCA-2025-00114",
          "description": "Similar Payment API failure caused by database connection pool exhaustion.",
          "citation": "RCA-2025-00114"
        },
        {
          "evidence_id": "EV-004",
          "type": "CMDB",
          "source": "CMDB",
          "description": "Payment API has a direct dependency on payment-db-prod-01.",
          "citation": "CMDB-PAYMENT-API"
        }
      ],
      "contradicting_evidence": [],
      "recommended_validation": [
        "Compare database connection usage before and after deployment v4.18.2.",
        "Review connection pool configuration changes introduced by v4.18.2.",
        "Verify whether database-side connection limits were reached."
      ]
    }
  ],

  "evidence_coverage": {
    "historical_rca": true,
    "cmdb": true,
    "changes": true,
    "logs": true
  },

  "ai_conclusion": "Candidate Root Cause identified. Technical validation is required.",
  "suggested_workaround": "Temporarily raise the connection pool limit.",
  "change_likely_required": true,
  "final_root_cause": null,

  "technical_validation": {
    "status": "PENDING",
    "reviewer": null,
    "decision": null
  }
}
```

Two rules this example demonstrates:

- The output says **Candidate Root Cause**, never Root Cause.
- `final_root_cause` stays `null` until the Technical Expert validates.

---

## 12. Technology stack

| Area | Choice |
|---|---|
| LLM | **Groq free tier** with an open-source model (main choice). Ollama with a small local model as offline fallback. |
| Embeddings | Open-source local embedding model through Ollama (`nomic-embed-text`) |
| RAG | ChromaDB |
| Backend | FastAPI |
| UI | Streamlit |
| Validation | Pydantic |
| Agent orchestration | LangGraph or custom orchestrator |
| Evaluation | RAGAS |
| Observability | Arize Phoenix + OpenTelemetry |
| Packaging | Docker |
| Mock incident / RCA store | SQLite (or JSON / CSV for simple sources) |
| Mock logs | Structured log store |
| Mock CMDB | Relational store |
| Mock changes | Relational store |

---

## 13. KPIs

Two levels.

**Business KPIs**

- Simulated investigation time
- MTTR / time-to-RCA
- Expert effort
- Percentage of manual investigation steps removed

**AI KPIs**

- Historical RCA retrieval precision
- RAG faithfulness
- Evidence coverage
- Hypothesis accuracy
- Technical Expert acceptance rate
- False hypothesis rate
- Tool-call accuracy

RAGAS already has metric families for both RAG and agent / tool use, which fits this
project well.

---

## 14. Development environment (measured on this machine)

| Item | Value |
|---|---|
| OS | Windows 11 Pro, 10.0.26100 |
| CPU | Intel Core Ultra 7 268V — 8 cores, 8 threads |
| RAM | 32 GB (shared with the GPU) |
| GPU | Intel Arc 140V, integrated — **no NVIDIA, no CUDA** |
| Free disk | ~670 GB |
| Ollama | installed, version 0.32.13 |
| Python | 3.14.7 installed |
| Docker | **not installed yet** (needed for requirement 9) |

What this means in practice:

- There is no CUDA GPU. Local models run mostly on CPU, so a large local model is not
  realistic. A small local model (7–8B) is fine; a 70B local model is not.
- A local embedding model is cheap and fast enough on CPU, so RAG can stay fully local.
- Groq free tier gives access to much larger models at zero cost and is the better place
  for the reasoning step.
- Docker Desktop must be installed before the delivery step.
- Python 3.14 is very new and several libraries in the stack may not have ready packages
  for it. A 3.11 or 3.12 virtual environment is the safer choice.

---

## 15. Documentation rules

- Written in **English**, so it is universally valid.
- Placed in the `docs/` folder, split into several `.md` files.
- **Clarity**: simple, direct language. No unnecessarily complicated terms.
- **Kept up to date**: change the document whenever the code or the features change.
- **Accessible**: easy to find for the whole team.
- **Modular**: information split into small, clear topics.
- **Useful**: write only what is needed. No extra details that confuse the reader.
- Follow the agreed section list for each document exactly. No extra sections, no ID or
  tagging systems, no cross-reference machinery. Say each thing once.

### Required content of the documentation

| # | Section | What it must contain |
|---|---|---|
| 1 | Problem definition & scope | Clear business / IT problem, objective, scope, assumptions, exclusions. |
| 2 | Understanding of the process | Traditional method, bottlenecks, what can be improved with AI. |
| 3 | Proposed solution / TO-BE flow | What the system that improves the problem looks like. |
| 4 | High-level architecture | Technical diagrams and workflow. Components and relationships: input, model / LLM, data, retrieval, backend, UI, external systems, output. |
| 5 | Data design & RAG thinking | What data is required, entities / schema, mock data strategy, what needs retrieval, ChromaDB usage. |
| 6 | Reasoning / decision / execution concept | Identification of agents (not very detailed — the next module covers it). |
| 7 | KPIs & success criteria | 1–2 sensible measures showing the project works better than the current process. Only the method of verification, no estimates or demo yet. |

---

## 16. Design decisions

Decided on 2026-08-18:

1. **LLM agents vs tools** — three LLM agents (Investigation Planner, Historical RCA
   Agent, RCA Reasoning Agent). CMDB, changes and logs are deterministic tools. See
   section 8.
2. **Confidence** — calculated by our own rules, not written by the LLM.
3. **Main model** — Groq free tier. Ollama stays as a local fallback and runs the
   embedding model. This can change later.
4. **Evidence rounds** — the "request more evidence" loop is limited to 2 rounds, then
   the case is escalated.
5. **Answer key for KPIs** — the mock data must include a separate file with the true
   root cause of each scenario. It is never indexed in ChromaDB and never shown to the
   agents. Without it, hypothesis accuracy cannot be measured.

6. **Orchestrator** — LangGraph, decided while writing document 04. Reason: the flow must
   pause for a human and resume later, and LangGraph gives the pause, the saved state and
   the resume for free.

Decided on 2026-08-19, after comparing the two documentation drafts:

7. **The output object is an RCA record**, not a Problem Record. The RCA feeds the
   Problem Record that the next process owns.
8. **Everything merged from the colleague's README is translated to English.** The
   documentation stays in one language.
9. **Recurrence pattern detection is a named capability**, including time patterns such as
   "every Monday during the payroll batch". The mock data must contain at least two
   stories with a time signature, otherwise there is nothing to detect.
10. **The RCA carries two forward-looking fields**: `suggested_workaround` and
    `change_likely_required`. Recommendations only. Confirm the boundary with the
    colleague who builds the Known Error DB Curator; if their component covers this, the
    two fields are removed and our output becomes their input instead.
11. **The investigation scope can be set by hand.** The Investigation Planner decides the
    service and the time window by default; the Problem Manager can override both before
    starting.
12. **One demo scenario has no useful history**, so the application can be shown
    correctly reporting weak support instead of inventing a cause.

Still open:

- Which exact Groq model to use.
- Python version for the project environment (3.11 or 3.12, not 3.14).
- Whether the Known Error DB Curator teammate covers the workaround and change
  recommendation (decision 10).
