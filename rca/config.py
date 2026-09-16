"""Project settings, read from the environment and from the .env file."""

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[1]

load_dotenv(ROOT_DIR / ".env")

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")

# The SQLite database: source data (loaded by scripts/load_sources_sqlite.py) and the RCA records.
DB_PATH = ROOT_DIR / "data" / "rca_sources.sqlite3"
