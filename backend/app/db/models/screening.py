"""ScreeningRule, ScreeningRun — data_dictionary.md §9/§8b. ScreeningRule is
versioned/insert-only, three-weight model (APPROVED, business_rules.md §5 —
Skill 50 / Experience 30 / Education 20, default pass_threshold_score=70.0).

ScreeningRun is one immutable row per screening execution, inserted only
once `Application` exists (it FKs to it, plus to the exact `ScreeningRule`
row in effect at `computed_at` — reproducible even after the rule is later
redefined, business_rules.md §4).

The `uq_screeningrule_current` and `uq_screeningrun_latest` partial unique
indexes are the structural backstop for "at most one current/latest row
per requisition/application" — SQLite supports partial unique indexes
natively via `sqlite_where`.
"""

from datetime import datetime

from sqlalchemy import (
    Boolean,
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
from app.db.enums import EDUCATION_LEVELS, PASS_FAIL_DECISIONS


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


class ScreeningRun(Base):
    __tablename__ = "screening_run"
    __table_args__ = (
        CheckConstraint(
            "screening_run_id GLOB 'SCRUN-[0-9][0-9][0-9][0-9][0-9][0-9][0-9]'",
            name="ck_screening_run_id_format",
        ),
        CheckConstraint(
            "screening_skill_component >= 0 AND screening_skill_component <= 1",
            name="ck_screening_run_skill_component_bounds",
        ),
        CheckConstraint(
            "screening_experience_component >= 0 AND screening_experience_component <= 1",
            name="ck_screening_run_experience_component_bounds",
        ),
        CheckConstraint(
            "screening_education_component >= 0 AND screening_education_component <= 1",
            name="ck_screening_run_education_component_bounds",
        ),
        CheckConstraint(
            "screening_score >= 0 AND screening_score <= 100",
            name="ck_screening_run_score_bounds",
        ),
        Index(
            "uq_screeningrun_latest",
            "application_id",
            unique=True,
            sqlite_where=text("is_latest = 1"),
        ),
    )

    screening_run_id: Mapped[str] = mapped_column(String(20), primary_key=True)
    application_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("application.application_id"), nullable=False
    )
    screening_rule_id: Mapped[str] = mapped_column(
        String(20), ForeignKey("screening_rule.screening_rule_id"), nullable=False
    )
    is_latest: Mapped[bool] = mapped_column(Boolean, nullable=False)
    screening_rule_version: Mapped[int] = mapped_column(Integer, nullable=False)
    screening_skill_component: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False)
    screening_experience_component: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False)
    screening_education_component: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False)
    screening_education_gate_passed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    screening_score: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    screening_decision: Mapped[str] = mapped_column(
        Enum(*PASS_FAIL_DECISIONS, name="screening_run_decision", create_constraint=True),
        nullable=False,
    )
    screening_explanation: Mapped[str] = mapped_column(String(500), nullable=False)
    computed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
