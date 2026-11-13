"""Anomaly summary analytics — Phase 9, implementation_plan.md's Phase 9
row and workflow.md §8: "Anomaly summary (counts by type, from the
validation report, not `AnomalyLabel`)."

**The operational/evaluation split, and why it exists (requirement 8 —
"avoid exposing ground-truth labels in ordinary operational dashboards or
exports unless explicitly required for evaluation reporting"):**

- `operational_anomaly_summary()` calls `validation.detect.run_detectors()`
  verbatim — Phase 6's own "one detection entry point, grouped by anomaly
  type" (its own docstring's phrase), already built from the from-scratch,
  ground-truth-blind detectors Phase 4 wrote. **Deliberately not**
  `validation.runner.run_all_rules()`/`counts_by_rule`: that function's
  per-`VAL-nn`-rule-ID counts are too coarse for two of the five anomaly
  types — `VAL-11` mixes `DuplicateApplication` detections together with
  unrelated consistency/invariant findings
  (`duplicate_submissions.py`'s own docstring: three distinct
  `rule_category` values share `rule_id="VAL-11"`), and `VAL-12` mixes
  `ClosedReqActiveApplications` findings together with generic row-count-
  vs-target reconciliation findings that are only meaningful for a
  synthetic dataset matching an exact starter/full target count, never
  for an arbitrary live operational database (a real bug, caught by this
  phase's own empty-database test: an empty database reported 3 "VAL-12"
  violations that were actually "0 rows, expected 150" reconciliation
  noise, not anomalies). `run_detectors()` calls each type's detector
  function directly — `closed_req_active_apps.check()`,
  `duplicate_submissions.select_detected_duplicates(duplicate_submissions.
  check())` — sidestepping both mixing problems entirely, not working
  around them with extra filtering logic of this module's own. It never
  imports, queries, or returns anything about `AnomalyLabel`. This is what
  an ordinary operational dashboard may show.
- `evaluation_summary_from_report()` loads one of Phase 6's **already
  computed** JSON evaluation reports (`data/evaluation_reports/<mode>.json`,
  written by `validation/evaluate.py`) verbatim — it does not recompute
  detection or re-derive TP/FP/FN itself (requirement 4: "reuse the
  existing Phase 6 anomaly evaluation reports rather than duplicating or
  changing detection logic"). Its output does carry ground-truth-derived
  figures (TP/FP/FN/precision/recall/F1 — the whole point of that
  report), so by this module's own naming it is reserved for an
  explicitly-labeled "evaluation reporting" context (`workflow.md` §7's
  dev-only "Ground Truth" view, `implementation_plan.md`'s Phase 10 row),
  never silently merged into the operational summary above.

`ANOMALY_TYPES` (re-exported from `validation.detect`) is the five seeded
`anomaly_type` values (`business_rules.md` §9a), in the same order
`run_detectors()` and Phase 6's evaluator already use.
"""

import json
from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session

from app.validation.detect import ANOMALY_TYPES, run_detectors

__all__ = [
    "ANOMALY_TYPES",
    "operational_anomaly_summary",
    "evaluation_summary_from_report",
    "export_operational_anomaly_summary",
]


def operational_anomaly_summary(session: Session) -> dict:
    """Runs Phase 6's five independent, ground-truth-blind detectors
    against the current database and returns counts by anomaly type,
    derived entirely from each detector's own findings — no ground truth
    read anywhere in this function."""
    findings_by_type = run_detectors(session)
    counts_by_anomaly_type = {
        anomaly_type: len(findings) for anomaly_type, findings in findings_by_type.items()
    }
    return {
        "checked_at": datetime.now().isoformat(),
        "counts_by_anomaly_type": counts_by_anomaly_type,
        "total_violations": sum(counts_by_anomaly_type.values()),
    }


def evaluation_summary_from_report(report_path: Path) -> dict:
    """Loads an already-computed Phase 6 evaluation report verbatim —
    `report_path` is typically `data/evaluation_reports/<mode>.json`,
    written by `validation/evaluate.py`. Raises `FileNotFoundError` if
    that report has not been generated yet (callers in an evaluation-
    reporting context are expected to have run
    `python -m app.validation.evaluate --mode <mode>` first; this
    function does not run it on their behalf, to keep the "which code
    path can see ground truth" boundary explicit and auditable).

    **This is the only function in this module whose output is derived
    from ground truth** — callers must treat it as evaluation-reporting
    content, not something to render on an ordinary operational
    dashboard (requirement 8).
    """
    report_path = Path(report_path)
    if not report_path.exists():
        raise FileNotFoundError(
            f"evaluation report {report_path} does not exist — run "
            "`python -m app.validation.evaluate --mode <mode>` first"
        )
    return json.loads(report_path.read_text(encoding="utf-8"))


def export_operational_anomaly_summary(session: Session, output_dir: Path) -> dict:
    """Writes `operational_anomaly_summary()`'s output to
    `<output_dir>/anomaly_summary_operational.json`. Contains no
    ground-truth-derived figures — safe for an ordinary operational
    export, unlike `evaluation_summary_from_report()`'s content."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    summary = operational_anomaly_summary(session)
    (output_dir / "anomaly_summary_operational.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    return summary
