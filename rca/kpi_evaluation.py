"""What the two KPI evaluation scripts share (scripts/eval_kpi_accuracy.py, scripts/eval_kpi_confidence.py).

The evaluation is an exam on the 13 stories of data/evaluation/answer_key.json, so it must run on the same data
every time, whatever was done in the application meanwhile:

- the database is built from the source files (data/sources), in a temporary folder: the problems of the stories
  are open there, as the answer key expects, and the application's database is never read or written;
- the fallback models are off: every story is answered by config.GROQ_MODEL, so two runs can be compared (as
  scripts/evaluate_ragas.py already does); the models that actually answered are kept in the report;
- SCRIPT_VERSION marks the reports written this way; rca/kpis.py shows only those.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from rca import config, storage
from rca.models import RCARecord

SCRIPT_VERSION = 2
SOURCES = config.ROOT_DIR / "data" / "sources"


def fresh_database() -> Path:
    """A new database with the source data only (incidents, CMDB, changes, logs and the problems of the
    sources), in a temporary folder."""
    path = Path(tempfile.mkdtemp(prefix="rca-kpi-")) / "evaluation.sqlite3"
    storage.load_sources(path, SOURCES)
    return path


def same_model_for_every_story() -> None:
    config.LLM_FALLBACK = False


def models_used(record: RCARecord) -> list[str]:
    """The models that answered the agent steps of the run, as the steps saved them ("groq:openai/gpt-oss-120b")."""
    found: list[str] = []
    for step in record.trace:
        for model in (step.details or {}).get("models") or []:
            if model not in found:
                found.append(model)
    return found
