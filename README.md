# AI-assisted Root Cause Analysis (RCA)

An application that helps a Problem Manager find out why an incident keeps coming back.

It gathers the past incidents and RCAs, the service dependencies, the recent changes and the
logs, and writes a draft with the candidate root causes and the evidence behind each one. A
Technical Expert then approves it, rejects it or asks for more details. **The AI does the
searching; a person decides the cause.**

- Every fact becomes a numbered piece of evidence before the model reasons, and a cause that
  cites anything else is refused in code.
- No RCA is final without the approval of an expert, whatever the confidence.
- The application only recommends. It never changes a real system.

---

## Tech stack

| Part | Technology |
|---|---|
| Interface | React 18 + TypeScript (Vite, Tailwind), in English and Romanian |
| Backend | FastAPI, SQLite |
| Agents | LangGraph, open models on Groq |
| Search | ChromaDB, embeddings with `nomic-embed-text` in Ollama (local) |
| Tracing | Arize Phoenix (optional) |

No GPU is needed and everything runs at zero licensing cost. All source systems are mock data.

---

## Requirements

| Install | Version | Used for |
|---|---|---|
| [Python](https://www.python.org/downloads/) | 3.11 or 3.12 | Backend, scripts, tests |
| [Node.js](https://nodejs.org/en/download) | 20 or later | Interface |
| [Ollama](https://ollama.com/download) | any recent | Embeddings for the search |
| [Groq API key](https://console.groq.com/keys) | free tier | The reasoning model |

---

## Quick start

Run every command from the root of the repository. The first time, follow all the steps.

**1. Install the Python dependencies**

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

**2. Configure**

```bash
cp .env.example .env               # Windows: copy .env.example .env
```

Fill in `GROQ_API_KEY` and `JWT_SECRET` in `.env`. The file explains each value.

**3. Download the embedding model** (Ollama must be running)

```bash
ollama pull nomic-embed-text
```

**4. Build the data** (the mock files are in `data/`, the stores are built locally)

```bash
python scripts/load_sources_sqlite.py --reset   # SQLite database
python scripts/ingest_chroma.py --reset         # search index, a few minutes
```

**5. Create the users**

```bash
python scripts/create_user.py manager problem_manager
python scripts/create_user.py expert technical_expert
```

Each command asks for a password.

**6. Start the application**, in two terminals:

```bash
uvicorn api:app --port 8000 --reload            # terminal 1: backend
```

```bash
cd web
npm install                                     # first time only
npm run dev                                     # terminal 2: interface
```

Open **http://localhost:5173** and sign in. The API documentation is at
http://localhost:8000/docs.

After the first time, only step 6 is needed.

---

## Commands

### Tests

```bash
python -m pytest                   # backend, without calling Groq
python -m pytest -m live           # only the tests that call Groq (uses your quota)

cd web
npm test                           # interface
npm run lint
npm run typecheck
```

### Interface for production

```bash
cd web
npm run build                      # result in web/dist/
npm run preview                    # serves it on http://localhost:4173
```

If the backend is not on `http://127.0.0.1:8000`, set `API_URL` before `npm run dev` or
`npm run preview`.

### One investigation from the terminal

```bash
python scripts/run_rca.py INC-2026-00482
```

### Change the mock data

After editing the stories or the catalog in `scripts/mock_data/`:

```bash
python scripts/build_mock_data.py --check       # validate only
python scripts/build_mock_data.py               # write the files in data/
python scripts/load_sources_sqlite.py --reset   # reload the sources, problems and RCAs are kept
python scripts/ingest_chroma.py --reset         # rebuild the search index
```

`load_sources_sqlite.py --reset-app` also starts the problems and RCAs again, keeping a copy in
`data/backups/`. More in [scripts/README.md](scripts/README.md).

### The graph in LangGraph Studio

```bash
langgraph dev
```

Opens Studio at `https://smith.langchain.com/studio/?baseUrl=http://127.0.0.1:2024`. You
need a free LangSmith account; the data stays local.

### Tracing with Phoenix

```bash
docker compose up phoenix
```

Set `PHOENIX_COLLECTOR_ENDPOINT=http://localhost:6006` in `.env` and restart the backend.
The traces are at http://localhost:6006.

### Evaluation

```bash
pip install -r requirements-eval.txt
python scripts/evaluate_ragas.py retrieval
python scripts/eval_kpi_accuracy.py
python scripts/eval_kpi_confidence.py
```

The RAGAS results are written in `results/ragas/`, the KPI reports in `data/evaluation/`.

---

## Project structure

```text
api.py            FastAPI backend
rca/              investigation pipeline, agents, guardrails, storage
web/              React interface
scripts/          data loading, users, evaluation
data/             mock source data
tests/            backend tests
docs/             documentation
diagrams/         diagrams of the documentation (draw.io)
```

---

## Documentation

| File | What it answers |
|---|---|
| [01-problem-definition.md](docs/01-problem-definition.md) | The problem, the objective, the scope |
| [02-current-process.md](docs/02-current-process.md) | How an RCA is done today, without AI |
| [03-proposed-solution.md](docs/03-proposed-solution.md) | The new flow, the roles, the states of an RCA |
| [04-architecture.md](docs/04-architecture.md) | The components, the diagrams, the data flow |
| [05-data-and-rag.md](docs/05-data-and-rag.md) | The data, the mock data, how ChromaDB is used |
| [06-reasoning-and-execution.md](docs/06-reasoning-and-execution.md) | The agents, the checks, the human approval |
| [07-kpis.md](docs/07-kpis.md) | What we measure and when the project is successful |

---

## Troubleshooting

| Problem | Fix |
|---|---|
| The interface can't reach the server | Start the backend: `uvicorn api:app --port 8000` |
| `Lipsește JWT_SECRET` when the backend starts | Add `JWT_SECRET` to `.env` |
| `Connection refused` on port 11434 | Start Ollama (the app, or `ollama serve`) |
| No past incidents or RCAs are found | Run `python scripts/ingest_chroma.py --reset` |
| `no such table` or an empty list | Run `python scripts/load_sources_sqlite.py --reset` |
| Groq error `429` | The free limit was reached; wait a minute and try again |
| `Activate.ps1 cannot be loaded` on Windows | Run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once |
| `npm` is not recognised | Install Node.js and open a new terminal |

---

## Scope

This project builds only the RCA part of Problem Management. It does not manage incidents or
changes, does not create Known Error records and does not connect to a real ITSM tool.
