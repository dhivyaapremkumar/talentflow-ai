"""Phase 2 model tests.

Unit 1 (this commit): Department, Skill, SystemActor, Interviewer,
InterviewerAvailabilitySlot — table creation, PK uniqueness, FK enforcement,
enum/GLOB-format constraints, and the start<end check constraint.

Each test gets a fresh in-memory SQLite database with foreign_keys=ON, so
these tests exercise the exact same engine configuration as app.db.session
(the PRAGMA listener is registered via make_engine(), not hand-rolled here).
"""

from datetime import datetime

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.models import Department, Interviewer, InterviewerAvailabilitySlot, Skill, SystemActor
from app.db.session import make_engine


@pytest.fixture()
def session():
    engine = make_engine(":memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def _department(session, dept_id="DEPT-0001"):
    d = Department(
        department_id=dept_id,
        name=f"Engineering {dept_id}",
        cost_center_code=f"CC-{dept_id}",
        created_at=datetime(2026, 1, 1),
    )
    session.add(d)
    session.commit()
    return d


def test_tables_created(session):
    # If create_all() ran without error (the fixture itself), the schema is valid.
    assert session.query(Department).count() == 0


def test_department_pk_uniqueness_rejected(session):
    _department(session)
    session.add(
        Department(
            department_id="DEPT-0001",
            name="Duplicate",
            cost_center_code="CC-OTHER",
            created_at=datetime(2026, 1, 1),
        )
    )
    with pytest.raises(IntegrityError):
        session.commit()


def test_department_id_format_rejected(session):
    session.add(
        Department(
            department_id="NOTVALID",
            name="Bad ID",
            cost_center_code="CC-X",
            created_at=datetime(2026, 1, 1),
        )
    )
    with pytest.raises(IntegrityError):
        session.commit()


def test_department_unique_name_rejected(session):
    _department(session, "DEPT-0001")
    session.add(
        Department(
            department_id="DEPT-0002",
            name="Engineering DEPT-0001",  # same name as the first
            cost_center_code="CC-DEPT-0002",
            created_at=datetime(2026, 1, 1),
        )
    )
    with pytest.raises(IntegrityError):
        session.commit()


def test_skill_enum_rejected(session):
    session.add(Skill(skill_id="SKL-0001", name="Python", category="NotARealCategory", is_active=True))
    with pytest.raises(IntegrityError):
        session.commit()


def test_skill_valid_insert(session):
    session.add(Skill(skill_id="SKL-0001", name="Python", category="Technical", is_active=True))
    session.commit()
    assert session.query(Skill).count() == 1


def test_system_actor_fk_to_department_enforced(session):
    session.add(
        SystemActor(
            actor_id="ACT-0001",
            full_name="Jane Recruiter",
            role="PROCESS_OWNER",
            department_id="DEPT-9999",  # does not exist
            email="jane@example.com",
            is_active=True,
            created_at=datetime(2026, 1, 1),
        )
    )
    with pytest.raises(IntegrityError):
        session.commit()


def test_system_actor_nullable_department_for_org_wide_roles(session):
    session.add(
        SystemActor(
            actor_id="ACT-0002",
            full_name="Sam Admin",
            role="SYSTEM_ADMINISTRATOR",
            department_id=None,
            email="sam@example.com",
            is_active=True,
            created_at=datetime(2026, 1, 1),
        )
    )
    session.commit()
    assert session.query(SystemActor).count() == 1


def test_system_actor_role_enum_rejected(session):
    session.add(
        SystemActor(
            actor_id="ACT-0003",
            full_name="Bad Role",
            role="NOT_A_ROLE",
            department_id=None,
            email="bad@example.com",
            is_active=True,
            created_at=datetime(2026, 1, 1),
        )
    )
    with pytest.raises(IntegrityError):
        session.commit()


def test_interviewer_requires_existing_department(session):
    _department(session)
    session.add(
        Interviewer(
            interviewer_id="IVR-0001",
            full_name="Ivy Reviewer",
            email="ivy@example.com",
            department_id="DEPT-0001",
            title="Senior Engineer",
            is_active=True,
        )
    )
    session.commit()
    assert session.query(Interviewer).count() == 1


def test_availability_slot_start_before_end_enforced(session):
    _department(session)
    session.add(
        Interviewer(
            interviewer_id="IVR-0001",
            full_name="Ivy Reviewer",
            email="ivy@example.com",
            department_id="DEPT-0001",
            title="Senior Engineer",
            is_active=True,
        )
    )
    session.commit()
    session.add(
        InterviewerAvailabilitySlot(
            slot_id="AVAIL-000001",
            interviewer_id="IVR-0001",
            start_datetime=datetime(2026, 3, 2, 14, 0),
            end_datetime=datetime(2026, 3, 2, 13, 0),  # before start — invalid
            is_booked=False,
        )
    )
    with pytest.raises(IntegrityError):
        session.commit()


def test_availability_slot_requires_existing_interviewer(session):
    session.add(
        InterviewerAvailabilitySlot(
            slot_id="AVAIL-000001",
            interviewer_id="IVR-9999",  # does not exist
            start_datetime=datetime(2026, 3, 2, 13, 0),
            end_datetime=datetime(2026, 3, 2, 14, 0),
            is_booked=False,
        )
    )
    with pytest.raises(IntegrityError):
        session.commit()
