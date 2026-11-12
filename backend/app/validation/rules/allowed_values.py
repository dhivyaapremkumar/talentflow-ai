"""VAL-03 — Required fields, nullability, enum/allowed values,
validation_strategy.md §3.

**Implementation note (a flagged choice, not a silent deviation):**
§3's text says this reuses "the Pydantic schema's own validators" — but
`app/schemas/` (the Pydantic contract layer) is a later phase
(architecture.md §7's directory tree lists it for the API layer, not yet
built as of Phase 4). Building a full Pydantic schema layer now, only to
satisfy this one rule, would be out-of-scope abstraction for this phase.
This module instead achieves the same intent generically, directly off
SQLAlchemy's own column metadata — not-null columns and `Enum`-typed
columns across all 22 tables — with no risk of drifting out of sync with
the schema, the same table-driven approach already used for VAL-01/VAL-02.
Once `app/schemas/` exists, it should delegate to this module (or vice
versa) rather than maintaining two independent rule definitions.
"""

from sqlalchemy import Enum as SAEnum
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.base import Base
from app.validation.report import Finding

RULE_ID = "VAL-03"
RULE_CATEGORY = "required_and_allowed_values"


def _pk_text(table, row_mapping) -> str:
    return ",".join(str(row_mapping[c.name]) for c in table.primary_key.columns)


def check(session: Session) -> list[Finding]:
    findings: list[Finding] = []
    for mapper in Base.registry.mappers:
        table = mapper.local_table
        not_null_cols = [c for c in table.columns if not c.nullable]
        enum_cols = [c for c in table.columns if isinstance(c.type, SAEnum)]
        if not not_null_cols and not enum_cols:
            continue

        stmt = select(table)
        for row in session.execute(stmt).mappings():
            entity_id = _pk_text(table, row)

            for col in not_null_cols:
                if row[col.name] is None:
                    findings.append(
                        Finding(
                            rule_id=RULE_ID,
                            rule_category=RULE_CATEGORY,
                            entity_type=table.name,
                            entity_id=entity_id,
                            message=f"{col.name} is NULL but is a required field",
                            severity="violation",
                        )
                    )

            for col in enum_cols:
                value = row[col.name]
                if value is not None and value not in col.type.enums:
                    findings.append(
                        Finding(
                            rule_id=RULE_ID,
                            rule_category=RULE_CATEGORY,
                            entity_type=table.name,
                            entity_id=entity_id,
                            message=f"{col.name}={value!r} is not in the allowed set {col.type.enums}",
                            severity="violation",
                        )
                    )
    return findings
