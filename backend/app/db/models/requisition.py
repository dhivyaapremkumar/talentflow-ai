"""JobRequisition, JobRequisitionSkill — data_dictionary.md §2/§4.

Note on `JobRequisitionSkill.weight_pct`: the rule "weights across a
requisition's skills sum to 100" spans *multiple rows* (one per required
skill), so it cannot be expressed as a single-row SQLite CHECK constraint —
it is a business-rule validation concern (VAL-03/VAL-12), implemented in
Phase 4, not here. Only the per-row `0 <= weight_pct <= 100` bound is a
structural constraint.
"""

from datetime import date, datetime

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, Enum, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.enums import PROFICIENCY_LEVELS

REQUISITION_LEVELS = ("Junior", "Mid", "Senior", "Lead", "Principal")
EMPLOYMENT_TYPES = ("FullTime", "Contract", "Intern")
REQUISITION_STATUSES = (
    "Draft",
    "PendingApproval",
    "Approved",
    "Open",
    "OnHold",
    "Closed",
    "Cancelled",
)


class JobRequisition(Base):
    __tablename__ = "job_requisition"
    __table_args__ = (
        CheckConstraint(
            "requisition_id GLOB 'REQ-[0-9][0-9][0-9][0-9][0-9]'", name="ck_requisition_id_format"
        ),
        CheckConstraint("salary_min >= 0", name="ck_requisition_salary_min_nonneg"),
        CheckConstraint("salary_max >= salary_min", name="ck_requisition_salary_max_gte_min"),
        CheckConstraint("headcount >= 1", name="ck_requisition_headcount_positive"),
    )

    requisition_id: Mapped[str] = mapped_column(String(20), primary_key=True)
    department_id: Mapped[str] = mapped_column(
        String(20), ForeignKey("department.department_id"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    level: Mapped[str] = mapped_column(
        Enum(*REQUISITION_LEVELS, name="requisition_level", create_constraint=True), nullable=False
    )
    employment_type: Mapped[str] = mapped_column(
        Enum(*EMPLOYMENT_TYPES, name="employment_type", create_constraint=True), nullable=False
    )
    status: Mapped[str] = mapped_column(
        Enum(*REQUISITION_STATUSES, name="requisition_status", create_constraint=True), nullable=False
    )
    salary_min: Mapped[int] = mapped_column(Integer, nullable=False)
    salary_max: Mapped[int] = mapped_column(Integer, nullable=False)
    headcount: Mapped[int] = mapped_column(Integer, nullable=False)
    requested_by_actor_id: Mapped[str] = mapped_column(
        String(20), ForeignKey("system_actor.actor_id"), nullable=False
    )
    opened_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    target_close_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    closed_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class JobRequisitionSkill(Base):
    __tablename__ = "job_requisition_skill"
    __table_args__ = (
        CheckConstraint("weight_pct >= 0 AND weight_pct <= 100", name="ck_jrs_weight_pct_bounds"),
    )

    requisition_id: Mapped[str] = mapped_column(
        String(20), ForeignKey("job_requisition.requisition_id"), primary_key=True
    )
    skill_id: Mapped[str] = mapped_column(String(20), ForeignKey("skill.skill_id"), primary_key=True)
    min_proficiency_level: Mapped[str] = mapped_column(
        Enum(*PROFICIENCY_LEVELS, name="jrs_min_proficiency_level", create_constraint=True),
        nullable=False,
    )
    is_mandatory: Mapped[bool] = mapped_column(Boolean, nullable=False)
    weight_pct: Mapped[int] = mapped_column(Integer, nullable=False)
