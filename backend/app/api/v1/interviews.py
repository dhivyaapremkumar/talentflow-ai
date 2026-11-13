"""Interview/Feedback endpoints. Writes go through `services/
scheduling.py` exclusively (Phase 8) — this router never computes a
scheduling-conflict check or a feedback-eligibility check itself."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.api.errors import NotFoundError
from app.db.models import Feedback, Interview, InterviewerAvailabilitySlot
from app.schemas.common import Page
from app.schemas.interview import (
    FeedbackOut,
    FeedbackSubmitIn,
    InterviewOut,
    InterviewScheduleIn,
    InterviewStatusTransitionIn,
)
from app.schemas.reference import AvailabilitySlotOut
from app.services.scheduling import schedule_interview, submit_feedback, transition_interview_status

router = APIRouter(prefix="/interviews", tags=["interviews"])


@router.get("", response_model=Page[InterviewOut])
def list_interviews(
    application_id: str | None = None,
    interviewer_id: str | None = None,
    status: str | None = None,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    stmt = select(Interview)
    count_stmt = select(func.count()).select_from(Interview)
    for column, value in (
        (Interview.application_id, application_id),
        (Interview.interviewer_id, interviewer_id),
        (Interview.status, status),
    ):
        if value is not None:
            stmt = stmt.where(column == value)
            count_stmt = count_stmt.where(column == value)
    total = db.execute(count_stmt).scalar_one()
    rows = db.execute(
        stmt.order_by(Interview.scheduled_start).limit(limit).offset(offset)
    ).scalars().all()
    return Page(items=rows, total=total, limit=limit, offset=offset)


@router.get("/{interview_id}", response_model=InterviewOut)
def get_interview(interview_id: str, db: Session = Depends(get_db)):
    interview = db.get(Interview, interview_id)
    if interview is None:
        raise NotFoundError(f"Interview {interview_id!r} does not exist")
    return interview


@router.get("/{interview_id}/feedback", response_model=FeedbackOut | None)
def get_interview_feedback(interview_id: str, db: Session = Depends(get_db)):
    return db.execute(select(Feedback).where(Feedback.interview_id == interview_id)).scalars().first()


@router.post("", response_model=InterviewOut, status_code=201)
def schedule_interview_endpoint(body: InterviewScheduleIn, db: Session = Depends(get_db)):
    interview = schedule_interview(
        db,
        body.application_id,
        body.interviewer_id,
        body.round_type,
        body.scheduled_start,
        body.scheduled_end,
        body.location_mode,
    )
    return interview


@router.post("/{interview_id}/status", response_model=InterviewOut)
def transition_interview_status_endpoint(
    interview_id: str, body: InterviewStatusTransitionIn, db: Session = Depends(get_db)
):
    return transition_interview_status(db, interview_id, body.to_status)


@router.post("/{interview_id}/feedback", response_model=FeedbackOut, status_code=201)
def submit_feedback_endpoint(interview_id: str, body: FeedbackSubmitIn, db: Session = Depends(get_db)):
    return submit_feedback(
        db,
        interview_id,
        body.interviewer_id,
        body.recommendation,
        body.overall_score,
        body.submitted_at,
        strengths_text=body.strengths_text,
        concerns_text=body.concerns_text,
    )


@router.get("/availability/{interviewer_id}", response_model=list[AvailabilitySlotOut])
def get_interviewer_availability(interviewer_id: str, db: Session = Depends(get_db)):
    return db.execute(
        select(InterviewerAvailabilitySlot)
        .where(InterviewerAvailabilitySlot.interviewer_id == interviewer_id)
        .order_by(InterviewerAvailabilitySlot.start_datetime)
    ).scalars().all()
