"""RequisitionStatusHistory, ApplicationStageHistory, OfferStatusHistory —
data_dictionary.md §15a/§15b/§15c. The three immutable, append-only event-
history tables (entity_relationships.md §4a — the hard limit this project
set on history tables; `ScreeningRun`/`ApplicationSubmissionAttempt`/
`Interview`/`Feedback` are a different category, repeatable-event-with-a-
result, not from/to transition logs).

Cross-row rules deferred to Phase 4 (same category as every other such
deferral in this package): `changed_at` strictly increasing per parent
entity, and "`to_status`/`to_stage` must be a legal transition from
`from_status`/`from_stage`" (business_rules.md §2/§3 — needs the full
transition graph, not expressible as a single-row CHECK). Each table's
from-column is nullable only for that entity's first history row; that
"nullable for the first row only" rule is also cross-row (depends on
whether earlier rows exist for the same parent id) and so is likewise
deferred.
"""

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Enum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.application import APPLICATION_STAGES
from app.db.models.offer import OFFER_STATUSES
from app.db.models.requisition import REQUISITION_STATUSES


class RequisitionStatusHistory(Base):
    __tablename__ = "requisition_status_history"
    __table_args__ = (
        CheckConstraint(
            "history_id GLOB 'RQH-[0-9][0-9][0-9][0-9][0-9][0-9]'", name="ck_rqh_id_format"
        ),
    )

    history_id: Mapped[str] = mapped_column(String(20), primary_key=True)
    requisition_id: Mapped[str] = mapped_column(
        String(20), ForeignKey("job_requisition.requisition_id"), nullable=False
    )
    from_status: Mapped[str | None] = mapped_column(
        Enum(*REQUISITION_STATUSES, name="rqh_from_status", create_constraint=True), nullable=True
    )
    to_status: Mapped[str] = mapped_column(
        Enum(*REQUISITION_STATUSES, name="rqh_to_status", create_constraint=True), nullable=False
    )
    changed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    actor_id: Mapped[str] = mapped_column(
        String(20), ForeignKey("system_actor.actor_id"), nullable=False
    )
    reason_text: Mapped[str | None] = mapped_column(String(200), nullable=True)


class ApplicationStageHistory(Base):
    __tablename__ = "application_stage_history"
    __table_args__ = (
        CheckConstraint(
            "history_id GLOB 'APH-[0-9][0-9][0-9][0-9][0-9][0-9]'", name="ck_aph_id_format"
        ),
    )

    history_id: Mapped[str] = mapped_column(String(20), primary_key=True)
    application_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("application.application_id"), nullable=False
    )
    from_stage: Mapped[str | None] = mapped_column(
        Enum(*APPLICATION_STAGES, name="aph_from_stage", create_constraint=True), nullable=True
    )
    to_stage: Mapped[str] = mapped_column(
        Enum(*APPLICATION_STAGES, name="aph_to_stage", create_constraint=True), nullable=False
    )
    changed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    actor_id: Mapped[str] = mapped_column(
        String(20), ForeignKey("system_actor.actor_id"), nullable=False
    )
    reason_text: Mapped[str | None] = mapped_column(String(200), nullable=True)


class OfferStatusHistory(Base):
    __tablename__ = "offer_status_history"
    __table_args__ = (
        CheckConstraint(
            "history_id GLOB 'OFH-[0-9][0-9][0-9][0-9][0-9][0-9]'", name="ck_ofh_id_format"
        ),
    )

    history_id: Mapped[str] = mapped_column(String(20), primary_key=True)
    offer_id: Mapped[str] = mapped_column(String(20), ForeignKey("offer.offer_id"), nullable=False)
    from_status: Mapped[str | None] = mapped_column(
        Enum(*OFFER_STATUSES, name="ofh_from_status", create_constraint=True), nullable=True
    )
    to_status: Mapped[str] = mapped_column(
        Enum(*OFFER_STATUSES, name="ofh_to_status", create_constraint=True), nullable=False
    )
    changed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    actor_id: Mapped[str] = mapped_column(
        String(20), ForeignKey("system_actor.actor_id"), nullable=False
    )
    reason_text: Mapped[str | None] = mapped_column(String(200), nullable=True)
