"""Application, ApplicationSubmissionAttempt — data_dictionary.md §8/§8a.

`application_id` is a derived PK (`APP-<requisition_id>-<candidate_id>`),
computed by application code (services/application_submission.py, a later
phase), never by a SQL `GENERATED ALWAYS AS` column — this keeps the
derivation logic in one place shared with validation
(architecture.md §6). The GLOB check below only enforces the *format*;
it cannot enforce that the embedded ids actually match the FK columns'
values — that cross-column consistency check is deferred to Phase 4
(same category as the other cross-row/cross-table rules already
documented in this package).

`latest_screening_run_id` intentionally *does* carry a real SQL FOREIGN
KEY to `screening_run.screening_run_id`, even though `ScreeningRun.
application_id` FKs back to this table — a genuine two-table reference
cycle. Verified empirically (not assumed) that SQLAlchemy's
`Base.metadata.create_all()` emits both CREATE TABLE statements with
inline FOREIGN KEY clauses and does not require `use_alter`/ALTER TABLE
for a simple two-node cycle; SQLite does not validate FK targets at
CREATE TABLE time, only at DML time. The only ordering constraint that
matters is already handled by the documented insert procedure
(data_dictionary.md §8b): insert Application first with
`latest_screening_run_id=NULL`, then the ScreeningRun row, then update
Application — one transaction, never a dangling reference.
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
from app.db.enums import PASS_FAIL_DECISIONS
from app.db.models.candidate import SOURCE_CHANNELS

APPLICATION_STAGES = (
    "Applied",
    "Screening",
    "Interviewing",
    "Offer",
    "Hired",
    "Rejected",
    "Withdrawn",
)
ATTEMPT_ISSUE_TYPES = ("None", "DuplicateSubmission")


class Application(Base):
    __tablename__ = "application"
    __table_args__ = (
        CheckConstraint(
            "application_id GLOB 'APP-REQ-[0-9][0-9][0-9][0-9][0-9]-CAND-"
            "[0-9][0-9][0-9][0-9][0-9][0-9]'",
            name="ck_application_id_format",
        ),
        CheckConstraint(
            "screening_score IS NULL OR (screening_score >= 0 AND screening_score <= 100)",
            name="ck_application_screening_score_bounds",
        ),
        CheckConstraint(
            "stage != 'Rejected' OR rejected_reason IS NOT NULL",
            name="ck_application_rejected_reason_required",
        ),
        CheckConstraint(
            "stage != 'Withdrawn' OR withdrawn_at IS NOT NULL",
            name="ck_application_withdrawn_at_required",
        ),
    )

    application_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    candidate_id: Mapped[str] = mapped_column(
        String(20), ForeignKey("candidate.candidate_id"), nullable=False
    )
    requisition_id: Mapped[str] = mapped_column(
        String(20), ForeignKey("job_requisition.requisition_id"), nullable=False
    )
    resume_artifact_id: Mapped[str] = mapped_column(
        String(20), ForeignKey("resume_artifact.resume_artifact_id"), nullable=False
    )
    applied_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    source_channel: Mapped[str] = mapped_column(
        Enum(*SOURCE_CHANNELS, name="application_source_channel", create_constraint=True),
        nullable=False,
    )
    stage: Mapped[str] = mapped_column(
        Enum(*APPLICATION_STAGES, name="application_stage", create_constraint=True),
        nullable=False,
    )
    screening_score: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    screening_skill_component: Mapped[float | None] = mapped_column(Numeric(5, 4), nullable=True)
    screening_experience_component: Mapped[float | None] = mapped_column(Numeric(5, 4), nullable=True)
    screening_education_component: Mapped[float | None] = mapped_column(Numeric(5, 4), nullable=True)
    screening_education_gate_passed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    screening_decision: Mapped[str | None] = mapped_column(
        Enum(*PASS_FAIL_DECISIONS, name="application_screening_decision", create_constraint=True),
        nullable=True,
    )
    screening_rule_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    screening_computed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    screening_explanation: Mapped[str | None] = mapped_column(String(500), nullable=True)
    latest_screening_run_id: Mapped[str | None] = mapped_column(
        String(20), ForeignKey("screening_run.screening_run_id"), nullable=True
    )
    rejected_reason: Mapped[str | None] = mapped_column(String(200), nullable=True)
    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class ApplicationSubmissionAttempt(Base):
    """Append-only audit trail of every submission event for a
    (candidate_id, requisition_id) pair — business_rules.md §10,
    data_dictionary.md §8a. `ground_truth_label_id` FKs to `AnomalyLabel`
    (added in Phase 2, Unit 8, once that table exists in `Base.metadata`)
    — set only at generation time for the 15 seeded duplicate-submission
    attempts; never consulted by the `issue_type` detector."""

    __tablename__ = "application_submission_attempt"
    __table_args__ = (
        CheckConstraint(
            "attempt_id GLOB 'ATT-[0-9][0-9][0-9][0-9][0-9][0-9][0-9]'",
            name="ck_attempt_id_format",
        ),
        CheckConstraint(
            "(is_canonical = 1 AND duplicate_of_attempt_id IS NULL) OR "
            "(is_canonical = 0 AND duplicate_of_attempt_id IS NOT NULL)",
            name="ck_attempt_canonical_duplicate_consistency",
        ),
        Index(
            "uq_attempt_canonical",
            "canonical_application_id",
            unique=True,
            sqlite_where=text("is_canonical = 1"),
        ),
    )

    attempt_id: Mapped[str] = mapped_column(String(20), primary_key=True)
    canonical_application_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("application.application_id"), nullable=False
    )
    candidate_id: Mapped[str] = mapped_column(
        String(20), ForeignKey("candidate.candidate_id"), nullable=False
    )
    requisition_id: Mapped[str] = mapped_column(
        String(20), ForeignKey("job_requisition.requisition_id"), nullable=False
    )
    submitted_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    is_canonical: Mapped[bool] = mapped_column(Boolean, nullable=False)
    duplicate_of_attempt_id: Mapped[str | None] = mapped_column(
        String(20), ForeignKey("application_submission_attempt.attempt_id"), nullable=True
    )
    issue_type: Mapped[str] = mapped_column(
        Enum(*ATTEMPT_ISSUE_TYPES, name="attempt_issue_type", create_constraint=True),
        nullable=False,
    )
    ground_truth_label_id: Mapped[str | None] = mapped_column(
        String(20), ForeignKey("anomaly_label.label_id"), nullable=True
    )
