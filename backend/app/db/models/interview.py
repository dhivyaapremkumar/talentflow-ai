"""Interviewer, InterviewerAvailabilitySlot, Interview, Feedback —
data_dictionary.md §10/§11/§12/§13.

`Interviewer` is deliberately separate from `SystemActor`
(entity_relationships.md §4).

Cross-table rules deferred to the Phase 4 validation engine (same category
as every other such deferral in this package — SQLite CHECK constraints
cannot reference another table's column): `round_number` contiguity per
application; `scheduled_start >= Application.screening_computed_at`;
`Feedback.interviewer_id == Interview.interviewer_id`;
`Feedback.submitted_at >= Interview.scheduled_end`; and "a `Feedback` row
may only exist once its `Interview.status = 'Completed'`" (the 10 seeded
missing-feedback anomalies rely on this *not* being a DB-level constraint —
business_rules.md §9).
"""

from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, Enum, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

INTERVIEW_ROUND_TYPES = ("Phone", "Technical", "Onsite", "Panel", "HiringManager")
INTERVIEW_STATUSES = ("Scheduled", "Completed", "Cancelled", "NoShow")
INTERVIEW_LOCATION_MODES = ("Remote", "Onsite")
FEEDBACK_RECOMMENDATIONS = ("StrongYes", "Yes", "No", "StrongNo")


class Interviewer(Base):
    __tablename__ = "interviewer"
    __table_args__ = (
        CheckConstraint("interviewer_id GLOB 'IVR-[0-9][0-9][0-9][0-9]'", name="ck_interviewer_id_format"),
    )

    interviewer_id: Mapped[str] = mapped_column(String(20), primary_key=True)
    full_name: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    department_id: Mapped[str] = mapped_column(
        String(20), ForeignKey("department.department_id"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(80), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class InterviewerAvailabilitySlot(Base):
    __tablename__ = "interviewer_availability_slot"
    __table_args__ = (
        CheckConstraint(
            "slot_id GLOB 'AVAIL-[0-9][0-9][0-9][0-9][0-9][0-9]'", name="ck_slot_id_format"
        ),
        CheckConstraint("start_datetime < end_datetime", name="ck_slot_start_before_end"),
    )

    slot_id: Mapped[str] = mapped_column(String(20), primary_key=True)
    interviewer_id: Mapped[str] = mapped_column(
        String(20), ForeignKey("interviewer.interviewer_id"), nullable=False
    )
    start_datetime: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    end_datetime: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    is_booked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class Interview(Base):
    __tablename__ = "interview"
    __table_args__ = (
        CheckConstraint(
            "interview_id GLOB 'IVW-[0-9][0-9][0-9][0-9][0-9][0-9]'", name="ck_interview_id_format"
        ),
        CheckConstraint("round_number >= 1", name="ck_interview_round_number_positive"),
        CheckConstraint("scheduled_start < scheduled_end", name="ck_interview_start_before_end"),
        CheckConstraint("created_at <= scheduled_start", name="ck_interview_created_before_scheduled"),
        CheckConstraint("updated_at >= created_at", name="ck_interview_updated_after_created"),
    )

    interview_id: Mapped[str] = mapped_column(String(20), primary_key=True)
    application_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("application.application_id"), nullable=False
    )
    interviewer_id: Mapped[str] = mapped_column(
        String(20), ForeignKey("interviewer.interviewer_id"), nullable=False
    )
    round_number: Mapped[int] = mapped_column(Integer, nullable=False)
    round_type: Mapped[str] = mapped_column(
        Enum(*INTERVIEW_ROUND_TYPES, name="interview_round_type", create_constraint=True),
        nullable=False,
    )
    scheduled_start: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    scheduled_end: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    status: Mapped[str] = mapped_column(
        Enum(*INTERVIEW_STATUSES, name="interview_status", create_constraint=True), nullable=False
    )
    location_mode: Mapped[str] = mapped_column(
        Enum(*INTERVIEW_LOCATION_MODES, name="interview_location_mode", create_constraint=True),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class Feedback(Base):
    __tablename__ = "feedback"
    __table_args__ = (
        CheckConstraint(
            "feedback_id GLOB 'FBK-[0-9][0-9][0-9][0-9][0-9][0-9]'", name="ck_feedback_id_format"
        ),
        CheckConstraint(
            "overall_score >= 1 AND overall_score <= 5", name="ck_feedback_overall_score_bounds"
        ),
    )

    feedback_id: Mapped[str] = mapped_column(String(20), primary_key=True)
    interview_id: Mapped[str] = mapped_column(
        String(20), ForeignKey("interview.interview_id"), unique=True, nullable=False
    )
    interviewer_id: Mapped[str] = mapped_column(
        String(20), ForeignKey("interviewer.interviewer_id"), nullable=False
    )
    recommendation: Mapped[str] = mapped_column(
        Enum(*FEEDBACK_RECOMMENDATIONS, name="feedback_recommendation", create_constraint=True),
        nullable=False,
    )
    overall_score: Mapped[int] = mapped_column(Integer, nullable=False)
    strengths_text: Mapped[str | None] = mapped_column(String(500), nullable=True)
    concerns_text: Mapped[str | None] = mapped_column(String(500), nullable=True)
    submitted_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
