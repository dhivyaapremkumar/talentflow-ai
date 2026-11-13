"""Offer schemas — data_dictionary.md §14."""

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


class OfferOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    offer_id: str
    application_id: str
    proposed_salary: int
    currency: str
    equity_amount: int | None
    status: str
    approved_by_actor_id: str | None
    approved_at: datetime | None
    extended_at: datetime | None
    decision_at: datetime | None
    expiry_date: date | None
    created_at: datetime


class OfferCreateIn(BaseModel):
    application_id: str
    proposed_salary: int
    currency: str = "USD"
    equity_amount: int | None = None


class OfferTransitionIn(BaseModel):
    to_status: str
    actor_id: str
    reason_text: str | None = None
    expiry_date: date | None = None
