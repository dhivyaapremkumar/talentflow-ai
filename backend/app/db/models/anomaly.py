"""AnomalyLabel — data_dictionary.md §16. Ground truth, isolated, never a
feature (architecture.md §5) — this table exists purely for the offline
detection-accuracy evaluation step; no detector or screening/workflow logic
may read it.

`entity_id`/`related_entity_id` are "FK by convention, not a DB FK" per the
spec — `entity_type` varies across rows (Interview, ApplicationSubmission
Attempt, Application, Offer), so a single real FOREIGN KEY column can't
target four different tables. Referential existence for these is therefore
a Phase 4 validation concern, not a structural one, same as every other
deferral in this package.
"""

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Enum, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

ANOMALY_ENTITY_TYPES = ("Interview", "ApplicationSubmissionAttempt", "Application", "Offer")
ANOMALY_TYPES = (
    "UnavailableInterviewer",
    "DuplicateApplication",
    "MissingFeedbackStageAdvanced",
    "SalaryOutsideBand",
    "ClosedReqActiveApplications",
)


class AnomalyLabel(Base):
    __tablename__ = "anomaly_label"
    __table_args__ = (
        CheckConstraint("label_id GLOB 'ANOM-[0-9][0-9][0-9][0-9]'", name="ck_anomaly_label_id_format"),
    )

    label_id: Mapped[str] = mapped_column(String(20), primary_key=True)
    entity_type: Mapped[str] = mapped_column(
        Enum(*ANOMALY_ENTITY_TYPES, name="anomaly_entity_type", create_constraint=True), nullable=False
    )
    entity_id: Mapped[str] = mapped_column(String(40), nullable=False)
    anomaly_type: Mapped[str] = mapped_column(
        Enum(*ANOMALY_TYPES, name="anomaly_type", create_constraint=True), nullable=False
    )
    related_entity_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    injected_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    description: Mapped[str] = mapped_column(String(200), nullable=False)
