"""Department — data_dictionary.md §1. Fixed catalog size (A-13): 10 rows in
both starter and full generation modes (not enforced here — a generator-time
concern)."""

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Department(Base):
    __tablename__ = "department"
    __table_args__ = (
        CheckConstraint(
            "department_id GLOB 'DEPT-[0-9][0-9][0-9][0-9]'",
            name="ck_department_id_format",
        ),
    )

    department_id: Mapped[str] = mapped_column(String(20), primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    cost_center_code: Mapped[str] = mapped_column(String(10), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
