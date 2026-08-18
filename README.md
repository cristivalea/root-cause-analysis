# AI-assisted Root Cause Analysis (RCA)

**Area:** Problem Management, large company
**Status:** documentation phase, implementation not started
**Last updated:** 2026-08-19

---

## What this project is

An application that helps a large company find out why an incident keeps coming back.

The Problem Manager starts an investigation. The application searches the past incidents
and past RCAs, checks the service dependencies, the recent changes and the logs, and
writes a draft with candidate root causes and the evidence behind each one. A Technical
Expert then approves it, rejects it, or asks for more evidence. Only after a human
approves does the RCA become final.

The AI does the searching and the correlation. The human decides the cause.

---

## Why it is needed

In ITIL, an incident is an interruption of a service and a problem is the cause behind one
or more incidents. Restoring the service is Incident Management. Finding out why it broke
is Problem Management, and that is where this application belongs.

Today that investigation takes one to four weeks in a large company. Most of that time is
not analysis. It is opening five or six different systems, searching each one separately,
copying the results into a document and reading until something looks connected. The
knowledge from past RCAs exists, but it is written in free text and is almost never found
again.

The application removes the searching, not the judgement. The expert starts from a
prepared case instead of an empty page.

---

## What it produces

One final RCA record: the status, the validated root cause, the evidence behind it, the
technical validation, the owner, and the dates. Every statement in it points back to the
exact incident, change, log line or RCA section it came from.

The record also suggests a possible workaround and says whether a change is likely to be
needed. Those are recommendations. The application never creates a Known Error and never
opens a Change Request, and it never takes any action on a real system.

---

## Three rules the design is built on

1. **The model proposes, the code executes.** Three LLM agents reason. Everything that
   fetches data, validates output, calculates confidence or writes a record is ordinary
   Python that can be tested without a model.
2. **Nothing is cited that was not found.** Every fact collected becomes a numbered
   evidence record first. A hypothesis that cites an identifier which is not in that list
   is refused in code, not asked to behave better.
3. **No RCA becomes final without a human.** The field holding the root cause stays empty
   until a Technical Expert approves. There is no confidence level, however high, that
   lets the application decide by itself.

---

## The documentation

The documents live in [`docs/`](docs/). Read them in order — each one builds on the one
before it.

| File | What it answers |
|---|---|
| [01-problem-definition.md](docs/01-problem-definition.md) | What problem we solve, what the objective is, what is in and out of scope |
| [02-current-process.md](docs/02-current-process.md) | How an RCA is done today without AI, where it loses time, what AI can improve |
| [03-proposed-solution.md](docs/03-proposed-solution.md) | What the new flow looks like, who does what, the states of an RCA, what goes in and what comes out |
| [04-architecture.md](docs/04-architecture.md) | The components, the diagrams, the data workflow, the handoffs, the deployment |
| [05-data-and-rag.md](docs/05-data-and-rag.md) | What data is needed, the entities, the mock data strategy, how ChromaDB is used |
| [06-reasoning-and-execution.md](docs/06-reasoning-and-execution.md) | What reasons and what executes, the validation, the guardrails, the human approval |
| [07-kpis.md](docs/07-kpis.md) | What we measure, how we compare with the manual process, when the project is successful |

There is one more file, which is not part of the documentation itself:

| File | What it is |
|---|---|
| [PROJECT_CONTEXT.md](docs/PROJECT_CONTEXT.md) | The working reference: all requirements, notes, decisions and open points. If anything disagrees with it, this file wins |

### Where to start

| If you want to | Read |
|---|---|
| Understand the project in five minutes | 01, then 03 |
| Understand how it is built | 04, then 06 |
| Work on the mock data | 05 |
| Understand what we promise to prove | 02, then 07 |

---

## How it is built

A summary. The detail, and the reason behind each choice, is in
[04-architecture.md](docs/04-architecture.md).

| Area | Choice |
|---|---|
| Reasoning model | Open-source model on the Groq free tier |
| Embeddings | `nomic-embed-text`, run locally in Ollama |
| Retrieval | ChromaDB, two collections: past incidents and past RCA sections |
| Orchestration | LangGraph, as a state machine that routes but does not reason |
| Backend | FastAPI |
| Interface | Streamlit, one view per role |
| Output validation | Pydantic, plus citation and content checks in plain Python |
| Evaluation | RAGAS, against an answer key that the agents never see |
| Observability and audit | Arize Phoenix with OpenTelemetry, plus an audit trail in the database |
| Storage | SQLite for records, files for the mock sources |
| Packaging | Docker Compose, three containers, started with one command |

Everything runs at zero licensing cost. All source systems are mock data, built to look
realistic.

---

## Scope

This project builds the **RCA** part of Problem Management, and only that.

It does not build a full Problem Management system, does not manage incidents or changes,
does not create Known Error records, and does not integrate with a real ITSM tool. Other
components, such as a Known Error DB Curator, are built separately by other members of the
team.

---

## How these documents are written

- In English, in simple and direct language.
- One subject per file, so a change stays in one place.
- Each thing is said once. If it belongs somewhere else, it is not repeated here.
- Diagrams are written in Mermaid, so they render directly in the repository.
- Every document has the same header, with the date it was last changed.

When the application changes, the document changes with it. A document that no longer
matches the code is worse than no document.
