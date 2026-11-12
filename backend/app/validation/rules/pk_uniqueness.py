"""VAL-01 — Primary-key uniqueness, validation_strategy.md §1.

Generic, table-driven: iterates every mapped table's PK columns rather
than hand-coding 22 separate checks. SQLite's own PRIMARY KEY constraint
already makes a real duplicate structurally impossible to insert in the
first place (this is the "structurally guaranteed" note in §1 — a hit
here would mean the storage engine itself is broken, not that an anomaly
slipped through); this module exists as an independent, read-only
verification layer regardless.
"""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.base import Base
from app.validation.report import Finding

RULE_ID = "VAL-01"
RULE_CATEGORY = "pk_uniqueness"


def check(session: Session) -> list[Finding]:
    findings: list[Finding] = []
    for mapper in Base.registry.mappers:
        table = mapper.local_table
        pk_cols = list(table.primary_key.columns)
        if not pk_cols:
            continue
        count_col = func.count().label("cnt")
        stmt = select(*pk_cols, count_col).group_by(*pk_cols).having(count_col > 1)
        for row in session.execute(stmt):
            *pk_values, count = row
            pk_text = ",".join(str(v) for v in pk_values)
            findings.append(
                Finding(
                    rule_id=RULE_ID,
                    rule_category=RULE_CATEGORY,
                    entity_type=table.name,
                    entity_id=pk_text,
                    message=f"Primary key ({pk_text}) appears {count} times in {table.name}",
                    severity="violation",
                )
            )
    return findings
