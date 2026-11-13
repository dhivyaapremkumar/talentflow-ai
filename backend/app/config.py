"""Central configuration constants.

Deliberately plain (no pydantic-settings dependency yet) per the project's
"avoid unnecessary abstraction" principle (architecture.md §8) — revisit only if
a later phase genuinely needs validated settings objects.
"""

import os
from pathlib import Path

# Fixed generation seed — PROJECT_SPEC.md §5, never overridden at runtime.
SEED = 20261022

# backend/ — the directory containing pyproject.toml, app/, data/, tests/.
# A relative DATABASE_PATH is resolved against this, not the caller's
# current working directory, so the live app behaves identically whether
# started from backend/, the repo root, or anywhere else (a real bug this
# fixes: a relative "data/..." path previously only worked by accident,
# when uvicorn happened to be launched with backend/ as the CWD).
BACKEND_ROOT = Path(__file__).resolve().parent.parent


def _resolve_database_path(raw: str) -> str:
    path = Path(raw)
    if not path.is_absolute():
        path = BACKEND_ROOT / path
    return str(path)


# Default points at the committed starter dataset's database — the one a
# fresh clone can actually produce by running the generator once (Phase 3),
# so the live app has real data to serve out of the box. DATABASE_PATH
# remains a full override: set it to any other database file (e.g. the
# full-mode database, or a different path entirely) to use that instead.
DATABASE_PATH = _resolve_database_path(
    os.environ.get("DATABASE_PATH", "data/talentflow_starter.db")
)
DATASET_MODE = os.environ.get("DATASET_MODE", "starter")
