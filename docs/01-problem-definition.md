# 1. Problem Definition and Scope

**Project:** AI-assisted Root Cause Analysis (RCA) application
**Area:** Problem Management, large company
**Last updated:** 2026-08-19

---

## 1.1 The problem

In ITIL, an **incident** is an interruption of a service, and a **problem** is the cause
behind one or more incidents. Incident Management restores the service as fast as
possible. Problem Management asks why it broke and makes sure it does not break again.
These are two different jobs, and this application belongs to the second one.

A large company runs hundreds of IT services. Some incidents keep coming back. When that
happens, Problem Management must find out **why** it happens, not only restore the
service. This investigation is called Root Cause Analysis.

Today this work is manual. To investigate one recurring incident, a person has to:

- read the current incident and find the older incidents that look similar,
- search past RCA documents to see if the same thing happened before,
- open the CMDB to understand what the affected service depends on,
- check which changes and deployments happened before the incident,
- read logs from the incident time window,
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
the expert a **draft RCA with hypotheses and evidence**, ready to be reviewed.

The application must:

1. Find the past incidents and past RCAs that are similar to the current one.
2. Describe the pattern behind the recurrence: which service, under which conditions, and
   whether the failures follow a time pattern, for example every Monday during the payroll
   batch.
3. Collect the technical evidence: service dependencies, recent changes, logs.
4. Propose one or more candidate root causes, each supported by evidence with citations.
5. Say clearly what it could not check.
6. Ask a human Technical Expert to approve, reject, or request more evidence.
7. Produce one final RCA record, visible to both the Problem Manager and the expert.

What we want to achieve:

- Reduce the time from "RCA needed" to "RCA draft ready" from days to minutes.
- Reduce the manual work of the expert to reviewing instead of searching.
- Make every conclusion traceable to the evidence behind it.
- Reuse the knowledge already stored in past RCAs.

The AI never decides the root cause. It prepares the case. The human decides.

---

## 1.3 Scope

### What the application does

- Starts an RCA for one incident that needs an investigation.
- Builds the group of similar past incidents that form the recurring problem.
- Runs the automatic investigation over four sources: past RCAs, CMDB, changes, logs.
- Produces candidate root causes with confidence, evidence and citations.
- Sends the draft to the Technical Expert for review.
- Handles the three expert answers: approve, reject, request more evidence.
- Lets the Problem Manager accept the validated RCA or send it back for clarification.
- Stores the final RCA and shows it to both roles.
- Records every step for audit: what was searched, what was decided, who approved.

### Who uses it

| Role | What they do |
|---|---|
| Problem Manager | Starts the RCA, follows the investigation, sends the draft to the expert, accepts the final RCA. Main user. |
| Technical Expert | Reviews the hypotheses and the evidence, then approves, rejects, or asks for more evidence. |

The Incident Manager is not a user of this application. Incidents arrive as data.

### What the application produces

One final RCA record containing: the status, the validated root cause, the evidence
behind it, the technical validation, the RCA owner, the creation date and the completion
date.

The record also carries two suggestions about what to do next: a possible workaround, and
whether a change is likely to be needed. These are **recommendations, not actions**. The
application never creates a Known Error and never opens a Change Request. It hands over a
finished analysis, and the next process decides what to do with it.

---

## 1.4 Assumptions

- The incidents that need an RCA are already identified and arrive as input. The
  application does not decide which incident deserves an RCA.
- The company already has past RCA documents that can be searched.
- CMDB, change records and logs exist and can be read.
- For this project all four sources are mock data, built to look realistic.
- Both users are internal employees. There is no external access.
- The Technical Expert has the knowledge to judge whether a hypothesis is correct.
- The application runs with an open-source model at zero cost.

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
