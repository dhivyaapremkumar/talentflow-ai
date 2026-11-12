"""Offer — data_dictionary.md §14.

The salary-band check ("offer salary outside approved band") is deliberately
*not* a DB CHECK constraint — the dataset must be able to represent the 6
seeded salary-out-of-band anomalies, so this is a Phase 4 validation rule
(business_rules.md §7), not a structural one. `Offer` reaches the band via
`application_id -> Application.requisition_id -> JobRequisition.salary_min/
max`, a cross-table path, which is itself another reason this can't be a
same-table CHECK.

The required-iff-status CHECKs below follow the same "required-if" (one
direction only) convention already used by `Application.rejected_reason`/
`withdrawn_at` — they assert the field must be present once status reaches
the relevant set, not that it must be absent before then.
"""

from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, DateTime, Enum, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

OFFER_CURRENCIES = ("USD",)
OFFER_STATUSES = (
    "Drafted",
    "PendingApproval",
    "Approved",
    "Extended",
    "Accepted",
    "Declined",
    "Rescinded",
    "Expired",
)


class Offer(Base):
    __tablename__ = "offer"
    __table_args__ = (
        CheckConstraint("offer_id GLOB 'OFR-[0-9][0-9][0-9][0-9][0-9]'", name="ck_offer_id_format"),
        CheckConstraint("proposed_salary >= 0", name="ck_offer_proposed_salary_nonneg"),
        CheckConstraint(
            "equity_amount IS NULL OR equity_amount >= 0", name="ck_offer_equity_amount_nonneg"
        ),
        CheckConstraint(
            "status NOT IN ('Approved', 'Extended', 'Accepted') OR "
            "(approved_by_actor_id IS NOT NULL AND approved_at IS NOT NULL)",
            name="ck_offer_approval_fields_required",
        ),
        CheckConstraint(
            "status NOT IN ('Extended', 'Accepted', 'Declined') OR extended_at IS NOT NULL",
            name="ck_offer_extended_at_required",
        ),
        CheckConstraint(
            "extended_at IS NULL OR approved_at IS NULL OR extended_at >= approved_at",
            name="ck_offer_extended_after_approved",
        ),
        CheckConstraint(
            "status NOT IN ('Accepted', 'Declined') OR decision_at IS NOT NULL",
            name="ck_offer_decision_at_required",
        ),
        CheckConstraint(
            "decision_at IS NULL OR extended_at IS NULL OR decision_at >= extended_at",
            name="ck_offer_decision_after_extended",
        ),
        CheckConstraint(
            "expiry_date IS NULL OR extended_at IS NULL OR DATE(expiry_date) >= DATE(extended_at)",
            name="ck_offer_expiry_after_extended",
        ),
    )

    offer_id: Mapped[str] = mapped_column(String(20), primary_key=True)
    application_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("application.application_id"), unique=True, nullable=False
    )
    proposed_salary: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(
        Enum(*OFFER_CURRENCIES, name="offer_currency", create_constraint=True), nullable=False
    )
    equity_amount: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(
        Enum(*OFFER_STATUSES, name="offer_status", create_constraint=True), nullable=False
    )
    approved_by_actor_id: Mapped[str | None] = mapped_column(
        String(20), ForeignKey("system_actor.actor_id"), nullable=True
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    extended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    decision_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    expiry_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
