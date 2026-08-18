# Documentation

**Project:** AI-assisted Root Cause Analysis (RCA) application
**Area:** Problem Management, large company
**Last updated:** 2026-08-18

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

## The documents

Read them in order. Each one builds on the one before it.

| File | What it answers |
|---|---|
| [01-problem-definition.md](01-problem-definition.md) | What problem we solve, what the objective is, what is in and out of scope |
| [02-current-process.md](02-current-process.md) | How an RCA is done today without AI, where it loses time, what AI can improve |
| [03-proposed-solution.md](03-proposed-solution.md) | What the new flow looks like, who does what, the states of an RCA |
| [04-architecture.md](04-architecture.md) | The components, the diagrams, the data workflow, the handoffs, the deployment |
| [05-data-and-rag.md](05-data-and-rag.md) | What data is needed, the entities, the mock data strategy, how ChromaDB is used |
| [06-reasoning-and-execution.md](06-reasoning-and-execution.md) | What reasons and what executes, the validation, the guardrails, the human approval |
| [07-kpis.md](07-kpis.md) | What we measure, how we compare with the manual process, when the project is successful |

There is one more file, which is not part of the documentation itself:

| File | What it is |
|---|---|
| [PROJECT_CONTEXT.md](PROJECT_CONTEXT.md) | The working reference: all requirements, notes, decisions and open points. It wins over everything else if they disagree |

---

## Where to start

| If you want to | Read |
|---|---|
| Understand the project in five minutes | 01, then 03 |
| Understand how it is built | 04, then 06 |
| Work on the mock data | 05 |
| Understand what we promise to prove | 02, then 07 |

---

## How these documents are written

- In English, in simple and direct language.
- One subject per file, so a change stays in one place.
- Each thing is said once. If it belongs somewhere else, it is not repeated here.
- Diagrams are written in Mermaid, so they render directly in the repository.
- Every document has the same header, with the date it was last changed.

When the application changes, the document changes with it. A document that no longer
matches the code is worse than no document.
