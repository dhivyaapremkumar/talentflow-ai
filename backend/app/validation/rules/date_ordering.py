"""VAL-04 — Date/timestamp ordering, validation_strategy.md §4.

Covers the cross-table ordering rules `data_dictionary.md` documents but
that cannot be expressed as same-row SQLite CHECK constraints (already
flagged as Phase-4 deferrals in the Phase 2 model docstrings), plus the
two new ones this pass: the canonical `ApplicationSubmissionAttempt`'s
`submitted_at` must be the minimum in its `(candidate_id, requisition_id)`
group, and `Application.applied_at` must equal that canonical attempt's
`submitted_at`. Same-row orderings (e.g. `Offer.extended_at >=
approved_at`) are already DB CHECK-enforced since Phase 2 and are not
re-checked here.
"""

from datetime import datetime
from itertools import groupby

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    Application,
    ApplicationSubmissionAttempt,
    Candidate,
    CandidateSkill,
    Feedback,
    Interview,
    JobRequisition,
    ResumeArtifact,
)
from app.validation.report import Finding

RULE_ID = "VAL-04"
RULE_CATEGORY = "date_ordering"


def _as_datetime(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    return datetime.combine(value, datetime.min.time())


def check(session: Session) -> list[Finding]:
    findings: list[Finding] = []

    candidates = {c.candidate_id: c for c in session.execute(select(Candidate)).scalars()}
    requisitions = {r.requisition_id: r for r in session.execute(select(JobRequisition)).scalars()}
    applications = {a.application_id: a for a in session.execute(select(Application)).scalars()}
    attempts = list(session.execute(select(ApplicationSubmissionAttempt)).scalars())
    interviews = {i.interview_id: i for i in session.execute(select(Interview)).scalars()}

    # Application.applied_at >= Candidate.created_at and >= JobRequisition.opened_at
    for app in applications.values():
        cand = candidates.get(app.candidate_id)
        if cand and app.applied_at < cand.created_at:
            findings.append(
                Finding(
                    RULE_ID, RULE_CATEGORY, "application", app.application_id,
                    f"applied_at {app.applied_at} is before candidate.created_at {cand.created_at}",
                    "violation",
                )
            )
        req = requisitions.get(app.requisition_id)
        if req and req.opened_at and app.applied_at < _as_datetime(req.opened_at):
            findings.append(
                Finding(
                    RULE_ID, RULE_CATEGORY, "application", app.application_id,
                    f"applied_at {app.applied_at} is before requisition.opened_at {req.opened_at}",
                    "violation",
                )
            )
        if app.screening_computed_at is not None and app.screening_computed_at < app.applied_at:
            findings.append(
                Finding(
                    RULE_ID, RULE_CATEGORY, "application", app.application_id,
                    f"screening_computed_at {app.screening_computed_at} is before applied_at {app.applied_at}",
                    "violation",
                )
            )

    # Interview.scheduled_start >= Application.screening_computed_at
    for iv in interviews.values():
        app = applications.get(iv.application_id)
        if app and app.screening_computed_at and iv.scheduled_start < app.screening_computed_at:
            findings.append(
                Finding(
                    RULE_ID, RULE_CATEGORY, "interview", iv.interview_id,
                    f"scheduled_start {iv.scheduled_start} is before "
                    f"application.screening_computed_at {app.screening_computed_at}",
                    "violation",
                )
            )

    # Feedback.submitted_at >= Interview.scheduled_end
    for fb in session.execute(select(Feedback)).scalars():
        iv = interviews.get(fb.interview_id)
        if iv and fb.submitted_at < iv.scheduled_end:
            findings.append(
                Finding(
                    RULE_ID, RULE_CATEGORY, "feedback", fb.feedback_id,
                    f"submitted_at {fb.submitted_at} is before interview.scheduled_end {iv.scheduled_end}",
                    "violation",
                )
            )

    # ResumeArtifact.uploaded_at >= Candidate.created_at
    for ra in session.execute(select(ResumeArtifact)).scalars():
        cand = candidates.get(ra.candidate_id)
        if cand and ra.uploaded_at < cand.created_at:
            findings.append(
                Finding(
                    RULE_ID, RULE_CATEGORY, "resume_artifact", ra.resume_artifact_id,
                    f"uploaded_at {ra.uploaded_at} is before candidate.created_at {cand.created_at}",
                    "violation",
                )
            )

    # CandidateSkill.updated_at >= Candidate.created_at
    for cs in session.execute(select(CandidateSkill)).scalars():
        cand = candidates.get(cs.candidate_id)
        if cand and cs.updated_at < cand.created_at:
            findings.append(
                Finding(
                    RULE_ID, RULE_CATEGORY, "candidate_skill",
                    f"{cs.candidate_id},{cs.skill_id}",
                    f"updated_at {cs.updated_at} is before candidate.created_at {cand.created_at}",
                    "violation",
                )
            )

    # Canonical attempt must have the minimum submitted_at in its group;
    # Application.applied_at must equal the canonical attempt's submitted_at.
    attempts_sorted = sorted(attempts, key=lambda a: (a.candidate_id, a.requisition_id))
    for (candidate_id, requisition_id), group_iter in groupby(
        attempts_sorted, key=lambda a: (a.candidate_id, a.requisition_id)
    ):
        group = list(group_iter)
        canonical = [a for a in group if a.is_canonical]
        min_submitted_at = min(a.submitted_at for a in group)
        for c in canonical:
            if c.submitted_at != min_submitted_at:
                findings.append(
                    Finding(
                        RULE_ID, RULE_CATEGORY, "application_submission_attempt", c.attempt_id,
                        f"is_canonical=true but submitted_at {c.submitted_at} is not the minimum "
                        f"({min_submitted_at}) in its (candidate_id, requisition_id) group",
                        "violation",
                    )
                )
            app = applications.get(c.canonical_application_id)
            if app and app.applied_at != c.submitted_at:
                findings.append(
                    Finding(
                        RULE_ID, RULE_CATEGORY, "application", app.application_id,
                        f"applied_at {app.applied_at} does not equal the canonical attempt's "
                        f"submitted_at {c.submitted_at}",
                        "violation",
                    )
                )

    return findings
