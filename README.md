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

## Getting started

This section takes you from a fresh clone to a running application. Follow the steps in
order the first time. After that, you only need [Run the application](#run-the-application).

### Prerequisites

| Tool | Version | What it is used for |
|---|---|---|
| [Python](https://www.python.org/downloads/) | 3.12 | Runs the application, the scripts and the tests |
| [Git](https://git-scm.com/downloads) | any recent | Clones the repository |
| [Ollama](https://ollama.com/download) | any recent | Creates the embeddings for the search, locally |
| A [Groq](https://console.groq.com/keys) account | free tier | Gives the API key for the reasoning model |
| A [LangSmith](https://smith.langchain.com) account | free tier | Optional. Only needed to open the graph in LangGraph Studio |

No GPU is needed. The reasoning runs on Groq, and Ollama only creates embeddings.

### 1. Clone the repository

```bash
git clone <repository-url>
cd root-cause-analysis
```

### 2. Create a virtual environment and install the dependencies

macOS / Linux:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Windows (PowerShell):

```powershell
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Every command below assumes the virtual environment is active.

### 3. Add your API key

Copy the example file and fill in your Groq key:

```bash
cp .env.example .env        # Windows: copy .env.example .env
```

| Variable | Required | Default | What it does |
|---|---|---|---|
| `GROQ_API_KEY` | yes | — | The key from the Groq console |
| `GROQ_MODEL` | no | `openai/gpt-oss-120b` | The model the agents use. `openai/gpt-oss-20b` is faster and has its own quota, useful for testing |
| `RAGAS_DO_NOT_TRACK` | no | `true` | Stops RAGAS from sending usage statistics. Only used by the evaluation |
| `RAGAS_JUDGE_MODEL` | no | `openai/gpt-oss-120b` | The model that judges the hypotheses in the evaluation |

The `.env` file is ignored by Git. Never commit it.

### 4. Start Ollama and download the embedding model

Make sure Ollama is running (the desktop app, or `ollama serve` in a separate terminal),
then download the model once:

```bash
ollama pull nomic-embed-text
```

The application expects Ollama at `http://localhost:11434`, which is its default address.

### 5. Prepare the data

The mock source files are already in the repository, in `data/`. Two local stores are built
from them, and neither is committed to Git, so you build them once after cloning:

```bash
python scripts/load_sources_sqlite.py --reset   # SQLite database: data/rca_sources.sqlite3
python scripts/ingest_chroma.py --reset         # ChromaDB search index: chroma_db/
```

The second command needs Ollama running. It takes a few minutes the first time.

### Run the application

The application has two parts, and each runs in its own terminal. Start the backend first.

**Terminal 1 — the backend (FastAPI):**

```bash
uvicorn api:app --port 8000 --reload
```

**Terminal 2 — the interface (Streamlit):**

```bash
streamlit run rca/ui/main.py
```

| What | Address |
|---|---|
| The interface | http://localhost:8501 |
| The backend API documentation (Swagger) | http://localhost:8000/docs |
| The backend health check | http://localhost:8000/health |

The interface does not read the database itself. It calls the backend, so it shows an error
if the backend is not running. Ollama must also be running while an investigation is in
progress.

> If the backend runs somewhere else, set `API_URL` before starting the interface, for
> example `API_URL=http://192.168.1.10:8000`. The default is `http://127.0.0.1:8000`.

---

## Useful commands

All commands run from the root of the repository, with the virtual environment active.

### See the investigation graph in LangGraph Studio

LangGraph Studio draws the graph of the investigation, lets you start a run, and shows the
state after every node.

```bash
langgraph dev
```

The command starts a local server at `http://127.0.0.1:2024` and opens Studio in the browser:

```text
https://smith.langchain.com/studio/?baseUrl=http://127.0.0.1:2024
```

- Studio is a web page served by LangSmith, so you need to be signed in to a free LangSmith
  account. Your data stays on the local server; no LangSmith API key is needed in `.env`.
- The graph is read from `rca/pipeline.py:graph`, as set in `langgraph.json`. Studio always
  shows the same pipeline the application runs.
- To start a run, fill in the `incident_id` field of the input, for example
  `INC-2026-00482`. The `owner` field is optional. The run uses Groq and Ollama, exactly like
  the application.
- Studio does not refresh on its own after you change the code. Stop the server with
  `Ctrl+C` and start it again.

### Export the graph as an image

```bash
python scripts/export_graph.py                  # Mermaid file and PNG, in diagrams/04-architecture/
python scripts/export_graph.py --format mmd     # only the Mermaid file, fully offline
python scripts/export_graph.py --out-dir docs   # write the files somewhere else
```

The PNG is drawn by the public service mermaid.ink, so the names of the graph nodes are sent
to it. Use `--format mmd` to avoid that.

### Run one investigation from the terminal

Runs the whole pipeline without the interface, prints every step, and saves the draft RCA in
the database:

```bash
python scripts/run_rca.py INC-2026-00482
python scripts/run_rca.py INC-2026-00482 --owner "Jane Doe"
```

### Search the knowledge base directly

Useful to check what the search finds before the agents see it:

```bash
python scripts/query_chroma.py --collection historical_incidents --query "database connection pool issue" --before "2026-07-14T14:32:00Z"
python scripts/query_chroma.py --collection historical_rcas --query "Payment API timeout after deployment" --service "Payment API"
```

| Option | What it does |
|---|---|
| `--collection` | `historical_incidents` or `historical_rcas` |
| `--before` | Only records older than this date, as the agents see them |
| `--service` | Only records from this service |
| `--max-distance` | How similar a result must be. Lower is stricter |
| `--limit` | The maximum number of results (default 5) |

### Rebuild the mock data

The mock data is generated by a script, so it is the same on every machine. Run this after
you change the stories or the catalog in `scripts/mock_data/`:

```bash
python scripts/build_mock_data.py --check       # build and validate only, write nothing
python scripts/build_mock_data.py               # write the files in data/
python scripts/load_sources_sqlite.py --reset   # reload the sources (problems and RCAs are kept)
python scripts/load_sources_sqlite.py --reset-app  # only when the problems changed: also starts the
                                                 # problems and RCAs again (a copy is kept in data/backups/)
python scripts/ingest_chroma.py --reset         # rebuild the search index
```

More detail is in [scripts/README.md](scripts/README.md).

### Run the tests

```bash
python -m pytest                    # all tests that do not call Groq
python -m pytest tests/test_tools.py
python -m pytest -m live            # only the tests that call the real Groq API
```

The live tests use your Groq quota. Set `GROQ_MODEL=openai/gpt-oss-20b` in `.env` to run them
on the smaller model.

### Run the RAGAS evaluation

The evaluation has its own dependencies, which are not needed to run the application:

```bash
python -m pip install -r requirements.txt -r requirements-eval.txt
```

```bash
python scripts/evaluate_ragas.py retrieval                    # score the search (needs Ollama)
python scripts/evaluate_ragas.py calibrate --thresholds 0.35 0.40 0.45 0.50 0.55
python scripts/evaluate_ragas.py faithfulness --run-stories   # score the hypotheses (needs Groq)
```

Every run writes a new folder in `results/ragas/` and never changes the application data.
The method and how to read the scores are explained in [ragas_project.md](ragas_project.md).

---

## Troubleshooting

| Problem | Cause and fix |
|---|---|
| The interface shows `Connection to API failed` | The backend is not running. Start it with `uvicorn api:app --port 8000` |
| `Connection refused` on port `11434` | Ollama is not running. Open the Ollama app or run `ollama serve` |
| An investigation finds no past incidents or RCAs | The search index is empty. Run `python scripts/ingest_chroma.py --reset` |
| `no such table` or an empty incident list | The database was not created. Run `python scripts/load_sources_sqlite.py --reset` |
| Groq error `429` | The free tier limit was reached. The application waits and retries; wait a minute between runs |
| `Activate.ps1 cannot be loaded` on Windows | Run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once, then activate again |
| A change in the code does not show in the interface | Streamlit keeps imported modules in memory. Stop it with `Ctrl+C` and start it again |

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
