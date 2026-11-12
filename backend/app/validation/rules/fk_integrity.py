"""VAL-02 — Foreign-key integrity, validation_strategy.md §2.

Uses SQLite's own `PRAGMA foreign_key_check` rather than re-deriving FK
metadata by hand — it is the storage engine's own authoritative answer to
"does every FK column resolve to an existing parent row", covering every
FK on every one of the 22 tables (including the six onto `SystemActor`
and `ScreeningRun.screening_rule_id`) with no risk of the check module
drifting out of sync with the schema.
"""

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.validation.report import Finding

RULE_ID = "VAL-02"
RULE_CATEGORY = "fk_integrity"


def check(session: Session) -> list[Finding]:
    findings: list[Finding] = []
    rows = session.execute(text("PRAGMA foreign_key_check")).fetchall()
    for row in rows:
        # (table, rowid, parent, fkid)
        table, rowid, parent, fkid = row
        findings.append(
            Finding(
                rule_id=RULE_ID,
                rule_category=RULE_CATEGORY,
                entity_type=table,
                entity_id=str(rowid),
                message=f"Row {rowid} in {table} has a foreign key (id {fkid}) that does not resolve in {parent}",
                severity="violation",
            )
        )
    return findings
