"""Is this Streamlit server running older code than the files? (final_project_steps.md, E9)

Streamlit runs every page again on each visit, but keeps the modules it imported (the models, the texts, the
client of the API) as they were when the server started. After a change of the code, a page can then meet an
older module and fail with an error that does not tell why. The pages compare the files with the start of
the server and say so instead.
"""

from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path

STARTED = time.time()  # this module is imported once, when the server starts
ROOT = Path(__file__).resolve().parents[1]  # rca/


def changed_since_start() -> datetime | None:
    """The last change of a module the server keeps in memory, when it is newer than the start. The pages
    themselves (app_pages) are run again on every visit, so a change to them needs no restart."""
    newest = max((path.stat().st_mtime for path in ROOT.rglob("*.py") if "app_pages" not in path.parts), default=0)
    return datetime.fromtimestamp(newest) if newest > STARTED + 1 else None
