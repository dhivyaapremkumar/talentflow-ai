"""Phase 2 model tests.

Unit 1: Department, Skill, SystemActor, Interviewer,
InterviewerAvailabilitySlot — table creation, PK uniqueness, FK enforcement,
enum/GLOB-format constraints, and the start<end check constraint.

Unit 2 (this commit): JobRequisition, JobRequisitionSkill, ScreeningRule —
composite PK, weight/threshold CHECK constraints, the three-weight-sum=100
constraint, and the uq_screeningrule_current partial unique index.

Each test gets a fresh in-memory SQLite database with foreign_keys=ON, so
these tests exercise the exact same engine configuration as app.db.session
(the PRAGMA listener is registered via make_engine(), not hand-rolled here).
"""

from datetime import date, datetime

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.models import (
    Department,
    Interviewer,
    InterviewerAvailabilitySlot,
    JobRequisition,
    JobRequisitionSkill,
    ScreeningRule,
    Skill,
    SystemActor,
)
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


# --- Unit 2: JobRequisition, JobRequisitionSkill, ScreeningRule ---------------


def _actor(session, actor_id="ACT-0001", role="BUSINESS_REQUESTER"):
    a = SystemActor(
        actor_id=actor_id,
        full_name=f"Actor {actor_id}",
        role=role,
        department_id=None,
        email=f"{actor_id.lower()}@example.com",
        is_active=True,
        created_at=datetime(2026, 1, 1),
    )
    session.add(a)
    session.commit()
    return a


def _requisition(session, req_id="REQ-00001", salary_min=100000, salary_max=150000, headcount=1):
    _department(session)
    _actor(session)
    r = JobRequisition(
        requisition_id=req_id,
        department_id="DEPT-0001",
        title="Software Engineer",
        level="Mid",
        employment_type="FullTime",
        status="Draft",
        salary_min=salary_min,
        salary_max=salary_max,
        headcount=headcount,
        requested_by_actor_id="ACT-0001",
        created_at=datetime(2026, 1, 1),
    )
    session.add(r)
    session.commit()
    return r


def test_requisition_valid_insert(session):
    _requisition(session)
    assert session.query(JobRequisition).count() == 1


def test_requisition_id_format_rejected(session):
    _department(session)
    _actor(session)
    session.add(
        JobRequisition(
            requisition_id="BADID",
            department_id="DEPT-0001",
            title="Bad ID",
            level="Mid",
            employment_type="FullTime",
            status="Draft",
            salary_min=100000,
            salary_max=150000,
            headcount=1,
            requested_by_actor_id="ACT-0001",
            created_at=datetime(2026, 1, 1),
        )
    )
    with pytest.raises(IntegrityError):
        session.commit()


def test_requisition_salary_max_below_min_rejected(session):
    with pytest.raises(IntegrityError):
        _requisition(session, salary_min=150000, salary_max=100000)


def test_requisition_headcount_zero_rejected(session):
    with pytest.raises(IntegrityError):
        _requisition(session, headcount=0)


def test_requisition_status_enum_rejected(session):
    _department(session)
    _actor(session)
    session.add(
        JobRequisition(
            requisition_id="REQ-00001",
            department_id="DEPT-0001",
            title="Bad Status",
            level="Mid",
            employment_type="FullTime",
            status="NotAStatus",
            salary_min=100000,
            salary_max=150000,
            headcount=1,
            requested_by_actor_id="ACT-0001",
            created_at=datetime(2026, 1, 1),
        )
    )
    with pytest.raises(IntegrityError):
        session.commit()


def _skill(session, skill_id="SKL-0001", name="Python"):
    s = Skill(skill_id=skill_id, name=name, category="Technical", is_active=True)
    session.add(s)
    session.commit()
    return s


def test_job_requisition_skill_valid_insert(session):
    _requisition(session)
    _skill(session)
    session.add(
        JobRequisitionSkill(
            requisition_id="REQ-00001",
            skill_id="SKL-0001",
            min_proficiency_level="Advanced",
            is_mandatory=True,
            weight_pct=60,
        )
    )
    session.commit()
    assert session.query(JobRequisitionSkill).count() == 1


def test_job_requisition_skill_duplicate_pair_rejected(session):
    _requisition(session)
    _skill(session)
    session.add(
        JobRequisitionSkill(
            requisition_id="REQ-00001",
            skill_id="SKL-0001",
            min_proficiency_level="Advanced",
            is_mandatory=True,
            weight_pct=60,
        )
    )
    session.commit()
    session.add(
        JobRequisitionSkill(
            requisition_id="REQ-00001",
            skill_id="SKL-0001",  # same composite PK again
            min_proficiency_level="Intermediate",
            is_mandatory=False,
            weight_pct=40,
        )
    )
    with pytest.raises(IntegrityError):
        session.commit()


def test_job_requisition_skill_weight_out_of_bounds_rejected(session):
    _requisition(session)
    _skill(session)
    session.add(
        JobRequisitionSkill(
            requisition_id="REQ-00001",
            skill_id="SKL-0001",
            min_proficiency_level="Advanced",
            is_mandatory=True,
            weight_pct=150,  # out of 0-100 bounds
        )
    )
    with pytest.raises(IntegrityError):
        session.commit()


def test_job_requisition_skill_proficiency_enum_rejected(session):
    _requisition(session)
    _skill(session)
    session.add(
        JobRequisitionSkill(
            requisition_id="REQ-00001",
            skill_id="SKL-0001",
            min_proficiency_level="NotALevel",
            is_mandatory=True,
            weight_pct=60,
        )
    )
    with pytest.raises(IntegrityError):
        session.commit()


def _screening_rule(session, rule_id="SCR-0001", skill_wt=50, exp_wt=30, edu_wt=20, threshold=70.0):
    _requisition(session)
    rule = ScreeningRule(
        screening_rule_id=rule_id,
        requisition_id="REQ-00001",
        is_current=True,
        version=1,
        min_years_experience=4.0,
        min_education_level="Bachelor",
        skill_weight_pct=skill_wt,
        experience_weight_pct=exp_wt,
        education_weight_pct=edu_wt,
        pass_threshold_score=threshold,
        created_at=datetime(2026, 1, 1),
    )
    session.add(rule)
    session.commit()
    return rule


def test_screening_rule_valid_insert_with_approved_default_weights(session):
    _screening_rule(session)
    assert session.query(ScreeningRule).count() == 1


def test_screening_rule_id_format_rejected(session):
    _requisition(session)
    session.add(
        ScreeningRule(
            screening_rule_id="BADID",
            requisition_id="REQ-00001",
            is_current=True,
            version=1,
            min_years_experience=4.0,
            min_education_level="Bachelor",
            skill_weight_pct=50,
            experience_weight_pct=30,
            education_weight_pct=20,
            pass_threshold_score=70.0,
            created_at=datetime(2026, 1, 1),
        )
    )
    with pytest.raises(IntegrityError):
        session.commit()


def test_screening_rule_weights_not_summing_to_100_rejected(session):
    with pytest.raises(IntegrityError):
        _screening_rule(session, skill_wt=50, exp_wt=30, edu_wt=15)  # sums to 95


def test_screening_rule_threshold_out_of_bounds_rejected(session):
    with pytest.raises(IntegrityError):
        _screening_rule(session, threshold=150.0)


def test_screening_rule_two_current_rows_for_same_requisition_rejected(session):
    """Structural backstop for 'at most one is_current=true per requisition'."""
    _screening_rule(session, rule_id="SCR-0001")
    session.add(
        ScreeningRule(
            screening_rule_id="SCR-0002",
            requisition_id="REQ-00001",
            is_current=True,  # a second current row for the same requisition
            version=2,
            min_years_experience=5.0,
            min_education_level="Bachelor",
            skill_weight_pct=50,
            experience_weight_pct=30,
            education_weight_pct=20,
            pass_threshold_score=70.0,
            created_at=datetime(2026, 1, 2),
        )
    )
    with pytest.raises(IntegrityError):
        session.commit()


def test_screening_rule_historical_noncurrent_row_for_same_requisition_allowed(session):
    """A redefinition's OLD row, flipped to is_current=False, coexists fine —
    this is exactly how `business_rules.md` §4's versioning is supposed to work."""
    _screening_rule(session, rule_id="SCR-0001")
    session.query(ScreeningRule).filter_by(screening_rule_id="SCR-0001").update({"is_current": False})
    session.commit()
    session.add(
        ScreeningRule(
            screening_rule_id="SCR-0002",
            requisition_id="REQ-00001",
            is_current=True,
            version=2,
            min_years_experience=5.0,
            min_education_level="Bachelor",
            skill_weight_pct=50,
            experience_weight_pct=30,
            education_weight_pct=20,
            pass_threshold_score=70.0,
            created_at=datetime(2026, 1, 2),
        )
    )
    session.commit()
    assert session.query(ScreeningRule).count() == 2
