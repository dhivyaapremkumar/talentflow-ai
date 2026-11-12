"""ScreeningRule — data_dictionary.md §9. Versioned/insert-only, three-weight
model (APPROVED, business_rules.md §5 — Skill 50 / Experience 30 / Education
20, default pass_threshold_score=70.0).

`ScreeningRun` is added to this module in a later Phase 2 unit, once
`Application` exists (it FKs to it).

The `uq_screeningrule_current` partial unique index is the structural
backstop for "at most one is_current=true row per requisition" — SQLite
supports partial unique indexes natively via `sqlite_where`.
"""

from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.enums import EDUCATION_LEVELS


class ScreeningRule(Base):
    __tablename__ = "screening_rule"
    __table_args__ = (
        CheckConstraint(
            "screening_rule_id GLOB 'SCR-[0-9][0-9][0-9][0-9]'", name="ck_screening_rule_id_format"
        ),
        CheckConstraint("version >= 1", name="ck_screening_rule_version_positive"),
        CheckConstraint("min_years_experience >= 0", name="ck_screening_rule_min_years_nonneg"),
        CheckConstraint(
            "skill_weight_pct + experience_weight_pct + education_weight_pct = 100",
            name="ck_screening_rule_weights_sum_100",
        ),
        CheckConstraint(
            "pass_threshold_score >= 0 AND pass_threshold_score <= 100",
            name="ck_screening_rule_threshold_bounds",
        ),
        Index(
            "uq_screeningrule_current",
            "requisition_id",
            unique=True,
            sqlite_where=text("is_current = 1"),
        ),
    )

    screening_rule_id: Mapped[str] = mapped_column(String(20), primary_key=True)
    requisition_id: Mapped[str] = mapped_column(
        String(20), ForeignKey("job_requisition.requisition_id"), nullable=False
    )
    is_current: Mapped[bool] = mapped_column(nullable=False, default=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    min_years_experience: Mapped[float] = mapped_column(Numeric(4, 1), nullable=False)
    min_education_level: Mapped[str] = mapped_column(
        Enum(*EDUCATION_LEVELS, name="screening_rule_min_education_level", create_constraint=True),
        nullable=False,
    )
    skill_weight_pct: Mapped[int] = mapped_column(Integer, nullable=False, default=50)
    experience_weight_pct: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    education_weight_pct: Mapped[int] = mapped_column(Integer, nullable=False, default=20)
    pass_threshold_score: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False, default=70.0)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
