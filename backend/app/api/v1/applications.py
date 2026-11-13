"""Application endpoints. Writes go through `services/
application_submission.py` and `services/screening.py` exclusively
(Phase 7) — this router never computes a screening score or a canonical-
attempt assignment itself; `services/application_lifecycle.py` (Phase 8)
owns stage transitions the same way."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.api.errors import NotFoundError
from app.db.models import Application, ApplicationSubmissionAttempt, Candidate, JobRequisition, ScreeningRun
from app.schemas.application import (
    ApplicationOutWithNames,
    ApplicationStageTransitionIn,
    ApplicationSubmitIn,
    ScreeningRunOut,
    SubmissionAttemptOut,
)
from app.schemas.common import Page
from app.services.application_lifecycle import transition_application_stage
from app.services.application_submission import submit_application
from app.services.screening import run_screening
from datetime import datetime

router = APIRouter(prefix="/applications", tags=["applications"])


def _with_names(app: Application, db: Session) -> ApplicationOutWithNames:
    candidate = db.get(Candidate, app.candidate_id)
    requisition = db.get(JobRequisition, app.requisition_id)
    data = ApplicationOutWithNames.model_validate(app)
    data.candidate_name = candidate.full_name if candidate else None
    data.requisition_title = requisition.title if requisition else None
    return data


@router.get("", response_model=Page[ApplicationOutWithNames])
def list_applications(
    requisition_id: str | None = None,
    candidate_id: str | None = None,
    stage: str | None = None,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    stmt = select(Application)
    count_stmt = select(func.count()).select_from(Application)
    for column, value in (
        (Application.requisition_id, requisition_id),
        (Application.candidate_id, candidate_id),
        (Application.stage, stage),
    ):
        if value is not None:
            stmt = stmt.where(column == value)
            count_stmt = count_stmt.where(column == value)
    total = db.execute(count_stmt).scalar_one()
    rows = db.execute(
        stmt.order_by(Application.application_id).limit(limit).offset(offset)
    ).scalars().all()
    return Page(items=[_with_names(r, db) for r in rows], total=total, limit=limit, offset=offset)


@router.get("/{application_id}", response_model=ApplicationOutWithNames)
def get_application(application_id: str, db: Session = Depends(get_db)):
    app_row = db.get(Application, application_id)
    if app_row is None:
        raise NotFoundError(f"Application {application_id!r} does not exist")
    return _with_names(app_row, db)


@router.get("/{application_id}/screening-runs", response_model=list[ScreeningRunOut])
def get_application_screening_runs(application_id: str, db: Session = Depends(get_db)):
    return db.execute(
        select(ScreeningRun)
        .where(ScreeningRun.application_id == application_id)
        .order_by(ScreeningRun.computed_at)
    ).scalars().all()


@router.get("/{application_id}/attempts", response_model=list[SubmissionAttemptOut])
def get_application_attempts(application_id: str, db: Session = Depends(get_db)):
    return db.execute(
        select(ApplicationSubmissionAttempt)
        .where(ApplicationSubmissionAttempt.canonical_application_id == application_id)
        .order_by(ApplicationSubmissionAttempt.submitted_at)
    ).scalars().all()


@router.post("", response_model=ApplicationOutWithNames, status_code=201)
def submit_application_endpoint(body: ApplicationSubmitIn, db: Session = Depends(get_db)):
    submit_application(
        db, body.candidate_id, body.requisition_id, datetime.now(), resume_artifact_id=body.resume_artifact_id
    )
    app_id = f"APP-{body.requisition_id}-{body.candidate_id}"
    return _with_names(db.get(Application, app_id), db)


@router.post("/{application_id}/screen", response_model=ApplicationOutWithNames)
def screen_application_endpoint(application_id: str, db: Session = Depends(get_db)):
    if db.get(Application, application_id) is None:
        raise NotFoundError(f"Application {application_id!r} does not exist")
    run_screening(db, application_id)
    return _with_names(db.get(Application, application_id), db)


@router.post("/{application_id}/transition", response_model=ApplicationOutWithNames)
def transition_application_endpoint(
    application_id: str, body: ApplicationStageTransitionIn, db: Session = Depends(get_db)
):
    if db.get(Application, application_id) is None:
        raise NotFoundError(f"Application {application_id!r} does not exist")
    transition_application_stage(
        db,
        application_id,
        body.to_stage,
        body.actor_id,
        reason_text=body.reason_text,
        rejected_reason=body.rejected_reason,
    )
    return _with_names(db.get(Application, application_id), db)
