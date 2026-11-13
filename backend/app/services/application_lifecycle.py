"""The live application-lifecycle service — Phase 8,
implementation_plan.md's Phase 8 row: `services/application_lifecycle.py`
"stays soft/advisory" for every transition (business_rules.md §11 lists
no hard-enforced row for `ApplicationStageHistory` — the only two hard
gates in the whole project are the two named `PendingApproval->Approved`
rows, §11).

Reuses `validation.rules.lifecycle_transitions.APPLICATION_LEGAL_EDGES`
verbatim — the same edge set the Phase 4 validator audits the generated
dataset against (architecture.md §6). This module never redefines the
transition graph.

**Hard gate that *does* apply here — not a role check, a readiness
precondition:** `business_rules.md` §6 / `workflow.md` §5 — an
`Application` may not reach stage `Offer` or `Hired` unless *every*
`Interview` belonging to it with `status = "Completed"` also has a
`Feedback` row. This is enforced for both target stages, exactly the
missing-feedback gate `validation/rules/feedback_requirements.py` audits
post-hoc; a hit there in generated data would mean this gate was bypassed
(matching that module's own stated expectation of zero at baseline).

**Composition note:** `_transition_application_stage_core()` is the
no-commit/no-rollback engine, exposed so `services/offer_lifecycle.py`
can advance `Application.stage` to `Hired` on offer acceptance inside its
*own* transaction (one atomic operation spanning both tables), rather
than duplicating the stage-transition algorithm. `transition_application_
stage()` is the public, self-contained entry point for every other
caller.

**Scope boundary, flagged (not silent):** withdrawal/resubmission
behavior (business_rules.md §3a) and Phase 7's submission reconciliation
are both already correct by construction and require no new code here —
nothing in this module, or in `services/application_submission.py`, ever
reads or writes the other's concern (`Application.stage` vs.
`ApplicationSubmissionAttempt.is_canonical`). `withdraw()` below only
ever writes `Application.stage`/`withdrawn_at`.
"""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Application, Feedback, Interview, SystemActor
from app.db.models.history import ApplicationStageHistory
from app.validation.rules.lifecycle_transitions import APPLICATION_LEGAL_EDGES

FEEDBACK_GATED_STAGES = ("Offer", "Hired")


class ApplicationLifecycleError(Exception):
    """Raised when an application-stage transition cannot proceed — the
    service rolls back the session before raising, so the caller is
    never left mid-transaction."""


def _next_history_id(session: Session) -> str:
    existing = session.execute(select(ApplicationStageHistory.history_id)).scalars().all()
    nums = [int(v.split("-")[1]) for v in existing]
    next_num = (max(nums) + 1) if nums else 1
    return f"APH-{next_num:06d}"


def _transition_application_stage_core(
    session: Session,
    application_id: str,
    to_stage: str,
    actor_id: str,
    changed_at: datetime | None,
    reason_text: str | None,
    rejected_reason: str | None,
) -> ApplicationStageHistory:
    application = session.get(Application, application_id)
    if application is None:
        raise ApplicationLifecycleError(f"Application {application_id!r} does not exist")

    actor = session.get(SystemActor, actor_id)
    if actor is None:
        raise ApplicationLifecycleError(f"SystemActor {actor_id!r} does not exist")

    from_stage = application.stage
    edge = (from_stage, to_stage)
    if edge not in APPLICATION_LEGAL_EDGES:
        raise ApplicationLifecycleError(f"illegal application transition {from_stage!r} -> {to_stage!r}")

    if to_stage == "Rejected" and not rejected_reason:
        raise ApplicationLifecycleError("rejected_reason is required when transitioning to Rejected")

    if to_stage in FEEDBACK_GATED_STAGES:
        feedback_interview_ids = {
            f.interview_id
            for f in session.execute(select(Feedback)).scalars()
        }
        missing = [
            iv.interview_id
            for iv in session.execute(
                select(Interview).where(
                    Interview.application_id == application_id, Interview.status == "Completed"
                )
            ).scalars()
            if iv.interview_id not in feedback_interview_ids
        ]
        if missing:
            raise ApplicationLifecycleError(
                f"cannot advance to {to_stage!r}: Completed interview(s) {missing} have no "
                "Feedback row (business_rules.md §6)"
            )

    now = changed_at or datetime.now()

    history = ApplicationStageHistory(
        history_id=_next_history_id(session),
        application_id=application_id,
        from_stage=from_stage,
        to_stage=to_stage,
        changed_at=now,
        actor_id=actor_id,
        reason_text=reason_text,
    )
    session.add(history)
    session.flush()

    application.stage = to_stage
    application.updated_at = now
    if to_stage == "Rejected":
        application.rejected_reason = rejected_reason
    if to_stage == "Withdrawn":
        application.withdrawn_at = now

    return history


def transition_application_stage(
    session: Session,
    application_id: str,
    to_stage: str,
    actor_id: str,
    changed_at: datetime | None = None,
    reason_text: str | None = None,
    rejected_reason: str | None = None,
) -> ApplicationStageHistory:
    """Executes one application-stage transition as one atomic
    transaction: validate the edge is legal, hard-enforce the
    missing-feedback gate for `Offer`/`Hired`, require `rejected_reason`
    for `Rejected`, insert the `ApplicationStageHistory` row, and update
    `Application.stage` (plus `rejected_reason`/`withdrawn_at` as needed).

    Raises `ApplicationLifecycleError` (after rolling back) for a missing
    application/actor, an illegal edge, a missing-feedback violation, or a
    missing `rejected_reason` — never partially commits.
    """
    try:
        history = _transition_application_stage_core(
            session, application_id, to_stage, actor_id, changed_at, reason_text, rejected_reason
        )
        session.commit()
        return history
    except Exception:
        session.rollback()
        raise


def withdraw(
    session: Session,
    application_id: str,
    actor_id: str,
    changed_at: datetime | None = None,
    reason_text: str | None = None,
) -> ApplicationStageHistory:
    """Convenience wrapper: candidate-initiated withdrawal from any
    non-terminal stage (business_rules.md §3)."""
    return transition_application_stage(session, application_id, "Withdrawn", actor_id, changed_at, reason_text)


def reject(
    session: Session,
    application_id: str,
    actor_id: str,
    rejected_reason: str,
    changed_at: datetime | None = None,
    reason_text: str | None = None,
) -> ApplicationStageHistory:
    """Convenience wrapper: recruiter-initiated rejection from `Screening`,
    `Interviewing`, or `Offer` (business_rules.md §3 — never directly from
    `Applied`)."""
    return transition_application_stage(
        session, application_id, "Rejected", actor_id, changed_at, reason_text, rejected_reason
    )
