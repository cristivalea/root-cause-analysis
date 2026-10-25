# 1. Problem Definition and Scope

**Project:** AI-assisted Root Cause Analysis (RCA) application
**Area:** Problem Management, large company
**Last updated:** 2026-10-22

---

## 1.1 The problem

In ITIL, an **incident** is an interruption of a service, and a **problem** is the cause
behind one or more incidents. Incident Management restores the service as fast as
possible. Problem Management asks why it broke and makes sure it does not break again.
These are two different jobs, and this application belongs to the second one.

A large company runs hundreds of IT services. Some incidents keep coming back. When that
happens, Problem Management must find out **why** it happens, not only restore the
service. This investigation is called Root Cause Analysis.

Today this work is manual. To investigate one recurring problem, a person has to:

- read the incidents and decide which ones belong to the same problem,
- search past RCA documents to see if the same thing happened before,
- open the CMDB to understand what the affected service depends on,
- check which changes and deployments happened before the incidents,
- read logs from the incident time windows,
- put all of this together and write a conclusion.

Each of these lives in a different system, with a different search, and often a different
owner. The person doing the RCA spends most of the time **collecting and matching
information**, not analysing it.

This creates real problems for the company:

| Problem | Effect |
|---|---|
| The investigation takes days or weeks | The same incident happens again while the RCA is still open |
| Senior experts spend hours on searching | Expensive people do low-value work |
| Past RCAs are written but rarely found again | The company solves the same problem twice |
| The result depends on who does the investigation | RCA quality is not consistent |
| Evidence is copied by hand into documents | Conclusions are hard to verify later |

The company loses time and money, and the knowledge it already has stays unused.

---

## 1.2 Objective

Build an application that does the searching and correlation automatically, and gives
the expert a **draft RCA with candidate causes and evidence**, ready to be reviewed.

The application must:

1. Propose which incidents belong together, so the Problem Manager can group them into a
   problem. Every RCA starts from a problem.
2. Find the past incidents and past RCAs that are similar to the problem, on the same service.
3. Describe the pattern behind the recurrence: which service, under which conditions, and
   whether the failures follow a time pattern, for example every Monday during the payroll
   batch.
4. Collect the technical evidence: service dependencies, recent changes, logs.
5. Propose one or more candidate root causes, each supported by evidence with citations,
   and a confidence level calculated by code.
6. Say clearly what it could not check.
7. Ask a human Technical Expert to approve, reject, or request more details.
8. Keep every RCA with all its revisions and decisions, visible to both roles.

What we want to achieve:

- Reduce the time from "RCA needed" to "RCA draft ready" from days to minutes.
- Reduce the manual work of the expert to reviewing instead of searching.
- Make every conclusion traceable to the evidence behind it.
- Reuse the knowledge already stored in past RCAs.

The AI never decides the root cause. It prepares the case. The human decides.

---

## 1.3 Scope

### What the application does

- Proposes groups of alike incidents as problems, and lets the Problem Manager accept,
  reject, or create a problem by hand.
- Lets the Problem Manager add or remove incidents, close and reopen a problem, and give
  optional guidance for the investigation.
- Starts an RCA for one problem, covering all its incidents.
- Runs the automatic investigation over four sources: past RCAs and incidents, CMDB,
  changes, logs.
- Produces candidate root causes with confidence, evidence and citations, and a cause
  diagram (5 Whys or Fishbone).
- Sends the draft to the Technical Expert, when the Problem Manager decides to.
- Handles the three expert answers: approve, reject, request more details.
- Runs a new revision of the RCA when the expert asks for more details.
- Closes the problem when the expert validates a root cause.
- Records every step for audit: what was searched, what was decided, who decided it.
- Shows four KPIs about how well the analysis works.

### Who uses it

| Role | What they do |
|---|---|
| Problem Manager | Groups incidents into problems, starts the RCA, follows the investigation, sends the draft to the expert, starts the next revision when the expert asks for more. Main user. |
| Technical Expert | Reviews the RCAs sent to them: the candidate causes and the evidence, then approves, rejects, or asks for more details. |

Each user signs in with their own account, and the account has one of the two roles. The
Incident Manager is not a user of this application. Incidents arrive as data.

### What the application produces

One RCA per investigation of a problem. An RCA has one or more **revisions**: each run of
the investigation is a revision, and every revision is kept. Each revision holds the
candidate causes, the evidence behind them, the timeline, what could not be checked and
the steps of the run.

When the expert approves, the RCA is **validated**: it holds the validated root cause, the
expert who decided, the comment, the dates, and it closes the problem.

Each revision also carries two suggestions about what to do next: a possible workaround,
and whether a change is likely to be needed. These are **recommendations, not actions**.
The application never creates a Known Error and never opens a Change Request. It hands
over a finished analysis, and the next process decides what to do with it.

---

## 1.4 Assumptions

- The incidents arrive as input. The application proposes how to group them, but the
  Problem Manager decides which incidents form a problem and which problem gets an RCA.
- The company already has past RCA documents that can be searched.
- CMDB, change records and logs exist and can be read.
- For this project all four sources are mock data, built to look realistic.
- Both users are internal employees. There is no external access.
- The Technical Expert has the knowledge to judge whether a hypothesis is correct.
- The application runs at zero cost: an open-weight model on the Groq free tier, and a
  local embedding model in Ollama.

---

## 1.5 Exclusions

The following are outside this project:

- A complete Problem Management system.
- Incident Management: detecting, registering or resolving incidents.
- Change Management: creating or approving change requests.
- Creating Known Error records or Change Requests. The RCA can say that one is likely
  needed, but it never creates one.
- Any automatic action on real systems. The application only investigates and proposes.
- Real integrations with real ITSM tools. Everything is mocked.
- Deciding the root cause without a human. The AI always stops at candidate hypotheses.
- Predicting future incidents. The application looks at what already happened.
