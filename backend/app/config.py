"""Central configuration constants.

Deliberately plain (no pydantic-settings dependency yet) per the project's
"avoid unnecessary abstraction" principle (architecture.md §8) — revisit only if
a later phase genuinely needs validated settings objects.
"""

import os

# Fixed generation seed — PROJECT_SPEC.md §5, never overridden at runtime.
SEED = 20261022

DATABASE_PATH = os.environ.get("DATABASE_PATH", "data/talentflow.db")
DATASET_MODE = os.environ.get("DATASET_MODE", "starter")
