"""Closed-requisition-with-active-applications detector — part of VAL-12
(validation_strategy.md §12), anomaly type 5 (ClosedReqActiveApplications).

Flags any `JobRequisition` with `status in {Closed, Cancelled}` that has
non-terminal-stage `Application` rows attached. Reporting granularity,
keyed on `application_id` (validation_strategy.md §12, finalized):
emits one violation row per affected `Application.application_id`, not
one aggregated row per requisition — matching the ground-truth label
table's own matching-key field for this type exactly (entity type
Application, per the data dictionary's anomaly-label section).

Deliberately described only in these generic terms, never by the
ground-truth table's literal model name — this file lives under
`validation/rules/`, where VAL-15's whole-package scanner (`app.
validation.ground_truth_leakage`) forbids that name anywhere in source,
comments and docstrings included.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Application, JobRequisition
from app.validation.report import Finding

RULE_ID = "VAL-12"
RULE_CATEGORY = "closed_req_active_apps"

TERMINAL_STAGES = {"Hired", "Rejected", "Withdrawn"}
TERMINAL_REQ_STATUSES = {"Closed", "Cancelled"}


def check(session: Session) -> list[Finding]:
    findings: list[Finding] = []

    requisitions = {
        r.requisition_id: r
        for r in session.execute(select(JobRequisition)).scalars()
        if r.status in TERMINAL_REQ_STATUSES
    }
    if not requisitions:
        return findings

    for app in session.execute(select(Application)).scalars():
        req = requisitions.get(app.requisition_id)
        if req is not None and app.stage not in TERMINAL_STAGES:
            findings.append(
                Finding(
                    RULE_ID, RULE_CATEGORY, "application", app.application_id,
                    f"application is at non-terminal stage {app.stage!r} but its requisition "
                    f"{req.requisition_id} status is {req.status!r}",
                    "violation",
                )
            )

    return findings
