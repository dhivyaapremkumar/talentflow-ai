"""VAL-16 — Export consistency, validation_strategy.md §20/§21.

Applies to post-injection only (exports are produced once, from the
final state of a generation run) — since Phase 5 (anomaly injection)
does not exist yet in this codebase, there is no post-injection dataset
to export, so this check is a no-op (returns no findings, not a false
"zero violations" claim) unless an `export_dir` is actually supplied.

**Scope note, flagged (not silent):** `data_generation/export.py`
(Phase 3) only produces the CSV format plus two small JSON summary
files (`table_checksums.json`, `entity_counts.json`) — there is no
per-table JSON export or SQL-dump export yet, so this check compares
only the CSV format against the live database. Full JSON/SQL export
formats are deferred to whichever later phase finalizes the export
pipeline (already flagged in `implementation_plan.md`'s Phase 3 row).
"""

import csv
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.data_generation.export import TABLE_ORDER
from app.db.base import Base
from app.validation.report import Finding

RULE_ID = "VAL-16"
RULE_CATEGORY = "export_consistency"


def check(session: Session, export_dir: Path | None) -> list[Finding]:
    findings: list[Finding] = []
    if export_dir is None or not export_dir.exists():
        return findings

    for table_name in TABLE_ORDER:
        csv_path = export_dir / f"{table_name}.csv"
        if not csv_path.exists():
            findings.append(
                Finding(
                    RULE_ID, RULE_CATEGORY, table_name, "*",
                    f"expected export file {csv_path} does not exist",
                    "violation",
                )
            )
            continue

        with csv_path.open("r", encoding="utf-8", newline="") as f:
            exported_row_count = sum(1 for _ in csv.reader(f)) - 1  # minus header

        table = Base.metadata.tables[table_name]
        db_row_count = session.execute(select(func.count()).select_from(table)).scalar_one()

        if exported_row_count != db_row_count:
            findings.append(
                Finding(
                    RULE_ID, RULE_CATEGORY, table_name, "*",
                    f"export has {exported_row_count} rows but the live database has "
                    f"{db_row_count} rows",
                    "violation",
                )
            )

    return findings
