"""JobRequisition endpoints. Writes go through `services/
requisition_lifecycle.py` exclusively (architecture.md §6) — this router
never constructs a status change itself."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.api.errors import NotFoundError
from app.db.models import JobRequisition
from app.schemas.common import Page
from app.schemas.requisition import RequisitionOut, RequisitionTransitionIn
from app.services.requisition_lifecycle import transition_requisition

router = APIRouter(prefix="/requisitions", tags=["requisitions"])


@router.get("", response_model=Page[RequisitionOut])
def list_requisitions(
    status: str | None = None,
    department_id: str | None = None,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    stmt = select(JobRequisition)
    count_stmt = select(func.count()).select_from(JobRequisition)
    if status is not None:
        stmt = stmt.where(JobRequisition.status == status)
        count_stmt = count_stmt.where(JobRequisition.status == status)
    if department_id is not None:
        stmt = stmt.where(JobRequisition.department_id == department_id)
        count_stmt = count_stmt.where(JobRequisition.department_id == department_id)
    total = db.execute(count_stmt).scalar_one()
    rows = db.execute(stmt.order_by(JobRequisition.requisition_id).limit(limit).offset(offset)).scalars().all()
    return Page(items=rows, total=total, limit=limit, offset=offset)


@router.get("/{requisition_id}", response_model=RequisitionOut)
def get_requisition(requisition_id: str, db: Session = Depends(get_db)):
    req = db.get(JobRequisition, requisition_id)
    if req is None:
        raise NotFoundError(f"JobRequisition {requisition_id!r} does not exist")
    return req


@router.post("/{requisition_id}/transition", response_model=RequisitionOut)
def transition_requisition_endpoint(
    requisition_id: str, body: RequisitionTransitionIn, db: Session = Depends(get_db)
):
    if db.get(JobRequisition, requisition_id) is None:
        raise NotFoundError(f"JobRequisition {requisition_id!r} does not exist")
    transition_requisition(db, requisition_id, body.to_status, body.actor_id, reason_text=body.reason_text)
    return db.get(JobRequisition, requisition_id)
