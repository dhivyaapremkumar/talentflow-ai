"""VAL-15 — Ground-truth non-leakage (whole-package),
validation_strategy.md §17.

Scans every `.py` file under `app/services/` and `app/validation/rules/`
for a textual reference to the ground-truth label model name or the
ground-truth FK field name — not just import statements, since a module
could in principle reach the column without importing the model
(validation_strategy.md §17). One whole-package test covers every rule
module automatically, including ones added later, with no per-module
line to remember to write.

Deliberately placed outside `validation/rules/` (same placement pattern
as `reconcile.py`/`checksums.py`) so this scanner's own source — which
must textually name the two forbidden strings in order to search for
them — never scans itself and produces a false positive against itself.
`services/` does not exist yet (Phase 7/8); scanning a not-yet-created
directory correctly yields zero findings, not an error.
"""

from pathlib import Path

from app.validation.report import Finding

RULE_ID = "VAL-15"
RULE_CATEGORY = "ground_truth_leakage"

_LABEL_MODEL_NAME = "AnomalyLabel"
_LABEL_FIELD_NAME = "ground_truth_label_id"
FORBIDDEN_STRINGS = (_LABEL_MODEL_NAME, _LABEL_FIELD_NAME)

SCAN_ROOTS = ("services", "validation/rules")


def check(app_root: Path) -> list[Finding]:
    findings: list[Finding] = []

    for rel_root in SCAN_ROOTS:
        root = app_root / rel_root
        if not root.exists():
            continue
        for py_file in sorted(root.rglob("*.py")):
            text = py_file.read_text(encoding="utf-8")
            rel_path = py_file.relative_to(app_root).as_posix()
            for forbidden in FORBIDDEN_STRINGS:
                if forbidden in text:
                    findings.append(
                        Finding(
                            RULE_ID, RULE_CATEGORY, "source_file", rel_path,
                            f"{rel_path} contains a reference to {forbidden!r}, which is forbidden "
                            "for any module under services/ or validation/rules/",
                            "violation",
                        )
                    )

    return findings
