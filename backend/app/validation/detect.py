"""Phase 6 — independent operational detection layer.

Does **not** implement new detection logic for four of the five anomaly
types — `scheduling_conflicts.py` (VAL-06), `feedback_requirements.py`
(VAL-08), `salary_band.py` (VAL-10), and `closed_req_active_apps.py`
(part of VAL-12) already are real, from-scratch, ground-truth-blind
detectors, built in Phase 4 and already proven against injected data in
Phase 5 (business_rules.md §13 step 4 — "the same 16 validation/
detection modules from step 2, run again"). This module's job is to
expose them as **one** detection entry point, grouped by anomaly type
rather than by `VAL-nn` rule ID, for the offline evaluator
(`validation/evaluate.py`) to consume — never to redefine their logic.

For duplicate applications, per this phase's explicit instruction,
reuses `duplicate_submissions.check()` + `select_detected_duplicates()`
rather than duplicating that detection algorithm.

**This module must never reference ground truth** — same guarantee as
`validation/rules/*.py`, now explicitly extended to cover this file too
(`ground_truth_leakage.SCAN_FILES`, not just `SCAN_ROOTS`), since it is
one of the "operational detector modules" this phase's instructions
require to be checked, even though it lives outside `validation/rules/`
for organizational reasons (it aggregates across modules, the same
placement rationale as `runner.py`).
"""

from sqlalchemy.orm import Session

from app.validation.report import Finding
from app.validation.rules import (
    closed_req_active_apps,
    duplicate_submissions,
    feedback_requirements,
    salary_band,
    scheduling_conflicts,
)

# Anomaly-type name -> the detector function producing its operational
# findings. Order matches business_rules.md Sec9's table.
ANOMALY_TYPES = [
    "UnavailableInterviewer",
    "DuplicateApplication",
    "MissingFeedbackStageAdvanced",
    "SalaryOutsideBand",
    "ClosedReqActiveApplications",
]


def _detect_duplicate_applications(session: Session) -> list[Finding]:
    all_findings = duplicate_submissions.check(session)
    return duplicate_submissions.select_detected_duplicates(all_findings)


_DETECTOR_BY_TYPE = {
    "UnavailableInterviewer": scheduling_conflicts.check,
    "DuplicateApplication": _detect_duplicate_applications,
    "MissingFeedbackStageAdvanced": feedback_requirements.check,
    "SalaryOutsideBand": salary_band.check,
    "ClosedReqActiveApplications": closed_req_active_apps.check,
}


def run_detectors(session: Session) -> dict[str, list[Finding]]:
    """Runs all five independent detectors and returns their findings
    grouped by anomaly type. Each call re-derives its findings fresh from
    operational records only — no caching, no shared mutable state, so
    calling this twice against an unchanged database always returns
    identical results (verified by tests, not just asserted)."""
    return {anomaly_type: fn(session) for anomaly_type, fn in _DETECTOR_BY_TYPE.items()}
