"""VAL-12 — Reconciliation of generated records, validation_strategy.md §12.

Row counts against the mandated targets (`volumes_for_mode`, the same
module `data_generation/generator.py` uses — one source of truth,
architecture.md §6), the canonical-attempt/ScreeningRun 1:1 invariants,
the `uq_screeningrule_current` partial-unique invariant independently
re-derived, the baseline `AnomalyLabel` zero-count expectation, and the
closed-req-with-active-applications detector (anomaly type 5).

FK orphan count is deliberately not re-derived here — VAL-02
(`fk_integrity.py`) is the authoritative source for that; this module
would only ever duplicate it (validation_strategy.md §12's own note:
"disagreement between that and reconciliation is a generator defect").
"""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.data_generation.volumes import volumes_for_mode
from app.db.models import (
    AnomalyLabel,
    Application,
    ApplicationSubmissionAttempt,
    JobRequisition,
    ScreeningRule,
    ScreeningRun,
)
from app.validation.report import Finding
from app.validation.rules import closed_req_active_apps

RULE_ID = "VAL-12"
RULE_CATEGORY = "reconciliation"


def _count(session: Session, model) -> int:
    return session.execute(select(func.count()).select_from(model)).scalar_one()


def check(session: Session, mode: str) -> list[Finding]:
    findings: list[Finding] = []
    volumes = volumes_for_mode(mode)

    target_by_model = {
        JobRequisition: ("job_requisition", volumes["job_requisition"]),
        Application: ("application", volumes["application"]),
        ScreeningRun: ("screening_run", volumes["application"]),  # 1:1 shadow
    }
    for model, (table_name, target) in target_by_model.items():
        actual = _count(session, model)
        if actual != target:
            findings.append(
                Finding(
                    RULE_ID, RULE_CATEGORY, table_name, "*",
                    f"row count {actual} does not match the {mode} target {target}",
                    "violation",
                )
            )

    app_count = _count(session, Application)

    canonical_count = session.execute(
        select(func.count()).select_from(ApplicationSubmissionAttempt).where(
            ApplicationSubmissionAttempt.is_canonical.is_(True)
        )
    ).scalar_one()
    if canonical_count != app_count:
        findings.append(
            Finding(
                RULE_ID, RULE_CATEGORY, "application_submission_attempt", "*",
                f"{canonical_count} canonical attempts, expected exactly {app_count} (one per Application)",
                "violation",
            )
        )

    latest_run_count = session.execute(
        select(func.count()).select_from(ScreeningRun).where(ScreeningRun.is_latest.is_(True))
    ).scalar_one()
    if latest_run_count != app_count:
        findings.append(
            Finding(
                RULE_ID, RULE_CATEGORY, "screening_run", "*",
                f"{latest_run_count} is_latest=true rows, expected exactly {app_count} (one per Application)",
                "violation",
            )
        )

    # uq_screeningrule_current invariant, independently re-derived: every
    # requisition that has ever had a ScreeningRule has exactly one
    # is_current=true row.
    current_counts: dict[str, int] = {}
    for rule in session.execute(select(ScreeningRule)).scalars():
        if rule.is_current:
            current_counts[rule.requisition_id] = current_counts.get(rule.requisition_id, 0) + 1
    for req_id, count in current_counts.items():
        if count != 1:
            findings.append(
                Finding(
                    RULE_ID, RULE_CATEGORY, "job_requisition", req_id,
                    f"{count} is_current=true ScreeningRule rows (expected exactly 1)",
                    "violation",
                )
            )

    # AnomalyLabel expectation: exactly 0 (baseline, before Phase 5 has run)
    # or exactly the documented total for this mode (post-injection,
    # business_rules.md Sec9a) — never any other count. This single check
    # covers both validation modes without needing a separate "has
    # injection run yet" flag threaded through from the caller.
    anomaly_label_count = _count(session, AnomalyLabel)
    expected_total = sum(volumes["anomaly_counts"].values()) + volumes["anomaly_counts"][
        "closed_requisition"
    ]  # closed_requisition produces 2 AnomalyLabel rows per incident (A-12)
    if anomaly_label_count not in (0, expected_total):
        findings.append(
            Finding(
                RULE_ID, RULE_CATEGORY, "anomaly_label", "*",
                f"{anomaly_label_count} AnomalyLabel rows exist — expected either 0 (no injection "
                f"has run) or exactly {expected_total} (business_rules.md Sec9a, this {mode} mode)",
                "violation",
            )
        )

    findings.extend(closed_req_active_apps.check(session))

    return findings
