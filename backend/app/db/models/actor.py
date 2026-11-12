"""SystemActor — data_dictionary.md §18 (fixed catalog, A-11: 20 rows both
modes; no authentication/password fields — audit/attribution identity only,
PROJECT_SPEC.md §2)."""

from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, Enum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

SYSTEM_ACTOR_ROLES = (
    "BUSINESS_REQUESTER",
    "PROCESS_OWNER",
    "APPROVER",
    "OPERATIONS_ANALYST",
    "SYSTEM_ADMINISTRATOR",
)


class SystemActor(Base):
    __tablename__ = "system_actor"
    __table_args__ = (
        CheckConstraint("actor_id GLOB 'ACT-[0-9][0-9][0-9][0-9]'", name="ck_actor_id_format"),
    )

    actor_id: Mapped[str] = mapped_column(String(20), primary_key=True)
    full_name: Mapped[str] = mapped_column(String(100), nullable=False)
    role: Mapped[str] = mapped_column(
        Enum(*SYSTEM_ACTOR_ROLES, name="system_actor_role", create_constraint=True), nullable=False
    )
    department_id: Mapped[str | None] = mapped_column(
        String(20), ForeignKey("department.department_id"), nullable=True
    )
    email: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
