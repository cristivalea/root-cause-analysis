"""Project settings, read from the environment and from the .env file."""

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[1]

load_dotenv(ROOT_DIR / ".env")

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")

# For manual tests only: when GROQ_MODEL reaches its daily limit, the next of these models answers
# (rca/llm.py). Off by default, and the evaluations turn it off, so a run is never a mix of models.
# Gemini and OpenRouter free tiers may use the prompts to train their models: mock data only.
LLM_FALLBACK = os.getenv("LLM_FALLBACK", "false").strip().lower() == "true"
FALLBACK_MODELS = [model.strip() for model in os.getenv(
    "FALLBACK_MODELS",
    "groq:openai/gpt-oss-20b,gemini:gemini-3.5-flash,openrouter:nvidia/nemotron-3-super-120b-a12b:free",
).split(",") if model.strip()]
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")

# The judge of the evaluations (rca/judge.py), never the agents: a model of another family than the
# agents, with its own free budget. A model whose name starts with "gemini" goes to Google AI Studio,
# any other to Groq. On the free tier Google may use the prompts to improve its models: mock data only,
# and it allows only about 20 requests a day per model (checked on gemini-3.5-flash): enough for short
# checks, not for a full evaluation.
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
JUDGE_MODEL = os.getenv("JUDGE_MODEL", "gemini-3.5-flash")

# The SQLite database: source data (loaded by scripts/load_sources_sqlite.py) and the RCA records.
DB_PATH = ROOT_DIR / "data" / "rca_sources.sqlite3"
