"""VAL-15 — Ground-truth non-leakage (whole-package),
validation_strategy.md §17.

Scans every `.py` file under `app/services/` and `app/validation/rules/`,
plus the specific individual files in `SCAN_FILES` below, for a textual
reference to the ground-truth label model name or the ground-truth FK
field name — not just import statements, since a module could in
principle reach the column without importing the model
(validation_strategy.md §17). One whole-package test covers every rule
module automatically, including ones added later, with no per-module
line to remember to write.

**`SCAN_FILES` (added Phase 6):** `validation/detect.py` is an
"operational detector module" per this phase's explicit requirement
("all operational detector modules are checked for ground-truth
access"), but it lives outside `validation/rules/` for the same
organizational reason `runner.py` does (it aggregates across existing
rule modules rather than defining a new `VAL-nn` rule) — so a directory-
level `SCAN_ROOTS` entry would either miss it (if scoped to
`validation/rules/` only) or wrongly also scan `validation/evaluate.py`,
`reconcile.py`, and this scanner's own file (if scoped to all of
`validation/`) — `reconcile.py` and `evaluate.py` are the explicitly
*permitted* exceptions (§17's named exclusions), and this file would
trip its own scan. `SCAN_FILES` gives file-level precision instead of
directory-level.

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
SCAN_FILES = ("validation/detect.py",)


def check(app_root: Path) -> list[Finding]:
    findings: list[Finding] = []

    py_files: list[Path] = []
    for rel_root in SCAN_ROOTS:
        root = app_root / rel_root
        if root.exists():
            py_files.extend(sorted(root.rglob("*.py")))
    for rel_file in SCAN_FILES:
        file_path = app_root / rel_file
        if file_path.exists():
            py_files.append(file_path)

    for py_file in py_files:
        text = py_file.read_text(encoding="utf-8")
        rel_path = py_file.relative_to(app_root).as_posix()
        for forbidden in FORBIDDEN_STRINGS:
            if forbidden in text:
                findings.append(
                    Finding(
                        RULE_ID, RULE_CATEGORY, "source_file", rel_path,
                        f"{rel_path} contains a reference to {forbidden!r}, which is forbidden "
                        "for any operational detector module",
                        "violation",
                    )
                )

    return findings
