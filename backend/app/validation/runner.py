"""Central validation runner — executes every VAL-01..VAL-16 rule module
against one database session and assembles one structured report
(validation_strategy.md §15/§21). Read-only: no rule module here ever
mutates data (architecture.md §2).

`report_mode` ("baseline" or "post_injection") is a report-labeling
concept only — every rule function computes the same real findings from
the data regardless of it; see `report.build_report`'s docstring.
`dataset_mode` ("starter" or "full") is a different thing entirely — the
generation scale, needed by VAL-12's reconciliation check to know which
row-count targets apply. These must never be conflated into one `mode`
parameter (a real bug caught while wiring this module into the
generator, fixed before this phase was reported done).
"""

from pathlib import Path

from sqlalchemy.orm import Session

from app.validation import checksums, ground_truth_leakage, reconcile
from app.validation.report import Finding, build_report
from app.validation.rules import (
    allowed_values,
    date_ordering,
    duplicate_submissions,
    export_consistency,
    feedback_requirements,
    fk_integrity,
    lifecycle_transitions,
    offer_approval,
    pk_uniqueness,
    role_appropriateness,
    salary_band,
    scheduling_conflicts,
    screening_recompute,
)

APP_ROOT = Path(__file__).resolve().parent.parent

RULE_IDS = [
    "VAL-01",
    "VAL-02",
    "VAL-03",
    "VAL-04",
    "VAL-05",
    "VAL-06",
    "VAL-07a",
    "VAL-07b",
    "VAL-08",
    "VAL-09",
    "VAL-10",
    "VAL-11",
    "VAL-12",
    "VAL-13",
    "VAL-14",
    "VAL-15",
    "VAL-16",
]


def run_all_rules(
    session: Session,
    dataset_mode: str,
    report_mode: str = "baseline",
    export_dir: Path | None = None,
) -> dict:
    findings: list[Finding] = []

    findings.extend(pk_uniqueness.check(session))
    findings.extend(fk_integrity.check(session))
    findings.extend(allowed_values.check(session))
    findings.extend(date_ordering.check(session))
    findings.extend(screening_recompute.check(session))
    findings.extend(scheduling_conflicts.check(session))
    findings.extend(lifecycle_transitions.check(session))
    findings.extend(feedback_requirements.check(session))
    findings.extend(offer_approval.check(session))
    findings.extend(salary_band.check(session))
    findings.extend(duplicate_submissions.check(session))
    findings.extend(reconcile.check(session, dataset_mode))
    # VAL-13 (checksums) needs an existing GenerationRun row to compare
    # against — it is a no-op (zero findings) when called before one
    # exists, e.g. the baseline gate, which must run *before*
    # GenerationRun is written.
    findings.extend(checksums.check(session))
    findings.extend(role_appropriateness.check(session))
    findings.extend(ground_truth_leakage.check(APP_ROOT))
    findings.extend(export_consistency.check(session, export_dir))

    return build_report(findings, report_mode, RULE_IDS)
