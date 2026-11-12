"""Candidate, ResumeArtifact — data_dictionary.md §5/§6.

Deliberately excludes demographic fields (PROJECT_SPEC.md A-9) — no gender,
age/DOB, ethnicity, marital status, religion, or photo column exists here,
by construction, not by omission-then-ignoring.
"""

from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, Enum, ForeignKey, Index, Numeric, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.enums import EDUCATION_LEVELS

SOURCE_CHANNELS = ("Referral", "Website", "LinkedIn", "Agency", "JobBoard")
RESUME_FILE_FORMATS = ("PDF", "DOCX")


class Candidate(Base):
    __tablename__ = "candidate"
    __table_args__ = (
        CheckConstraint(
            "candidate_id GLOB 'CAND-[0-9][0-9][0-9][0-9][0-9][0-9]'", name="ck_candidate_id_format"
        ),
        CheckConstraint(
            "years_experience >= 0 AND years_experience <= 50", name="ck_candidate_years_experience_bounds"
        ),
    )

    candidate_id: Mapped[str] = mapped_column(String(20), primary_key=True)
    full_name: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    location_city: Mapped[str] = mapped_column(String(60), nullable=False)
    location_country: Mapped[str] = mapped_column(String(60), nullable=False)
    years_experience: Mapped[float] = mapped_column(Numeric(4, 1), nullable=False)
    highest_education_level: Mapped[str] = mapped_column(
        Enum(*EDUCATION_LEVELS, name="candidate_highest_education_level", create_constraint=True),
        nullable=False,
    )
    source_channel: Mapped[str] = mapped_column(
        Enum(*SOURCE_CHANNELS, name="candidate_source_channel", create_constraint=True), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class ResumeArtifact(Base):
    __tablename__ = "resume_artifact"
    __table_args__ = (
        CheckConstraint(
            "resume_artifact_id GLOB 'RES-[0-9][0-9][0-9][0-9][0-9][0-9]'",
            name="ck_resume_artifact_id_format",
        ),
        Index(
            "uq_resume_artifact_latest",
            "candidate_id",
            unique=True,
            sqlite_where=text("is_latest = 1"),
        ),
    )

    resume_artifact_id: Mapped[str] = mapped_column(String(20), primary_key=True)
    candidate_id: Mapped[str] = mapped_column(
        String(20), ForeignKey("candidate.candidate_id"), nullable=False
    )
    file_name: Mapped[str] = mapped_column(String(120), nullable=False)
    file_format: Mapped[str] = mapped_column(
        Enum(*RESUME_FILE_FORMATS, name="resume_file_format", create_constraint=True), nullable=False
    )
    parsed_years_experience: Mapped[float] = mapped_column(Numeric(4, 1), nullable=False)
    parsed_education_level: Mapped[str] = mapped_column(
        Enum(*EDUCATION_LEVELS, name="resume_parsed_education_level", create_constraint=True),
        nullable=False,
    )
    is_latest: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
