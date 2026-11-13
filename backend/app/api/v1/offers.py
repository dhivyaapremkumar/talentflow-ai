"""Offer endpoints. Writes go through `services/offer_lifecycle.py`
exclusively (Phase 8) — this router never evaluates the salary band or
the APPROVER gate itself; a non-APPROVER transition attempt on
`PendingApproval->Approved` is rejected by the service and surfaces here
as `code="role_not_permitted"` (see `api/errors.py`)."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.api.errors import NotFoundError
from app.db.models import Offer
from app.schemas.common import Page
from app.schemas.offer import OfferCreateIn, OfferOut, OfferTransitionIn
from app.services.offer_lifecycle import create_offer, transition_offer

router = APIRouter(prefix="/offers", tags=["offers"])


@router.get("", response_model=Page[OfferOut])
def list_offers(
    status: str | None = None,
    application_id: str | None = None,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    stmt = select(Offer)
    count_stmt = select(func.count()).select_from(Offer)
    for column, value in ((Offer.status, status), (Offer.application_id, application_id)):
        if value is not None:
            stmt = stmt.where(column == value)
            count_stmt = count_stmt.where(column == value)
    total = db.execute(count_stmt).scalar_one()
    rows = db.execute(stmt.order_by(Offer.offer_id).limit(limit).offset(offset)).scalars().all()
    return Page(items=rows, total=total, limit=limit, offset=offset)


@router.get("/{offer_id}", response_model=OfferOut)
def get_offer(offer_id: str, db: Session = Depends(get_db)):
    offer = db.get(Offer, offer_id)
    if offer is None:
        raise NotFoundError(f"Offer {offer_id!r} does not exist")
    return offer


@router.post("", response_model=OfferOut, status_code=201)
def create_offer_endpoint(body: OfferCreateIn, db: Session = Depends(get_db)):
    return create_offer(
        db, body.application_id, body.proposed_salary, currency=body.currency, equity_amount=body.equity_amount
    )


@router.post("/{offer_id}/transition", response_model=OfferOut)
def transition_offer_endpoint(offer_id: str, body: OfferTransitionIn, db: Session = Depends(get_db)):
    if db.get(Offer, offer_id) is None:
        raise NotFoundError(f"Offer {offer_id!r} does not exist")
    transition_offer(
        db, offer_id, body.to_status, body.actor_id, reason_text=body.reason_text, expiry_date=body.expiry_date
    )
    return db.get(Offer, offer_id)
