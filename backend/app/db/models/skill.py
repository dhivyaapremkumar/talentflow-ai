"""Skill — data_dictionary.md §3 (fixed catalog, A-13: 40 rows both modes).

`CandidateSkill` (the bridge to `Candidate`) is added to this module once
`Candidate` exists (Phase 2, Candidate unit) — kept out for now so this unit
has no forward dependency on a table that doesn't exist yet.
"""

from sqlalchemy import Boolean, CheckConstraint, Enum, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

SKILL_CATEGORIES = ("Technical", "Tool", "Domain", "Soft")


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
