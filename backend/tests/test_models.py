"""Phase 2 model tests.

Unit 1: Department, Skill, SystemActor, Interviewer,
InterviewerAvailabilitySlot — table creation, PK uniqueness, FK enforcement,
enum/GLOB-format constraints, and the start<end check constraint.

Unit 2: JobRequisition, JobRequisitionSkill, ScreeningRule — composite PK,
weight/threshold CHECK constraints, the three-weight-sum=100 constraint,
and the uq_screeningrule_current partial unique index.

Unit 3: Candidate, ResumeArtifact, CandidateSkill.

Unit 4: Application, ApplicationSubmissionAttempt, ScreeningRun — the
derived-PK application_id, the canonical/duplicate attempt CHECK +
uq_attempt_canonical partial unique index, the uq_screeningrun_latest
partial unique index, and a real insert-level round-trip through the
Application<->ScreeningRun circular FK.

Unit 5: Interview, Feedback — round_number/start-before-end CHECKs, and
the 1:1 Feedback<->Interview unique FK.

Unit 6: Offer — the 1:1 Offer<->Application unique FK, and the
required-iff-status / chronological-ordering CHECK constraints
(approval/extension/decision/expiry).

Unit 7 (this commit): RequisitionStatusHistory, ApplicationStageHistory,
OfferStatusHistory — the three append-only event-history tables. Mostly
FK-enforcement and ID-format tests; the transition-legality and
strictly-increasing-changed_at rules are cross-row and deferred to
Phase 4 (not tested here, consistent with every other such deferral).

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
    Application,
    ApplicationStageHistory,
    ApplicationSubmissionAttempt,
    Candidate,
    CandidateSkill,
    Department,
    Feedback,
    Interview,
    Interviewer,
    InterviewerAvailabilitySlot,
    JobRequisition,
    JobRequisitionSkill,
    Offer,
    OfferStatusHistory,
    RequisitionStatusHistory,
    ResumeArtifact,
    ScreeningRule,
    ScreeningRun,
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


# --- Unit 3: Candidate, ResumeArtifact, CandidateSkill ------------------------


def _candidate(session, cand_id="CAND-000001", years_experience=6.0):
    c = Candidate(
        candidate_id=cand_id,
        full_name="Casey Candidate",
        email=f"{cand_id.lower()}@example.com",
        phone=None,
        location_city="Chennai",
        location_country="India",
        years_experience=years_experience,
        highest_education_level="Bachelor",
        source_channel="Website",
        created_at=datetime(2026, 1, 1),
    )
    session.add(c)
    session.commit()
    return c


def test_candidate_valid_insert(session):
    _candidate(session)
    assert session.query(Candidate).count() == 1


def test_candidate_id_format_rejected(session):
    session.add(
        Candidate(
            candidate_id="BADID",
            full_name="Bad ID",
            email="bad@example.com",
            phone=None,
            location_city="Chennai",
            location_country="India",
            years_experience=1.0,
            highest_education_level="Bachelor",
            source_channel="Website",
            created_at=datetime(2026, 1, 1),
        )
    )
    with pytest.raises(IntegrityError):
        session.commit()


def test_candidate_years_experience_out_of_bounds_rejected(session):
    with pytest.raises(IntegrityError):
        _candidate(session, years_experience=51.0)


def test_candidate_unique_email_rejected(session):
    _candidate(session, cand_id="CAND-000001")
    session.add(
        Candidate(
            candidate_id="CAND-000002",
            full_name="Dup Email",
            email="cand-000001@example.com",  # same email as the first
            phone=None,
            location_city="Chennai",
            location_country="India",
            years_experience=1.0,
            highest_education_level="Bachelor",
            source_channel="Website",
            created_at=datetime(2026, 1, 1),
        )
    )
    with pytest.raises(IntegrityError):
        session.commit()


def test_resume_artifact_valid_insert(session):
    _candidate(session)
    session.add(
        ResumeArtifact(
            resume_artifact_id="RES-000001",
            candidate_id="CAND-000001",
            file_name="casey_resume.pdf",
            file_format="PDF",
            parsed_years_experience=6.0,
            parsed_education_level="Bachelor",
            is_latest=True,
            uploaded_at=datetime(2026, 1, 1),
        )
    )
    session.commit()
    assert session.query(ResumeArtifact).count() == 1


def test_resume_artifact_two_latest_for_same_candidate_rejected(session):
    """Structural backstop for 'exactly one is_latest=true per candidate'."""
    _candidate(session)
    session.add(
        ResumeArtifact(
            resume_artifact_id="RES-000001",
            candidate_id="CAND-000001",
            file_name="v1.pdf",
            file_format="PDF",
            parsed_years_experience=6.0,
            parsed_education_level="Bachelor",
            is_latest=True,
            uploaded_at=datetime(2026, 1, 1),
        )
    )
    session.commit()
    session.add(
        ResumeArtifact(
            resume_artifact_id="RES-000002",
            candidate_id="CAND-000001",
            file_name="v2.pdf",
            file_format="PDF",
            parsed_years_experience=6.0,
            parsed_education_level="Bachelor",
            is_latest=True,  # second is_latest=true for the same candidate
            uploaded_at=datetime(2026, 1, 2),
        )
    )
    with pytest.raises(IntegrityError):
        session.commit()


def test_candidate_skill_valid_insert(session):
    _candidate(session)
    _skill(session)
    session.add(
        CandidateSkill(
            candidate_id="CAND-000001",
            skill_id="SKL-0001",
            proficiency_level="Advanced",
            years_of_experience=3.0,
            source="SelfReported",
            updated_at=datetime(2026, 1, 1),
        )
    )
    session.commit()
    assert session.query(CandidateSkill).count() == 1


def test_candidate_skill_duplicate_pair_rejected(session):
    _candidate(session)
    _skill(session)
    session.add(
        CandidateSkill(
            candidate_id="CAND-000001",
            skill_id="SKL-0001",
            proficiency_level="Advanced",
            years_of_experience=3.0,
            source="SelfReported",
            updated_at=datetime(2026, 1, 1),
        )
    )
    session.commit()
    session.add(
        CandidateSkill(
            candidate_id="CAND-000001",
            skill_id="SKL-0001",  # same composite PK again
            proficiency_level="Expert",
            years_of_experience=5.0,
            source="ResumeParsed",
            updated_at=datetime(2026, 1, 2),
        )
    )
    with pytest.raises(IntegrityError):
        session.commit()


def test_candidate_skill_proficiency_enum_rejected(session):
    _candidate(session)
    _skill(session)
    session.add(
        CandidateSkill(
            candidate_id="CAND-000001",
            skill_id="SKL-0001",
            proficiency_level="NotALevel",
            years_of_experience=3.0,
            source="SelfReported",
            updated_at=datetime(2026, 1, 1),
        )
    )
    with pytest.raises(IntegrityError):
        session.commit()


# --- Unit 4: Application, ApplicationSubmissionAttempt, ScreeningRun --------


def _resume_artifact(session, cand_id="CAND-000001", res_id="RES-000001"):
    r = ResumeArtifact(
        resume_artifact_id=res_id,
        candidate_id=cand_id,
        file_name="resume.pdf",
        file_format="PDF",
        parsed_years_experience=6.0,
        parsed_education_level="Bachelor",
        is_latest=True,
        uploaded_at=datetime(2026, 1, 1),
    )
    session.add(r)
    session.commit()
    return r


def _application(
    session,
    app_id="APP-REQ-00001-CAND-000001",
    req_id="REQ-00001",
    cand_id="CAND-000001",
    res_id="RES-000001",
    stage="Applied",
    rejected_reason=None,
    withdrawn_at=None,
):
    _requisition(session, req_id=req_id)
    _candidate(session, cand_id=cand_id)
    _resume_artifact(session, cand_id=cand_id, res_id=res_id)
    a = Application(
        application_id=app_id,
        candidate_id=cand_id,
        requisition_id=req_id,
        resume_artifact_id=res_id,
        applied_at=datetime(2026, 1, 1),
        source_channel="Website",
        stage=stage,
        rejected_reason=rejected_reason,
        withdrawn_at=withdrawn_at,
        created_at=datetime(2026, 1, 1),
        updated_at=datetime(2026, 1, 1),
    )
    session.add(a)
    session.commit()
    return a


def test_application_valid_insert(session):
    _application(session)
    assert session.query(Application).count() == 1


def test_application_id_format_rejected(session):
    _requisition(session)
    _candidate(session)
    _resume_artifact(session)
    session.add(
        Application(
            application_id="BAD-ID",
            candidate_id="CAND-000001",
            requisition_id="REQ-00001",
            resume_artifact_id="RES-000001",
            applied_at=datetime(2026, 1, 1),
            source_channel="Website",
            stage="Applied",
            created_at=datetime(2026, 1, 1),
            updated_at=datetime(2026, 1, 1),
        )
    )
    with pytest.raises(IntegrityError):
        session.commit()


def test_application_rejected_without_reason_rejected(session):
    with pytest.raises(IntegrityError):
        _application(session, stage="Rejected", rejected_reason=None)


def test_application_rejected_with_reason_allowed(session):
    _application(session, stage="Rejected", rejected_reason="Not enough experience")
    assert session.query(Application).count() == 1


def test_application_withdrawn_without_timestamp_rejected(session):
    with pytest.raises(IntegrityError):
        _application(session, stage="Withdrawn", withdrawn_at=None)


def test_application_screening_score_out_of_bounds_rejected(session):
    _requisition(session)
    _candidate(session)
    _resume_artifact(session)
    session.add(
        Application(
            application_id="APP-REQ-00001-CAND-000001",
            candidate_id="CAND-000001",
            requisition_id="REQ-00001",
            resume_artifact_id="RES-000001",
            applied_at=datetime(2026, 1, 1),
            source_channel="Website",
            stage="Screening",
            screening_score=150.0,
            created_at=datetime(2026, 1, 1),
            updated_at=datetime(2026, 1, 1),
        )
    )
    with pytest.raises(IntegrityError):
        session.commit()


def test_application_stage_enum_rejected(session):
    with pytest.raises(IntegrityError):
        _application(session, stage="NotAStage")


def _attempt(
    session,
    attempt_id="ATT-0000001",
    app_id="APP-REQ-00001-CAND-000001",
    is_canonical=True,
    duplicate_of_attempt_id=None,
    issue_type="None",
    submitted_at=datetime(2026, 1, 1),
):
    att = ApplicationSubmissionAttempt(
        attempt_id=attempt_id,
        canonical_application_id=app_id,
        candidate_id="CAND-000001",
        requisition_id="REQ-00001",
        submitted_at=submitted_at,
        is_canonical=is_canonical,
        duplicate_of_attempt_id=duplicate_of_attempt_id,
        issue_type=issue_type,
    )
    session.add(att)
    session.commit()
    return att


def test_application_submission_attempt_valid_insert(session):
    _application(session)
    _attempt(session)
    assert session.query(ApplicationSubmissionAttempt).count() == 1


def test_application_submission_attempt_id_format_rejected(session):
    _application(session)
    with pytest.raises(IntegrityError):
        _attempt(session, attempt_id="BADID")


def test_application_submission_attempt_canonical_duplicate_consistency_rejected(session):
    """is_canonical=True with a non-null duplicate_of_attempt_id violates the
    paired CHECK constraint (data_dictionary.md §8a)."""
    _application(session)
    with pytest.raises(IntegrityError):
        _attempt(session, is_canonical=True, duplicate_of_attempt_id="ATT-0000099")


def test_application_submission_attempt_two_canonical_for_same_application_rejected(session):
    _application(session)
    _attempt(session, attempt_id="ATT-0000001", is_canonical=True)
    with pytest.raises(IntegrityError):
        _attempt(
            session,
            attempt_id="ATT-0000002",
            is_canonical=True,  # second canonical row for the same application
            submitted_at=datetime(2026, 1, 2),
        )


def test_application_submission_attempt_issue_type_enum_rejected(session):
    _application(session)
    with pytest.raises(IntegrityError):
        _attempt(session, issue_type="NotAnIssueType")


def _screening_run(
    session,
    run_id="SCRUN-0000001",
    app_id="APP-REQ-00001-CAND-000001",
    rule_id="SCR-0001",
    is_latest=True,
    score=85.0,
    decision="Pass",
):
    _application(session, app_id=app_id)
    # Insert the ScreeningRule directly rather than via the _screening_rule()
    # helper: that helper always calls _requisition() internally, which would
    # try to re-create the same REQ-00001/DEPT-0001/ACT-0001 rows _application()
    # already created above and collide on department.cost_center_code's
    # unique constraint.
    session.add(
        ScreeningRule(
            screening_rule_id=rule_id,
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
    session.commit()
    run = ScreeningRun(
        screening_run_id=run_id,
        application_id=app_id,
        screening_rule_id=rule_id,
        is_latest=is_latest,
        screening_rule_version=1,
        screening_skill_component=0.9,
        screening_experience_component=0.8,
        screening_education_component=1.0,
        screening_education_gate_passed=True,
        screening_score=score,
        screening_decision=decision,
        screening_explanation="Strong skill match; meets education gate.",
        computed_at=datetime(2026, 1, 2),
    )
    session.add(run)
    session.commit()
    return run


def test_screening_run_valid_insert(session):
    _screening_run(session)
    assert session.query(ScreeningRun).count() == 1


def test_screening_run_id_format_rejected(session):
    _application(session)
    session.add(
        ScreeningRule(
            screening_rule_id="SCR-0001",
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
    session.commit()
    session.add(
        ScreeningRun(
            screening_run_id="BADID",
            application_id="APP-REQ-00001-CAND-000001",
            screening_rule_id="SCR-0001",
            is_latest=True,
            screening_rule_version=1,
            screening_skill_component=0.9,
            screening_experience_component=0.8,
            screening_education_component=1.0,
            screening_education_gate_passed=True,
            screening_score=85.0,
            screening_decision="Pass",
            screening_explanation="x",
            computed_at=datetime(2026, 1, 2),
        )
    )
    with pytest.raises(IntegrityError):
        session.commit()


def test_screening_run_score_out_of_bounds_rejected(session):
    with pytest.raises(IntegrityError):
        _screening_run(session, score=150.0)


def test_screening_run_decision_enum_rejected(session):
    with pytest.raises(IntegrityError):
        _screening_run(session, decision="Maybe")


def test_screening_run_two_latest_for_same_application_rejected(session):
    """Structural backstop for 'at most one is_latest=true per application'
    (data_dictionary.md §8b)."""
    _screening_run(session, run_id="SCRUN-0000001", is_latest=True)
    session.add(
        ScreeningRun(
            screening_run_id="SCRUN-0000002",
            application_id="APP-REQ-00001-CAND-000001",
            screening_rule_id="SCR-0001",
            is_latest=True,  # second latest row for the same application
            screening_rule_version=1,
            screening_skill_component=0.9,
            screening_experience_component=0.85,
            screening_education_component=1.0,
            screening_education_gate_passed=True,
            screening_score=87.0,
            screening_decision="Pass",
            screening_explanation="Re-screened.",
            computed_at=datetime(2026, 1, 3),
        )
    )
    with pytest.raises(IntegrityError):
        session.commit()


def test_application_latest_screening_run_id_roundtrip(session):
    """Real insert-level proof (not just DDL) that the Application<->
    ScreeningRun circular FK works end-to-end via the documented three-step
    procedure: insert Application with latest_screening_run_id=NULL, insert
    the ScreeningRun row, then update Application to point at it
    (data_dictionary.md §8b)."""
    _screening_run(session)
    session.query(Application).filter_by(application_id="APP-REQ-00001-CAND-000001").update(
        {"latest_screening_run_id": "SCRUN-0000001", "screening_score": 85.0}
    )
    session.commit()
    updated = session.get(Application, "APP-REQ-00001-CAND-000001")
    assert updated.latest_screening_run_id == "SCRUN-0000001"


def test_application_latest_screening_run_id_bad_fk_rejected(session):
    _application(session)
    with pytest.raises(IntegrityError):
        session.query(Application).filter_by(application_id="APP-REQ-00001-CAND-000001").update(
            {"latest_screening_run_id": "SCRUN-9999999"}
        )
        session.commit()


# --- Unit 5: Interview, Feedback --------------------------------------------


def _interviewer(session, interviewer_id="IVR-0001"):
    _department(session)
    i = Interviewer(
        interviewer_id=interviewer_id,
        full_name="Ivy Reviewer",
        email=f"{interviewer_id.lower()}@example.com",
        department_id="DEPT-0001",
        title="Senior Engineer",
        is_active=True,
    )
    session.add(i)
    session.commit()
    return i


def _interview(
    session,
    interview_id="IVW-000001",
    app_id="APP-REQ-00001-CAND-000001",
    interviewer_id="IVR-0001",
    scheduled_start=datetime(2026, 2, 1, 10, 0),
    scheduled_end=datetime(2026, 2, 1, 11, 0),
    status="Scheduled",
):
    _application(session, app_id=app_id)
    # Insert Interviewer directly rather than via _interviewer(): that helper
    # always calls _department(), which would try to re-create DEPT-0001
    # (already created by _application() -> _requisition() above) and
    # collide on department.cost_center_code's unique constraint.
    session.add(
        Interviewer(
            interviewer_id=interviewer_id,
            full_name="Ivy Reviewer",
            email=f"{interviewer_id.lower()}@example.com",
            department_id="DEPT-0001",
            title="Senior Engineer",
            is_active=True,
        )
    )
    session.commit()
    iv = Interview(
        interview_id=interview_id,
        application_id=app_id,
        interviewer_id=interviewer_id,
        round_number=1,
        round_type="Technical",
        scheduled_start=scheduled_start,
        scheduled_end=scheduled_end,
        status=status,
        location_mode="Remote",
        created_at=datetime(2026, 1, 15),
        updated_at=datetime(2026, 1, 15),
    )
    session.add(iv)
    session.commit()
    return iv


def test_interview_valid_insert(session):
    _interview(session)
    assert session.query(Interview).count() == 1


def test_interview_id_format_rejected(session):
    _application(session)
    session.add(
        Interviewer(
            interviewer_id="IVR-0001",
            full_name="Ivy Reviewer",
            email="ivr-0001@example.com",
            department_id="DEPT-0001",
            title="Senior Engineer",
            is_active=True,
        )
    )
    session.commit()
    session.add(
        Interview(
            interview_id="BADID",
            application_id="APP-REQ-00001-CAND-000001",
            interviewer_id="IVR-0001",
            round_number=1,
            round_type="Technical",
            scheduled_start=datetime(2026, 2, 1, 10, 0),
            scheduled_end=datetime(2026, 2, 1, 11, 0),
            status="Scheduled",
            location_mode="Remote",
            created_at=datetime(2026, 1, 15),
            updated_at=datetime(2026, 1, 15),
        )
    )
    with pytest.raises(IntegrityError):
        session.commit()


def test_interview_scheduled_end_before_start_rejected(session):
    with pytest.raises(IntegrityError):
        _interview(
            session,
            scheduled_start=datetime(2026, 2, 1, 11, 0),
            scheduled_end=datetime(2026, 2, 1, 10, 0),
        )


def test_interview_round_type_enum_rejected(session):
    _application(session)
    session.add(
        Interviewer(
            interviewer_id="IVR-0001",
            full_name="Ivy Reviewer",
            email="ivr-0001@example.com",
            department_id="DEPT-0001",
            title="Senior Engineer",
            is_active=True,
        )
    )
    session.commit()
    session.add(
        Interview(
            interview_id="IVW-000001",
            application_id="APP-REQ-00001-CAND-000001",
            interviewer_id="IVR-0001",
            round_number=1,
            round_type="NotARoundType",
            scheduled_start=datetime(2026, 2, 1, 10, 0),
            scheduled_end=datetime(2026, 2, 1, 11, 0),
            status="Scheduled",
            location_mode="Remote",
            created_at=datetime(2026, 1, 15),
            updated_at=datetime(2026, 1, 15),
        )
    )
    with pytest.raises(IntegrityError):
        session.commit()


def test_interview_status_enum_rejected(session):
    with pytest.raises(IntegrityError):
        _interview(session, status="NotAStatus")


def test_interview_requires_existing_application(session):
    _interviewer(session)
    session.add(
        Interview(
            interview_id="IVW-000001",
            application_id="APP-REQ-99999-CAND-999999",  # does not exist
            interviewer_id="IVR-0001",
            round_number=1,
            round_type="Technical",
            scheduled_start=datetime(2026, 2, 1, 10, 0),
            scheduled_end=datetime(2026, 2, 1, 11, 0),
            status="Scheduled",
            location_mode="Remote",
            created_at=datetime(2026, 1, 15),
            updated_at=datetime(2026, 1, 15),
        )
    )
    with pytest.raises(IntegrityError):
        session.commit()


def _feedback(
    session,
    feedback_id="FBK-000001",
    interview_id="IVW-000001",
    interviewer_id="IVR-0001",
    overall_score=4,
    recommendation="Yes",
):
    _interview(session, interview_id=interview_id, interviewer_id=interviewer_id, status="Completed")
    fb = Feedback(
        feedback_id=feedback_id,
        interview_id=interview_id,
        interviewer_id=interviewer_id,
        recommendation=recommendation,
        overall_score=overall_score,
        strengths_text="Strong problem solving.",
        concerns_text=None,
        submitted_at=datetime(2026, 2, 1, 12, 0),
    )
    session.add(fb)
    session.commit()
    return fb


def test_feedback_valid_insert(session):
    _feedback(session)
    assert session.query(Feedback).count() == 1


def test_feedback_id_format_rejected(session):
    _interview(session, status="Completed")
    session.add(
        Feedback(
            feedback_id="BADID",
            interview_id="IVW-000001",
            interviewer_id="IVR-0001",
            recommendation="Yes",
            overall_score=4,
            submitted_at=datetime(2026, 2, 1, 12, 0),
        )
    )
    with pytest.raises(IntegrityError):
        session.commit()


def test_feedback_overall_score_out_of_bounds_rejected(session):
    with pytest.raises(IntegrityError):
        _feedback(session, overall_score=6)


def test_feedback_recommendation_enum_rejected(session):
    with pytest.raises(IntegrityError):
        _feedback(session, recommendation="Maybe")


def test_feedback_two_rows_for_same_interview_rejected(session):
    """Structural 1:1 enforcement — unique=True on Feedback.interview_id
    (data_dictionary.md §13)."""
    _feedback(session, feedback_id="FBK-000001")
    session.add(
        Feedback(
            feedback_id="FBK-000002",
            interview_id="IVW-000001",  # same interview again
            interviewer_id="IVR-0001",
            recommendation="No",
            overall_score=2,
            submitted_at=datetime(2026, 2, 1, 13, 0),
        )
    )
    with pytest.raises(IntegrityError):
        session.commit()


def test_feedback_requires_existing_interview(session):
    session.add(
        Feedback(
            feedback_id="FBK-000001",
            interview_id="IVW-999999",  # does not exist
            interviewer_id="IVR-0001",
            recommendation="Yes",
            overall_score=4,
            submitted_at=datetime(2026, 2, 1, 12, 0),
        )
    )
    with pytest.raises(IntegrityError):
        session.commit()


# --- Unit 6: Offer ----------------------------------------------------------


def _offer(
    session,
    offer_id="OFR-00001",
    app_id="APP-REQ-00001-CAND-000001",
    status="Drafted",
    proposed_salary=140000,
    approved_by_actor_id=None,
    approved_at=None,
    extended_at=None,
    decision_at=None,
    expiry_date=None,
):
    _application(session, app_id=app_id)
    if approved_by_actor_id is not None:
        # ACT-0001 already exists (created by _requisition() inside
        # _application() above) — use a distinct id for the approver so
        # this doesn't collide with it.
        _actor(session, actor_id=approved_by_actor_id, role="APPROVER")
    offer = Offer(
        offer_id=offer_id,
        application_id=app_id,
        proposed_salary=proposed_salary,
        currency="USD",
        equity_amount=None,
        status=status,
        approved_by_actor_id=approved_by_actor_id,
        approved_at=approved_at,
        extended_at=extended_at,
        decision_at=decision_at,
        expiry_date=expiry_date,
        created_at=datetime(2026, 1, 1),
    )
    session.add(offer)
    session.commit()
    return offer


def test_offer_valid_insert(session):
    _offer(session)
    assert session.query(Offer).count() == 1


def test_offer_id_format_rejected(session):
    _application(session)
    session.add(
        Offer(
            offer_id="BADID",
            application_id="APP-REQ-00001-CAND-000001",
            proposed_salary=140000,
            currency="USD",
            status="Drafted",
            created_at=datetime(2026, 1, 1),
        )
    )
    with pytest.raises(IntegrityError):
        session.commit()


def test_offer_negative_proposed_salary_rejected(session):
    with pytest.raises(IntegrityError):
        _offer(session, proposed_salary=-1)


def test_offer_status_enum_rejected(session):
    with pytest.raises(IntegrityError):
        _offer(session, status="NotAStatus")


def test_offer_two_rows_for_same_application_rejected(session):
    """Structural 1:1 enforcement — unique=True on Offer.application_id
    (data_dictionary.md §14)."""
    _offer(session, offer_id="OFR-00001")
    session.add(
        Offer(
            offer_id="OFR-00002",
            application_id="APP-REQ-00001-CAND-000001",  # same application again
            proposed_salary=145000,
            currency="USD",
            status="Drafted",
            created_at=datetime(2026, 1, 2),
        )
    )
    with pytest.raises(IntegrityError):
        session.commit()


def test_offer_approved_without_actor_and_timestamp_rejected(session):
    with pytest.raises(IntegrityError):
        _offer(session, status="Approved", approved_by_actor_id=None, approved_at=None)


def test_offer_approved_with_actor_and_timestamp_allowed(session):
    _offer(
        session,
        status="Approved",
        approved_by_actor_id="ACT-0002",
        approved_at=datetime(2026, 1, 5),
    )
    assert session.query(Offer).count() == 1


def test_offer_extended_without_extended_at_rejected(session):
    with pytest.raises(IntegrityError):
        _offer(
            session,
            status="Extended",
            approved_by_actor_id="ACT-0002",
            approved_at=datetime(2026, 1, 5),
            extended_at=None,
        )


def test_offer_extended_before_approved_rejected(session):
    with pytest.raises(IntegrityError):
        _offer(
            session,
            status="Extended",
            approved_by_actor_id="ACT-0002",
            approved_at=datetime(2026, 1, 10),
            extended_at=datetime(2026, 1, 5),  # before approved_at — invalid
        )


def test_offer_accepted_without_decision_at_rejected(session):
    with pytest.raises(IntegrityError):
        _offer(
            session,
            status="Accepted",
            approved_by_actor_id="ACT-0002",
            approved_at=datetime(2026, 1, 5),
            extended_at=datetime(2026, 1, 6),
            decision_at=None,
        )


def test_offer_decision_before_extended_rejected(session):
    with pytest.raises(IntegrityError):
        _offer(
            session,
            status="Accepted",
            approved_by_actor_id="ACT-0002",
            approved_at=datetime(2026, 1, 5),
            extended_at=datetime(2026, 1, 10),
            decision_at=datetime(2026, 1, 6),  # before extended_at — invalid
        )


def test_offer_expiry_before_extended_rejected(session):
    with pytest.raises(IntegrityError):
        _offer(
            session,
            status="Extended",
            approved_by_actor_id="ACT-0002",
            approved_at=datetime(2026, 1, 5),
            extended_at=datetime(2026, 1, 10),
            expiry_date=date(2026, 1, 1),  # before extended_at's date — invalid
        )


def test_offer_requires_existing_application(session):
    session.add(
        Offer(
            offer_id="OFR-00001",
            application_id="APP-REQ-99999-CAND-999999",  # does not exist
            proposed_salary=140000,
            currency="USD",
            status="Drafted",
            created_at=datetime(2026, 1, 1),
        )
    )
    with pytest.raises(IntegrityError):
        session.commit()


# --- Unit 7: RequisitionStatusHistory, ApplicationStageHistory, ------------
# --- OfferStatusHistory ------------------------------------------------------


def test_requisition_status_history_valid_insert(session):
    _requisition(session)
    session.add(
        RequisitionStatusHistory(
            history_id="RQH-000001",
            requisition_id="REQ-00001",
            from_status=None,
            to_status="Draft",
            changed_at=datetime(2026, 1, 1),
            actor_id="ACT-0001",
            reason_text=None,
        )
    )
    session.commit()
    assert session.query(RequisitionStatusHistory).count() == 1


def test_requisition_status_history_id_format_rejected(session):
    _requisition(session)
    session.add(
        RequisitionStatusHistory(
            history_id="BADID",
            requisition_id="REQ-00001",
            from_status=None,
            to_status="Draft",
            changed_at=datetime(2026, 1, 1),
            actor_id="ACT-0001",
        )
    )
    with pytest.raises(IntegrityError):
        session.commit()


def test_requisition_status_history_to_status_enum_rejected(session):
    _requisition(session)
    session.add(
        RequisitionStatusHistory(
            history_id="RQH-000001",
            requisition_id="REQ-00001",
            from_status=None,
            to_status="NotAStatus",
            changed_at=datetime(2026, 1, 1),
            actor_id="ACT-0001",
        )
    )
    with pytest.raises(IntegrityError):
        session.commit()


def test_requisition_status_history_requires_existing_requisition(session):
    _department(session)
    _actor(session)
    session.add(
        RequisitionStatusHistory(
            history_id="RQH-000001",
            requisition_id="REQ-99999",  # does not exist
            from_status=None,
            to_status="Draft",
            changed_at=datetime(2026, 1, 1),
            actor_id="ACT-0001",
        )
    )
    with pytest.raises(IntegrityError):
        session.commit()


def test_application_stage_history_valid_insert(session):
    _application(session)
    session.add(
        ApplicationStageHistory(
            history_id="APH-000001",
            application_id="APP-REQ-00001-CAND-000001",
            from_stage=None,
            to_stage="Applied",
            changed_at=datetime(2026, 1, 1),
            actor_id="ACT-0001",
            reason_text=None,
        )
    )
    session.commit()
    assert session.query(ApplicationStageHistory).count() == 1


def test_application_stage_history_id_format_rejected(session):
    _application(session)
    session.add(
        ApplicationStageHistory(
            history_id="BADID",
            application_id="APP-REQ-00001-CAND-000001",
            from_stage=None,
            to_stage="Applied",
            changed_at=datetime(2026, 1, 1),
            actor_id="ACT-0001",
        )
    )
    with pytest.raises(IntegrityError):
        session.commit()


def test_application_stage_history_to_stage_enum_rejected(session):
    _application(session)
    session.add(
        ApplicationStageHistory(
            history_id="APH-000001",
            application_id="APP-REQ-00001-CAND-000001",
            from_stage=None,
            to_stage="NotAStage",
            changed_at=datetime(2026, 1, 1),
            actor_id="ACT-0001",
        )
    )
    with pytest.raises(IntegrityError):
        session.commit()


def test_application_stage_history_requires_existing_application(session):
    _department(session)
    _actor(session)
    session.add(
        ApplicationStageHistory(
            history_id="APH-000001",
            application_id="APP-REQ-99999-CAND-999999",  # does not exist
            from_stage=None,
            to_stage="Applied",
            changed_at=datetime(2026, 1, 1),
            actor_id="ACT-0001",
        )
    )
    with pytest.raises(IntegrityError):
        session.commit()


def test_offer_status_history_valid_insert(session):
    _offer(session)
    session.add(
        OfferStatusHistory(
            history_id="OFH-000001",
            offer_id="OFR-00001",
            from_status=None,
            to_status="Drafted",
            changed_at=datetime(2026, 1, 1),
            actor_id="ACT-0001",
            reason_text=None,
        )
    )
    session.commit()
    assert session.query(OfferStatusHistory).count() == 1


def test_offer_status_history_id_format_rejected(session):
    _offer(session)
    session.add(
        OfferStatusHistory(
            history_id="BADID",
            offer_id="OFR-00001",
            from_status=None,
            to_status="Drafted",
            changed_at=datetime(2026, 1, 1),
            actor_id="ACT-0001",
        )
    )
    with pytest.raises(IntegrityError):
        session.commit()


def test_offer_status_history_to_status_enum_rejected(session):
    _offer(session)
    session.add(
        OfferStatusHistory(
            history_id="OFH-000001",
            offer_id="OFR-00001",
            from_status=None,
            to_status="NotAStatus",
            changed_at=datetime(2026, 1, 1),
            actor_id="ACT-0001",
        )
    )
    with pytest.raises(IntegrityError):
        session.commit()


def test_offer_status_history_requires_existing_offer(session):
    _department(session)
    _actor(session)
    session.add(
        OfferStatusHistory(
            history_id="OFH-000001",
            offer_id="OFR-99999",  # does not exist
            from_status=None,
            to_status="Drafted",
            changed_at=datetime(2026, 1, 1),
            actor_id="ACT-0001",
        )
    )
    with pytest.raises(IntegrityError):
        session.commit()
