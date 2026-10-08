"""Project settings, read from the environment and from the .env file."""

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[1]

load_dotenv(ROOT_DIR / ".env")

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")

# The judge of the evaluations (rca/judge.py), never the agents: a model of another family than the
# agents, with its own free budget. A model whose name starts with "gemini" goes to Google AI Studio,
# any other to Groq. On the free tier Google may use the prompts to improve its models: mock data only,
# and it allows only about 20 requests a day per model (checked on gemini-3.5-flash): enough for short
# checks, not for a full evaluation.
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
JUDGE_MODEL = os.getenv("JUDGE_MODEL", "gemini-3.5-flash")

# The SQLite database: source data (loaded by scripts/load_sources_sqlite.py) and the RCA records.
DB_PATH = ROOT_DIR / "data" / "rca_sources.sqlite3"
