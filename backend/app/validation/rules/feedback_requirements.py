"""VAL-08 — Feedback completeness, validation_strategy.md §8,
business_rules.md §6.

Check: no `Application` at stage `Offer`/`Hired` has a `Completed`
`Interview` without a `Feedback` row. Expected zero at baseline; exactly
10 (full) / 2 (starter) post-injection (MissingFeedbackStageAdvanced,
Phase 5 — not yet exercised).
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Application, Feedback, Interview
from app.validation.report import Finding

RULE_ID = "VAL-08"
RULE_CATEGORY = "feedback_requirements"


def check(session: Session) -> list[Finding]:
    findings: list[Finding] = []

    applications = {
        a.application_id: a
        for a in session.execute(select(Application)).scalars()
        if a.stage in ("Offer", "Hired")
    }
    interview_ids_with_feedback = {
        f.interview_id for f in session.execute(select(Feedback)).scalars()
    }

    for iv in session.execute(select(Interview)).scalars():
        if iv.application_id not in applications:
            continue
        if iv.status == "Completed" and iv.interview_id not in interview_ids_with_feedback:
            findings.append(
                Finding(
                    RULE_ID, RULE_CATEGORY, "application", iv.application_id,
                    f"application advanced to stage "
                    f"{applications[iv.application_id].stage!r} but Completed interview "
                    f"{iv.interview_id} has no Feedback row",
                    "violation",
                )
            )

    return findings
