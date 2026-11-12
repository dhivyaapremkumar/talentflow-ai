"""GenerationRun — data_dictionary.md §17. Reproducibility manifest; one row
per generator invocation, never updated after insert.

`seed` is CHECK-constrained to the single project-mandated value (20261022,
PROJECT_SPEC.md) rather than left as an open integer range — this project
has exactly one approved seed, and the spec's "Allowed values" column lists
it as that one literal value, not a range.

`run_id`/`generated_at` are volatile execution metadata (expected to differ
across repeated runs); `seed`/`mode`/`generator_version`/
`entity_counts_json`/`table_checksums_json`/`overall_checksum` and the
*results* portions of the two report JSON fields are deterministic content
(expected to be byte-identical across repeated runs sharing seed+mode+
generator_version). This distinction is a Phase 4 comparison concern, not
something a CHECK constraint can express — it's about comparing specific
JSON sub-fields across *different rows*, not validating any single row.
"""

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.config import SEED

GENERATION_RUN_MODES = ("starter", "full")


class GenerationRun(Base):
    __tablename__ = "generation_run"
    __table_args__ = (
        CheckConstraint("run_id GLOB 'GEN-[0-9][0-9][0-9][0-9]'", name="ck_generation_run_id_format"),
        CheckConstraint(f"seed = {SEED}", name="ck_generation_run_seed_fixed"),
    )

    run_id: Mapped[str] = mapped_column(String(20), primary_key=True)
    seed: Mapped[int] = mapped_column(Integer, nullable=False)
    mode: Mapped[str] = mapped_column(
        Enum(*GENERATION_RUN_MODES, name="generation_run_mode", create_constraint=True), nullable=False
    )
    generator_version: Mapped[str] = mapped_column(String(40), nullable=False)
    generated_by_actor_id: Mapped[str] = mapped_column(
        String(20), ForeignKey("system_actor.actor_id"), nullable=False
    )
    generated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    entity_counts_json: Mapped[str] = mapped_column(Text, nullable=False)
    table_checksums_json: Mapped[str] = mapped_column(Text, nullable=False)
    overall_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    baseline_validation_report_json: Mapped[str] = mapped_column(Text, nullable=False)
    post_injection_validation_report_json: Mapped[str] = mapped_column(Text, nullable=False)
