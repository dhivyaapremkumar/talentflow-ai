"""The live interview-scheduling service — Phase 8,
implementation_plan.md's Phase 8 row: `services/scheduling.py`.

Implements the exact containment/overlap algorithm
`validation/rules/scheduling_conflicts.py` audits the generated dataset
against (data_dictionary.md §11: "a scheduling conflict exists when an
Interview's scheduled_start/end for an interviewer does not fall fully
inside one of that interviewer's InterviewerAvailabilitySlot windows, or
overlaps a window already booked by another Interview") — but as a
**pre-insert gate** over one candidate interview, not a post-hoc audit
over the whole dataset, so the algorithm is necessarily written fresh
here rather than imported; the containment/overlap *logic* is identical,
not reimplemented differently (architecture.md §6's reuse principle is
about not letting the formula drift, not about forcing a read-only
auditor and a write-path gate to share one function signature when their
inputs genuinely differ — one row-under-consideration vs. every row on
file).

**Deliberate difference from the read-only auditor, flagged, not
silent:** the auditor's overlap check considers every `Interview` row
regardless of `status`, because it is reviewing historical data for audit
purposes. This live scheduling gate excludes `status = "Cancelled"`
interviews from the overlap check — a cancelled interview no longer
occupies the interviewer's time, so a live caller should be able to book
that freed slot. `NoShow`/`Completed` interviews still count (the
interview actually happened at that time).

**Feedback submission lives here, not in a separate module:**
`application_lifecycle.py`/`offer_lifecycle.py`/`requisition_lifecycle.py`
are the four Phase 8 files named in the approved plan; `Feedback` is
structurally an interview-scheduling concern (data_dictionary.md §13:
`Feedback.interviewer_id` must equal `Interview.interviewer_id`, and a
`Feedback` row may only exist once `Interview.status = "Completed"`), so
`submit_feedback()` is colocated with the rest of this module's
Interview-related logic rather than inventing a fifth service file.

**No `InterviewStatusHistory` table exists** (`entity_relationships.md`
§4a caps the from/to history category at exactly three tables) —
`Interview` is a repeatable-event-with-a-result entity, same category as
`ScreeningRun`/`ApplicationSubmissionAttempt`; `transition_interview_
status()` below updates `Interview.status` directly with no history row,
matching that documented design, not an omission.
"""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    Application,
    Feedback,
    Interview,
    Interviewer,
    InterviewerAvailabilitySlot,
)

INTERVIEW_LEGAL_STATUS_EDGES = {
    ("Scheduled", "Completed"),
    ("Scheduled", "Cancelled"),
    ("Scheduled", "NoShow"),
}
NON_OCCUPYING_STATUSES = {"Cancelled"}


class SchedulingError(Exception):
    """Raised when scheduling/feedback submission cannot proceed — the
    service rolls back the session before raising, so the caller is
    never left mid-transaction."""


def _next_interview_id(session: Session) -> str:
    existing = session.execute(select(Interview.interview_id)).scalars().all()
    nums = [int(v.split("-")[1]) for v in existing]
    next_num = (max(nums) + 1) if nums else 1
    return f"IVW-{next_num:06d}"


def _next_feedback_id(session: Session) -> str:
    existing = session.execute(select(Feedback.feedback_id)).scalars().all()
    nums = [int(v.split("-")[1]) for v in existing]
    next_num = (max(nums) + 1) if nums else 1
    return f"FBK-{next_num:06d}"


def schedule_interview(
    session: Session,
    application_id: str,
    interviewer_id: str,
    round_type: str,
    scheduled_start: datetime,
    scheduled_end: datetime,
    location_mode: str,
    created_at: datetime | None = None,
) -> Interview:
    """Schedules one interview round as one atomic transaction:

    1. The application must be at stage `Interviewing` (workflow.md §4 —
       scheduling only happens "for each Interviewing-stage application").
    2. `round_number` is assigned as the next contiguous number for the
       application (count of existing rounds + 1).
    3. The window must fall fully inside one of the interviewer's open
       `InterviewerAvailabilitySlot` windows, and must not overlap another
       non-cancelled `Interview` already booked for that interviewer.
    4. The containing slot's `is_booked` is set `True`.

    Raises `SchedulingError` (after rolling back) for a missing
    application/interviewer, a wrong application stage, an inactive
    interviewer, an invalid window, or a scheduling conflict — never
    partially commits.
    """
    try:
        application = session.get(Application, application_id)
        if application is None:
            raise SchedulingError(f"Application {application_id!r} does not exist")
        if application.stage != "Interviewing":
            raise SchedulingError(
                f"Application {application_id!r} is at stage {application.stage!r}, "
                "not 'Interviewing' (workflow.md §4)"
            )

        interviewer = session.get(Interviewer, interviewer_id)
        if interviewer is None:
            raise SchedulingError(f"Interviewer {interviewer_id!r} does not exist")
        if not interviewer.is_active:
            raise SchedulingError(f"Interviewer {interviewer_id!r} is not active")

        if scheduled_start >= scheduled_end:
            raise SchedulingError("scheduled_start must be before scheduled_end")
        if application.screening_computed_at is not None and scheduled_start < application.screening_computed_at:
            raise SchedulingError(
                "scheduled_start must be >= Application.screening_computed_at (data_dictionary.md §12)"
            )

        now = created_at or datetime.now()
        if now > scheduled_start:
            raise SchedulingError("created_at must be <= scheduled_start")

        slots = session.execute(
            select(InterviewerAvailabilitySlot).where(
                InterviewerAvailabilitySlot.interviewer_id == interviewer_id
            )
        ).scalars().all()
        containing_slot = next(
            (
                slot
                for slot in slots
                if slot.start_datetime <= scheduled_start and scheduled_end <= slot.end_datetime
            ),
            None,
        )
        if containing_slot is None:
            raise SchedulingError(
                f"[{scheduled_start}, {scheduled_end}) is not fully contained in any "
                f"availability slot for interviewer {interviewer_id!r}"
            )

        other_interviews = session.execute(
            select(Interview).where(Interview.interviewer_id == interviewer_id)
        ).scalars().all()
        for iv in other_interviews:
            if iv.status in NON_OCCUPYING_STATUSES:
                continue
            if scheduled_start < iv.scheduled_end and iv.scheduled_start < scheduled_end:
                raise SchedulingError(
                    f"[{scheduled_start}, {scheduled_end}) overlaps existing interview "
                    f"{iv.interview_id} [{iv.scheduled_start}, {iv.scheduled_end}) for the same "
                    f"interviewer ({interviewer_id})"
                )

        round_number = session.execute(
            select(Interview).where(Interview.application_id == application_id)
        ).scalars().all()
        round_number = len(round_number) + 1

        interview = Interview(
            interview_id=_next_interview_id(session),
            application_id=application_id,
            interviewer_id=interviewer_id,
            round_number=round_number,
            round_type=round_type,
            scheduled_start=scheduled_start,
            scheduled_end=scheduled_end,
            status="Scheduled",
            location_mode=location_mode,
            created_at=now,
            updated_at=now,
        )
        session.add(interview)
        session.flush()

        containing_slot.is_booked = True

        session.commit()
        return interview
    except Exception:
        session.rollback()
        raise


def transition_interview_status(
    session: Session, interview_id: str, to_status: str, updated_at: datetime | None = None
) -> Interview:
    """Transitions `Interview.status`: `Scheduled -> Completed/Cancelled/
    NoShow` — all three terminal (business_rules.md §3). No history row is
    written (see module docstring)."""
    try:
        interview = session.get(Interview, interview_id)
        if interview is None:
            raise SchedulingError(f"Interview {interview_id!r} does not exist")

        edge = (interview.status, to_status)
        if edge not in INTERVIEW_LEGAL_STATUS_EDGES:
            raise SchedulingError(f"illegal interview status transition {edge[0]!r} -> {edge[1]!r}")

        interview.status = to_status
        interview.updated_at = updated_at or datetime.now()

        session.commit()
        return interview
    except Exception:
        session.rollback()
        raise


def submit_feedback(
    session: Session,
    interview_id: str,
    interviewer_id: str,
    recommendation: str,
    overall_score: int,
    submitted_at: datetime,
    strengths_text: str | None = None,
    concerns_text: str | None = None,
) -> Feedback:
    """Records one `Feedback` row as one atomic transaction.

    Raises `SchedulingError` (after rolling back) if the interview does
    not exist, is not `Completed`, already has a `Feedback` row (1:1,
    data_dictionary.md §13), `interviewer_id` does not equal
    `Interview.interviewer_id` (the structural FK-equality gate,
    business_rules.md §11's note that feedback is not role-gated), or
    `submitted_at` precedes `scheduled_end`.
    """
    try:
        interview = session.get(Interview, interview_id)
        if interview is None:
            raise SchedulingError(f"Interview {interview_id!r} does not exist")
        if interview.status != "Completed":
            raise SchedulingError(
                f"Interview {interview_id!r} is {interview.status!r}, not 'Completed' "
                "(data_dictionary.md §13)"
            )
        if interviewer_id != interview.interviewer_id:
            raise SchedulingError(
                f"Feedback.interviewer_id {interviewer_id!r} must equal Interview.interviewer_id "
                f"{interview.interviewer_id!r} (data_dictionary.md §13)"
            )
        if submitted_at < interview.scheduled_end:
            raise SchedulingError("submitted_at must be >= Interview.scheduled_end")

        existing = session.execute(
            select(Feedback).where(Feedback.interview_id == interview_id)
        ).scalars().first()
        if existing is not None:
            raise SchedulingError(f"Interview {interview_id!r} already has a Feedback row")

        feedback = Feedback(
            feedback_id=_next_feedback_id(session),
            interview_id=interview_id,
            interviewer_id=interviewer_id,
            recommendation=recommendation,
            overall_score=overall_score,
            strengths_text=strengths_text,
            concerns_text=concerns_text,
            submitted_at=submitted_at,
        )
        session.add(feedback)

        session.commit()
        return feedback
    except Exception:
        session.rollback()
        raise
