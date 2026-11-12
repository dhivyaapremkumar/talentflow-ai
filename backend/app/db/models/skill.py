"""Skill, CandidateSkill — data_dictionary.md §3/§7.

`CandidateSkill` is one of the 12 mandated entities (the Candidate<->Skill
bridge) — not a 13th table (entity_relationships.md §1).
"""

from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, Enum, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.enums import PROFICIENCY_LEVELS

SKILL_CATEGORIES = ("Technical", "Tool", "Domain", "Soft")
SKILL_SOURCES = ("ResumeParsed", "SelfReported")


class Skill(Base):
    __tablename__ = "skill"
    __table_args__ = (
        CheckConstraint("skill_id GLOB 'SKL-[0-9][0-9][0-9][0-9]'", name="ck_skill_id_format"),
    )

    skill_id: Mapped[str] = mapped_column(String(20), primary_key=True)
    name: Mapped[str] = mapped_column(String(60), unique=True, nullable=False)
    category: Mapped[str] = mapped_column(
        Enum(*SKILL_CATEGORIES, name="skill_category", create_constraint=True), nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class CandidateSkill(Base):
    """`years_of_experience <= Candidate.years_experience` (data_dictionary.md
    §7) is a cross-table rule — SQLite CHECK constraints cannot reference
    another table's column, so this is a Phase 4 validation-engine concern,
    not a structural constraint here (same category as JobRequisitionSkill's
    weight-sum rule)."""

    __tablename__ = "candidate_skill"

    candidate_id: Mapped[str] = mapped_column(
        String(20), ForeignKey("candidate.candidate_id"), primary_key=True
    )
    skill_id: Mapped[str] = mapped_column(String(20), ForeignKey("skill.skill_id"), primary_key=True)
    proficiency_level: Mapped[str] = mapped_column(
        Enum(*PROFICIENCY_LEVELS, name="candidate_skill_proficiency_level", create_constraint=True),
        nullable=False,
    )
    years_of_experience: Mapped[float] = mapped_column(Numeric(4, 1), nullable=False)
    source: Mapped[str] = mapped_column(
        Enum(*SKILL_SOURCES, name="candidate_skill_source", create_constraint=True), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
