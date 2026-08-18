# 2. Understanding of the Current Process

**Project:** AI-assisted Root Cause Analysis (RCA) application
**Area:** Problem Management, large company
**Last updated:** 2026-08-19

---

## 2.1 How an RCA is done today

The process below is the traditional way of working, without AI. It starts after an
incident has already been resolved and someone decides that the cause must be
investigated.

The short version:

| Stage | How it is done today | Where it loses time | What the application changes |
|---|---|---|---|
| Spotting the recurrence | Weekly reports read by hand in Excel or Jira | Days or weeks; a pattern spread over several services is missed | Similar incidents are grouped automatically, by meaning and by time |
| Collecting the context | Five or six tools opened one by one: tickets, old RCAs, CMDB, change calendar, logs | Time lost switching between systems, each with its own search | All sources are queried in one run |
| Finding the cause | Brainstorming from what the team remembers, then trial and error | Depends on who is available; the first plausible cause wins | The evidence is correlated and at least two hypotheses are written, each with its proof |
| Writing it down | The document is written by hand, often incomplete | No common structure, so the task is avoided | A structured draft is ready before the review starts |

The detailed version follows.

| Step | What happens | Who does it | Typical time |
|---|---|---|---|
| 1 | An incident comes back several times, so an RCA is requested | Problem Manager | hours |
| 2 | An owner is assigned and technical people are asked to help | Problem Manager | 1 day |
| 3 | Similar past incidents are searched in the ticket system | Problem Manager | hours |
| 4 | Past RCA documents are searched to see if this happened before | Problem Manager | hours to days |
| 5 | The affected service and its dependencies are checked in the CMDB | Technical Expert | hours |
| 6 | Recent changes and deployments are collected from Change Management | Technical Expert | hours to days |
| 7 | Logs from the incident window are requested and read | Technical Expert | days |
| 8 | Everything is put in one timeline and compared | Technical Expert | hours to days |
| 9 | Hypotheses are discussed in a meeting with several teams | Both + other teams | days |
| 10 | The chosen hypothesis is verified technically | Technical Expert | days |
| 11 | The RCA document is written, reviewed and approved | Both | days |

In a large company this takes **one to four weeks** for a single RCA. Most of that time
is not analysis. It is searching, waiting and repeating the same explanation to different
teams.

### What the work really looks like

The expert opens five or six different tools. The ticket system for incidents. A document
library for old RCAs. The CMDB for dependencies. The change calendar for deployments. The
log platform for the error messages. Each tool has its own search and its own way of
naming the same service.

Then everything is copied into a spreadsheet or a document, sorted by time, and read
until something looks connected.

---

## 2.2 Bottlenecks

These are the points where the current process loses the most time and quality.

**Information is spread across many systems.**
There is no single place to ask "what do we know about this service around this date". The
expert must ask each system separately, one by one.

**Searching old RCAs almost never works.**
Past RCAs are free text documents. The search is keyword based. If the old RCA says
"connection pool exhausted" and the new incident says "database timeouts", the search
finds nothing. The knowledge exists but stays hidden.

**Waiting for other teams.**
Log access, database metrics or deployment details often belong to another team. A
request can wait one or two days before someone answers.

**Manual correlation.**
Building the timeline by hand is slow and easy to get wrong. A change that happened 34
minutes before the incident is easy to miss if nobody looks at that exact window.

**Expert time is used badly.**
The most experienced people spend most of their hours collecting information instead of
judging it.

**The first plausible cause wins.**
When the investigation is long and tiring, the first explanation that sounds reasonable is
usually accepted. Alternative causes are rarely written down.

**The investigation depends on who is available.**
The people who can judge a production failure are the most senior and the most booked. If
they are busy with another incident, the RCA waits for them.

**Memory decides more often than evidence.**
The investigation starts from what the team remembers about the last similar failure. A
familiar cause is accepted faster than an unfamiliar one, and the evidence is then read to
confirm it instead of to test it.

**The result depends on the person.**
Two experts investigating the same incident produce two different documents, with
different structure and different depth.

**Evidence is not traceable.**
The final document says "the logs showed connection timeouts", but it does not say which
log lines. Six months later nobody can check the conclusion.

**Recurrence is noticed too late.**
Because incidents are handled one by one, nobody sees that this is the fifth time the same
pattern appears, until it becomes serious.

---

## 2.3 What can be improved with AI

The tasks that take the most time are searching, matching and correlating. These are
exactly the tasks a machine does well.

| Today | With the application |
|---|---|
| The expert searches five systems by hand | The system queries all sources automatically |
| Old RCAs are found by keyword, or not at all | Old RCAs are found by meaning, using semantic search |
| Similar incidents are spotted by memory | Similar incidents are grouped automatically |
| The timeline is built manually in a spreadsheet | The timeline is built automatically from the collected evidence |
| Hypotheses come from one long meeting | A draft with hypotheses and evidence is ready before the meeting |
| Usually one hypothesis is written | At least two are proposed, so alternatives are not lost |
| "The logs showed errors" | Every statement points to the exact record it came from |
| Each RCA looks different | Every RCA has the same structure |
| Nobody records what was not checked | The gaps are written down explicitly |

The result is that the expert receives a prepared case instead of an empty page.

---

## 2.4 What must stay human

AI is good at collecting and comparing. It is not the right thing to decide the cause of a
failure in a real production system.

These parts stay with people:

- **The decision.** Only the Technical Expert confirms that a hypothesis is the real cause.
- **Technical judgement.** Many things are not written in any system: how the service
  really behaves, what the team changed last month without a ticket, what is normal for
  this application.
- **Verification.** Testing a hypothesis means looking at the real system, not at
  documents.
- **Responsibility.** The Problem Manager owns the RCA and answers for the result.

This is why the application always stops at candidate hypotheses and asks for approval.
The goal is not to replace the investigation. It is to remove the manual work around it,
so the expert can spend the time on the part that actually needs an expert.
