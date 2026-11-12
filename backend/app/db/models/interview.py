"""Interviewer, InterviewerAvailabilitySlot — data_dictionary.md §10/§11.

`Interview` and `Feedback` are added to this module in a later Phase 2 unit,
once `Application` exists (they FK to it) — kept out for now so this unit has
no forward dependency on a table that doesn't exist yet. `Interviewer` is
deliberately separate from `SystemActor` (entity_relationships.md §4).
"""

from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


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
