"""VAL-13 — Deterministic reproducibility using checksums,
validation_strategy.md §13.

Re-derives each of the 21 operational tables' canonical CSV straight
from the *live database* (not from in-memory generation state) and
compares against the most recent `GenerationRun.table_checksums_json`/
`overall_checksum` — proving the recorded manifest genuinely reflects
what's actually stored, not just what the generator process remembered
producing. Shares `export.py`'s exact canonicalization logic
(`data_generation/export.py`) rather than re-deriving it, per
architecture.md §6.

The "run the generator twice and diff" half of this check (full
cross-process reproducibility) is exercised directly by
`tests/test_data_generation.py` in Phase 3 — this module is the
complementary "does the stored manifest match the live DB" half, which
only makes sense once a `GenerationRun` row exists to compare against.
"""

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.data_generation.export import TABLE_COLUMNS, TABLE_ORDER, _canonical_csv
from app.db.base import Base
from app.db.models import GenerationRun
from app.validation.report import Finding

RULE_ID = "VAL-13"
RULE_CATEGORY = "checksums"


def _table_rows_as_dicts(session: Session, table_name: str) -> list[dict]:
    table = Base.metadata.tables[table_name]
    columns = TABLE_COLUMNS[table_name]
    stmt = select(*[table.c[c] for c in columns])
    return [dict(zip(columns, row)) for row in session.execute(stmt)]


def check(session: Session) -> list[Finding]:
    findings: list[Finding] = []

    run = session.execute(
        select(GenerationRun).order_by(GenerationRun.generated_at.desc())
    ).scalars().first()
    if run is None:
        return findings  # Nothing to compare yet.

    recorded_checksums = json.loads(run.table_checksums_json)

    import hashlib

    recomputed_checksums = {}
    for table_name in TABLE_ORDER:
        rows = _table_rows_as_dicts(session, table_name)
        csv_text = _canonical_csv(table_name, rows)
        recomputed_checksums[table_name] = hashlib.sha256(csv_text.encode("utf-8")).hexdigest()

    for table_name in TABLE_ORDER:
        recorded = recorded_checksums.get(table_name)
        recomputed = recomputed_checksums[table_name]
        if recorded != recomputed:
            findings.append(
                Finding(
                    RULE_ID, RULE_CATEGORY, table_name, run.run_id,
                    f"GenerationRun.table_checksums_json records {recorded!r} for {table_name}, "
                    f"but a fresh checksum of the live table is {recomputed!r}",
                    "violation",
                )
            )

    overall_recomputed = hashlib.sha256(
        "".join(recomputed_checksums[t] for t in TABLE_ORDER).encode("utf-8")
    ).hexdigest()
    if run.overall_checksum != overall_recomputed:
        findings.append(
            Finding(
                RULE_ID, RULE_CATEGORY, "generation_run", run.run_id,
                f"overall_checksum {run.overall_checksum!r} does not match the recomputed "
                f"{overall_recomputed!r}",
                "violation",
            )
        )

    return findings
