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

# The most tokens one request may count, the answer reserved by the provider included: the free tier of
# Groq refuses a request above 8000 tokens (413), and it reserves about 2048 tokens for the answer
# (measured, final_project_steps.md E5). The agents fit their input under it (rca/llm.input_budget).
LLM_REQUEST_LIMIT_TOKENS = int(os.getenv("LLM_REQUEST_LIMIT_TOKENS", "8000"))
LLM_OUTPUT_RESERVE_TOKENS = int(os.getenv("LLM_OUTPUT_RESERVE_TOKENS", "2048"))
# How long the reasoning models (gpt-oss) think before they answer: "low", "medium" or "high"; empty leaves the
# provider default. Their thinking counts as output tokens, so it shares the output limit with the answer
# (final_project_steps.md, E10).
LLM_REASONING_EFFORT = os.getenv("LLM_REASONING_EFFORT", "").strip().lower()
# The request limit of the providers without the 8000 tokens limit of the Groq free tier (Gemini, OpenRouter):
# their requests may carry more of the evidence before anything is shortened.
LLM_LARGE_REQUEST_LIMIT_TOKENS = int(os.getenv("LLM_LARGE_REQUEST_LIMIT_TOKENS", "24000"))

# The variants of E10 (final_project_steps.md), each measured against the code without it, on the same model:
# V3 the answer schema without titles and developer notes; V4 the output limit sent with every request, as large
# as the request limit leaves; V5 the rule that a hypothesis must go past the symptom to the change behind it.
LLM_COMPACT_SCHEMA = os.getenv("LLM_COMPACT_SCHEMA", "false").strip().lower() == "true"
LLM_EXPLICIT_OUTPUT_LIMIT = os.getenv("LLM_EXPLICIT_OUTPUT_LIMIT", "false").strip().lower() == "true"
REASONING_CAUSE_RULE = os.getenv("REASONING_CAUSE_RULE", "false").strip().lower() == "true"

# The judge of the evaluations (rca/judge.py), never the agents: a model of another family than the
# agents, with its own free budget. A model whose name starts with "gemini" goes to Google AI Studio,
# any other to Groq. On the free tier Google may use the prompts to improve its models: mock data only,
# and it allows only about 20 requests a day per model (checked on gemini-3.5-flash): enough for short
# checks, not for a full evaluation.
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
JUDGE_MODEL = os.getenv("JUDGE_MODEL", "gemini-3.5-flash")

# The SQLite database: source data (loaded by scripts/load_sources_sqlite.py) and the RCA records.
DB_PATH = ROOT_DIR / "data" / "rca_sources.sqlite3"
