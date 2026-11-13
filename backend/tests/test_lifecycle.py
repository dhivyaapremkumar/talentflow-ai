"""Phase 8 service-layer tests — requisition_lifecycle.py,
application_lifecycle.py, scheduling.py, offer_lifecycle.py — run against
real, live code with controlled fixtures built directly for this file,
not the large generated dataset (per this phase's own testing
instruction).

Regression coverage for Phase 7 (screening.py/application_submission.py)
already exists in tests/test_services.py; regression coverage for
Phase 4 (validation) and Phase 6 (detection/evaluation) already exists in
tests/test_validation.py and tests/test_evaluation.py. This file adds
only Phase 8's new coverage; the completion report records the one full
`pytest tests/` run that proves all of it still passes together.
"""

from datetime import date, datetime

import pytest
from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.models import (
    Application,
    Candidate,
    Department,
    Interviewer,
    InterviewerAvailabilitySlot,
    JobRequisition,
    JobRequisitionSkill,
    Offer,
    ResumeArtifact,
    ScreeningRule,
    Skill,
    SystemActor,
)
from app.db.models.history import ApplicationStageHistory, OfferStatusHistory, RequisitionStatusHistory
from app.db.session import make_engine
from app.services.application_lifecycle import (
    ApplicationLifecycleError,
    reject,
    transition_application_stage,
    withdraw,
)
from app.services.offer_lifecycle import (
    OfferLifecycleError,
    create_offer,
    transition_offer,
)
from app.services.offer_lifecycle import approve as approve_offer
from app.services.requisition_lifecycle import (
    RequisitionLifecycleError,
    transition_requisition,
)
from app.services.requisition_lifecycle import approve as approve_requisition
from app.services.scheduling import (
    SchedulingError,
    schedule_interview,
    submit_feedback,
    transition_interview_status,
)


@pytest.fixture()
def session():
    engine = make_engine(":memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


# --- Shared fixture builders ---------------------------------------------


def _actors(session):
    session.add(Department(department_id="DEPT-0001", name="Engineering", cost_center_code="CC-0001", created_at=datetime(2026, 1, 1)))
    session.flush()
    session.add_all([
        SystemActor(actor_id="ACT-0001", full_name="Requester", role="BUSINESS_REQUESTER", department_id="DEPT-0001", email="req@example.com", is_active=True, created_at=datetime(2026, 1, 1)),
        SystemActor(actor_id="ACT-0002", full_name="Owner", role="PROCESS_OWNER", department_id="DEPT-0001", email="owner@example.com", is_active=True, created_at=datetime(2026, 1, 1)),
        SystemActor(actor_id="ACT-0003", full_name="Approver", role="APPROVER", department_id=None, email="approver@example.com", is_active=True, created_at=datetime(2026, 1, 1)),
        SystemActor(actor_id="ACT-0004", full_name="Admin", role="SYSTEM_ADMINISTRATOR", department_id=None, email="admin@example.com", is_active=True, created_at=datetime(2026, 1, 1)),
    ])
    session.commit()


def _requisition(session, req_id="REQ-00020", status="Draft", salary_min=100000, salary_max=150000, with_rule_and_skill=False):
    session.add(JobRequisition(
        requisition_id=req_id, department_id="DEPT-0001", title="Backend Engineer", level="Mid",
        employment_type="FullTime", status=status, salary_min=salary_min, salary_max=salary_max, headcount=1,
        requested_by_actor_id="ACT-0001", created_at=datetime(2026, 1, 1),
        opened_at=datetime(2026, 1, 2).date() if status in ("Open", "OnHold", "Closed") else None,
        closed_at=datetime(2026, 1, 5).date() if status in ("Closed", "Cancelled") else None,
    ))
    session.commit()
    if with_rule_and_skill:
        session.add(Skill(skill_id="SKL-9001", name="Python", category="Technical", is_active=True))
        session.commit()
        session.add(JobRequisitionSkill(requisition_id=req_id, skill_id="SKL-9001", min_proficiency_level="Advanced", is_mandatory=True, weight_pct=100))
        session.add(ScreeningRule(
            screening_rule_id="SCR-0020", requisition_id=req_id, is_current=True, version=1,
            min_years_experience=3.0, min_education_level="Bachelor", skill_weight_pct=50,
            experience_weight_pct=30, education_weight_pct=20, pass_threshold_score=70.0,
            created_at=datetime(2026, 1, 1),
        ))
        session.commit()
    return req_id


def _application(session, cand_id, req_id, stage="Applied", screening_computed_at=None, rejected_reason=None, withdrawn_at=None):
    session.add(Candidate(
        candidate_id=cand_id, full_name=f"Candidate {cand_id}", email=f"{cand_id.lower()}@example.com",
        phone=None, location_city="Remote", location_country="USA", years_experience=5.0,
        highest_education_level="Bachelor", source_channel="Website", created_at=datetime(2026, 1, 1),
    ))
    session.flush()
    resume_id = f"RES-{cand_id.split('-')[1]}"
    session.add(ResumeArtifact(
        resume_artifact_id=resume_id, candidate_id=cand_id, file_name="resume.pdf", file_format="PDF",
        parsed_years_experience=5.0, parsed_education_level="Bachelor", is_latest=True, uploaded_at=datetime(2026, 1, 1),
    ))
    session.commit()
    app_id = f"APP-{req_id}-{cand_id}"
    session.add(Application(
        application_id=app_id, candidate_id=cand_id, requisition_id=req_id, resume_artifact_id=resume_id,
        applied_at=datetime(2026, 1, 3), source_channel="Website", stage=stage,
        screening_computed_at=screening_computed_at, rejected_reason=rejected_reason, withdrawn_at=withdrawn_at,
        created_at=datetime(2026, 1, 3), updated_at=datetime(2026, 1, 3),
    ))
    session.commit()
    return app_id


def _interviewer(session, interviewer_id="IVR-0001", is_active=True):
    session.add(Interviewer(
        interviewer_id=interviewer_id, full_name="Pat Interviewer", email=f"{interviewer_id.lower()}@example.com",
        department_id="DEPT-0001", title="Senior Engineer", is_active=is_active,
    ))
    session.commit()
    return interviewer_id


def _availability_slot(session, slot_id, interviewer_id, start, end):
    session.add(InterviewerAvailabilitySlot(slot_id=slot_id, interviewer_id=interviewer_id, start_datetime=start, end_datetime=end, is_booked=False))
    session.commit()
    return slot_id


def _offer(session, offer_id, app_id, status="Drafted", proposed_salary=120000, created_at=None):
    session.add(Offer(
        offer_id=offer_id, application_id=app_id, proposed_salary=proposed_salary, currency="USD",
        equity_amount=None, status=status, created_at=created_at or datetime(2026, 1, 15),
    ))
    session.commit()
    return offer_id


# --- Requisition lifecycle -------------------------------------------------


def test_requisition_valid_transition(session):
    _actors(session)
    req_id = _requisition(session, status="Draft")
    history = transition_requisition(session, req_id, "PendingApproval", "ACT-0001", changed_at=datetime(2026, 1, 2))
    req = session.get(JobRequisition, req_id)
    assert req.status == "PendingApproval"
    assert history.from_status == "Draft"
    assert history.to_status == "PendingApproval"


def test_requisition_invalid_transition_rejected(session):
    _actors(session)
    req_id = _requisition(session, status="Draft")
    with pytest.raises(RequisitionLifecycleError):
        transition_requisition(session, req_id, "Open", "ACT-0002", changed_at=datetime(2026, 1, 2))
    req = session.get(JobRequisition, req_id)
    assert req.status == "Draft"


def test_requisition_approve_by_approver_succeeds(session):
    _actors(session)
    req_id = _requisition(session, status="PendingApproval")
    history = approve_requisition(session, req_id, "ACT-0003", changed_at=datetime(2026, 1, 2))
    req = session.get(JobRequisition, req_id)
    assert req.status == "Approved"
    assert history.to_status == "Approved"


def test_requisition_approve_by_non_approver_rejected_direct_call(session):
    """Hard-gate bypass attempt: calls requisition_lifecycle.approve()
    directly (no API/UI layer) with a PROCESS_OWNER actor and asserts the
    service layer rejects it before any row is written —
    validation_strategy.md §14's exact test design."""
    _actors(session)
    req_id = _requisition(session, status="PendingApproval")
    with pytest.raises(RequisitionLifecycleError):
        approve_requisition(session, req_id, "ACT-0002", changed_at=datetime(2026, 1, 2))
    req = session.get(JobRequisition, req_id)
    assert req.status == "PendingApproval"
    assert session.query(RequisitionStatusHistory).count() == 0


def test_requisition_open_requires_screening_rule_and_skill(session):
    _actors(session)
    req_id = _requisition(session, status="Approved", with_rule_and_skill=False)
    with pytest.raises(RequisitionLifecycleError):
        transition_requisition(session, req_id, "Open", "ACT-0002", changed_at=datetime(2026, 1, 2))
    req = session.get(JobRequisition, req_id)
    assert req.status == "Approved"


def test_requisition_open_succeeds_with_rule_and_skill(session):
    _actors(session)
    req_id = _requisition(session, status="Approved", with_rule_and_skill=True)
    transition_requisition(session, req_id, "Open", "ACT-0002", changed_at=datetime(2026, 1, 2))
    req = session.get(JobRequisition, req_id)
    assert req.status == "Open"
    assert req.opened_at == date(2026, 1, 2)


def test_requisition_transition_rollback_leaves_no_partial_state(session):
    _actors(session)
    req_id = _requisition(session, status="Draft")
    with pytest.raises(RequisitionLifecycleError):
        transition_requisition(session, req_id, "Cancelled", "ACT-9999", changed_at=datetime(2026, 1, 2))
    assert session.query(RequisitionStatusHistory).count() == 0
    req = session.get(JobRequisition, req_id)
    assert req.status == "Draft"


# --- Application lifecycle -------------------------------------------------


def test_application_valid_transition(session):
    _actors(session)
    req_id = _requisition(session, status="Open", with_rule_and_skill=True)
    app_id = _application(session, "CAND-000401", req_id, stage="Applied")
    transition_application_stage(session, app_id, "Screening", "ACT-0002", changed_at=datetime(2026, 1, 4))
    app = session.get(Application, app_id)
    assert app.stage == "Screening"


def test_application_invalid_transition_rejected(session):
    _actors(session)
    req_id = _requisition(session, status="Open", with_rule_and_skill=True)
    app_id = _application(session, "CAND-000402", req_id, stage="Applied")
    with pytest.raises(ApplicationLifecycleError):
        transition_application_stage(session, app_id, "Interviewing", "ACT-0002", changed_at=datetime(2026, 1, 4))
    app = session.get(Application, app_id)
    assert app.stage == "Applied"


def test_application_reject_requires_rejected_reason(session):
    _actors(session)
    req_id = _requisition(session, status="Open", with_rule_and_skill=True)
    app_id = _application(session, "CAND-000403", req_id, stage="Screening")
    with pytest.raises(ApplicationLifecycleError):
        transition_application_stage(session, app_id, "Rejected", "ACT-0002", changed_at=datetime(2026, 1, 4))
    app = session.get(Application, app_id)
    assert app.stage == "Screening"
    assert session.query(ApplicationStageHistory).count() == 0


def test_application_reject_succeeds_with_reason(session):
    _actors(session)
    req_id = _requisition(session, status="Open", with_rule_and_skill=True)
    app_id = _application(session, "CAND-000404", req_id, stage="Screening")
    reject(session, app_id, "ACT-0002", "failed screening", changed_at=datetime(2026, 1, 4))
    app = session.get(Application, app_id)
    assert app.stage == "Rejected"
    assert app.rejected_reason == "failed screening"


def test_application_withdraw_sets_withdrawn_at(session):
    _actors(session)
    req_id = _requisition(session, status="Open", with_rule_and_skill=True)
    app_id = _application(session, "CAND-000405", req_id, stage="Applied")
    now = datetime(2026, 1, 5)
    withdraw(session, app_id, "ACT-0002", changed_at=now)
    app = session.get(Application, app_id)
    assert app.stage == "Withdrawn"
    assert app.withdrawn_at == now


def test_application_transition_rollback_leaves_no_partial_state(session):
    _actors(session)
    req_id = _requisition(session, status="Open", with_rule_and_skill=True)
    app_id = _application(session, "CAND-000406", req_id, stage="Applied")
    with pytest.raises(ApplicationLifecycleError):
        transition_application_stage(session, app_id, "Screening", "ACT-9999", changed_at=datetime(2026, 1, 4))
    assert session.query(ApplicationStageHistory).count() == 0
    app = session.get(Application, app_id)
    assert app.stage == "Applied"


# --- Missing-feedback workflow enforcement ---------------------------------


def test_application_advance_to_offer_blocked_by_missing_feedback(session):
    _actors(session)
    req_id = _requisition(session, status="Open", with_rule_and_skill=True)
    app_id = _application(session, "CAND-000407", req_id, stage="Interviewing", screening_computed_at=datetime(2026, 1, 3))
    _interviewer(session, "IVR-0001")
    _availability_slot(session, "AVAIL-000001", "IVR-0001", datetime(2026, 1, 10, 9), datetime(2026, 1, 10, 17))
    interview = schedule_interview(
        session, app_id, "IVR-0001", "Technical",
        datetime(2026, 1, 10, 10), datetime(2026, 1, 10, 11), "Remote", created_at=datetime(2026, 1, 9),
    )
    transition_interview_status(session, interview.interview_id, "Completed", updated_at=datetime(2026, 1, 10, 11))
    with pytest.raises(ApplicationLifecycleError):
        transition_application_stage(session, app_id, "Offer", "ACT-0002", changed_at=datetime(2026, 1, 11))
    app = session.get(Application, app_id)
    assert app.stage == "Interviewing"


def test_application_advance_to_offer_succeeds_with_feedback(session):
    _actors(session)
    req_id = _requisition(session, status="Open", with_rule_and_skill=True)
    app_id = _application(session, "CAND-000408", req_id, stage="Interviewing", screening_computed_at=datetime(2026, 1, 3))
    _interviewer(session, "IVR-0001")
    _availability_slot(session, "AVAIL-000001", "IVR-0001", datetime(2026, 1, 10, 9), datetime(2026, 1, 10, 17))
    interview = schedule_interview(
        session, app_id, "IVR-0001", "Technical",
        datetime(2026, 1, 10, 10), datetime(2026, 1, 10, 11), "Remote", created_at=datetime(2026, 1, 9),
    )
    transition_interview_status(session, interview.interview_id, "Completed", updated_at=datetime(2026, 1, 10, 11))
    submit_feedback(session, interview.interview_id, "IVR-0001", "Yes", 4, datetime(2026, 1, 10, 11, 30))
    transition_application_stage(session, app_id, "Offer", "ACT-0002", changed_at=datetime(2026, 1, 11))
    app = session.get(Application, app_id)
    assert app.stage == "Offer"


# --- Interview scheduling ---------------------------------------------------


def test_schedule_interview_success_within_slot(session):
    _actors(session)
    req_id = _requisition(session, status="Open", with_rule_and_skill=True)
    app_id = _application(session, "CAND-000409", req_id, stage="Interviewing", screening_computed_at=datetime(2026, 1, 3))
    _interviewer(session, "IVR-0002")
    _availability_slot(session, "AVAIL-000002", "IVR-0002", datetime(2026, 1, 10, 9), datetime(2026, 1, 10, 17))
    interview = schedule_interview(
        session, app_id, "IVR-0002", "Phone",
        datetime(2026, 1, 10, 10), datetime(2026, 1, 10, 11), "Remote", created_at=datetime(2026, 1, 9),
    )
    assert interview.round_number == 1
    slot = session.get(InterviewerAvailabilitySlot, "AVAIL-000002")
    assert slot.is_booked is True


def test_schedule_interview_rejected_outside_availability(session):
    _actors(session)
    req_id = _requisition(session, status="Open", with_rule_and_skill=True)
    app_id = _application(session, "CAND-000410", req_id, stage="Interviewing", screening_computed_at=datetime(2026, 1, 3))
    _interviewer(session, "IVR-0003")
    _availability_slot(session, "AVAIL-000003", "IVR-0003", datetime(2026, 1, 10, 9), datetime(2026, 1, 10, 17))
    with pytest.raises(SchedulingError):
        schedule_interview(
            session, app_id, "IVR-0003", "Phone",
            datetime(2026, 1, 10, 18), datetime(2026, 1, 10, 19), "Remote", created_at=datetime(2026, 1, 9),
        )


def test_schedule_interview_rejected_overlap_with_existing(session):
    _actors(session)
    req_id = _requisition(session, status="Open", with_rule_and_skill=True)
    app_id = _application(session, "CAND-000411", req_id, stage="Interviewing", screening_computed_at=datetime(2026, 1, 3))
    _interviewer(session, "IVR-0004")
    _availability_slot(session, "AVAIL-000004", "IVR-0004", datetime(2026, 1, 10, 9), datetime(2026, 1, 10, 17))
    schedule_interview(
        session, app_id, "IVR-0004", "Phone",
        datetime(2026, 1, 10, 10), datetime(2026, 1, 10, 11), "Remote", created_at=datetime(2026, 1, 9),
    )
    with pytest.raises(SchedulingError):
        schedule_interview(
            session, app_id, "IVR-0004", "Technical",
            datetime(2026, 1, 10, 10, 30), datetime(2026, 1, 10, 11, 30), "Remote", created_at=datetime(2026, 1, 9),
        )


def test_schedule_interview_allows_reuse_after_cancellation(session):
    _actors(session)
    req_id = _requisition(session, status="Open", with_rule_and_skill=True)
    app_id = _application(session, "CAND-000412", req_id, stage="Interviewing", screening_computed_at=datetime(2026, 1, 3))
    _interviewer(session, "IVR-0005")
    _availability_slot(session, "AVAIL-000005", "IVR-0005", datetime(2026, 1, 10, 9), datetime(2026, 1, 10, 17))
    first = schedule_interview(
        session, app_id, "IVR-0005", "Phone",
        datetime(2026, 1, 10, 10), datetime(2026, 1, 10, 11), "Remote", created_at=datetime(2026, 1, 9),
    )
    transition_interview_status(session, first.interview_id, "Cancelled", updated_at=datetime(2026, 1, 9, 12))
    second = schedule_interview(
        session, app_id, "IVR-0005", "Technical",
        datetime(2026, 1, 10, 10), datetime(2026, 1, 10, 11), "Remote", created_at=datetime(2026, 1, 9),
    )
    assert second.round_number == 2


def test_schedule_interview_requires_interviewing_stage(session):
    _actors(session)
    req_id = _requisition(session, status="Open", with_rule_and_skill=True)
    app_id = _application(session, "CAND-000413", req_id, stage="Applied")
    _interviewer(session, "IVR-0006")
    _availability_slot(session, "AVAIL-000006", "IVR-0006", datetime(2026, 1, 10, 9), datetime(2026, 1, 10, 17))
    with pytest.raises(SchedulingError):
        schedule_interview(
            session, app_id, "IVR-0006", "Phone",
            datetime(2026, 1, 10, 10), datetime(2026, 1, 10, 11), "Remote", created_at=datetime(2026, 1, 9),
        )


def test_schedule_interview_round_number_contiguous(session):
    _actors(session)
    req_id = _requisition(session, status="Open", with_rule_and_skill=True)
    app_id = _application(session, "CAND-000414", req_id, stage="Interviewing", screening_computed_at=datetime(2026, 1, 3))
    _interviewer(session, "IVR-0007")
    _availability_slot(session, "AVAIL-000007", "IVR-0007", datetime(2026, 1, 10, 9), datetime(2026, 1, 10, 17))
    first = schedule_interview(
        session, app_id, "IVR-0007", "Phone",
        datetime(2026, 1, 10, 10), datetime(2026, 1, 10, 11), "Remote", created_at=datetime(2026, 1, 9),
    )
    second = schedule_interview(
        session, app_id, "IVR-0007", "Technical",
        datetime(2026, 1, 10, 13), datetime(2026, 1, 10, 14), "Remote", created_at=datetime(2026, 1, 9),
    )
    assert first.round_number == 1
    assert second.round_number == 2


def test_schedule_interview_rollback_leaves_no_partial_state(session):
    _actors(session)
    req_id = _requisition(session, status="Open", with_rule_and_skill=True)
    app_id = _application(session, "CAND-000415", req_id, stage="Interviewing", screening_computed_at=datetime(2026, 1, 3))
    _interviewer(session, "IVR-0008")
    _availability_slot(session, "AVAIL-000008", "IVR-0008", datetime(2026, 1, 10, 9), datetime(2026, 1, 10, 17))
    with pytest.raises(SchedulingError):
        schedule_interview(
            session, app_id, "IVR-0008", "Phone",
            datetime(2026, 1, 10, 18), datetime(2026, 1, 10, 19), "Remote", created_at=datetime(2026, 1, 9),
        )
    from app.db.models import Interview
    assert session.query(Interview).count() == 0
    slot = session.get(InterviewerAvailabilitySlot, "AVAIL-000008")
    assert slot.is_booked is False


# --- Offer lifecycle and salary-band enforcement ---------------------------


def test_offer_create_success(session):
    _actors(session)
    req_id = _requisition(session, status="Open", salary_min=100000, salary_max=150000)
    app_id = _application(session, "CAND-000420", req_id, stage="Offer")
    offer = create_offer(session, app_id, proposed_salary=120000, created_at=datetime(2026, 1, 15))
    assert offer.status == "Drafted"
    assert offer.proposed_salary == 120000


def test_offer_create_rejected_wrong_stage(session):
    _actors(session)
    req_id = _requisition(session, status="Open", salary_min=100000, salary_max=150000)
    app_id = _application(session, "CAND-000421", req_id, stage="Interviewing", screening_computed_at=datetime(2026, 1, 3))
    with pytest.raises(OfferLifecycleError):
        create_offer(session, app_id, proposed_salary=120000, created_at=datetime(2026, 1, 15))
    assert session.query(Offer).count() == 0


def test_offer_create_rejected_outside_salary_band(session):
    _actors(session)
    req_id = _requisition(session, status="Open", salary_min=100000, salary_max=150000)
    app_id = _application(session, "CAND-000422", req_id, stage="Offer")
    with pytest.raises(OfferLifecycleError):
        create_offer(session, app_id, proposed_salary=200000, created_at=datetime(2026, 1, 15))
    assert session.query(Offer).count() == 0


def test_offer_invalid_transition_rejected(session):
    _actors(session)
    req_id = _requisition(session, status="Open", salary_min=100000, salary_max=150000)
    app_id = _application(session, "CAND-000423", req_id, stage="Offer")
    offer_id = _offer(session, "OFR-00001", app_id, status="Drafted")
    with pytest.raises(OfferLifecycleError):
        transition_offer(session, offer_id, "Approved", "ACT-0003", changed_at=datetime(2026, 1, 16))
    offer = session.get(Offer, offer_id)
    assert offer.status == "Drafted"


def test_offer_approve_by_approver_succeeds(session):
    _actors(session)
    req_id = _requisition(session, status="Open", salary_min=100000, salary_max=150000)
    app_id = _application(session, "CAND-000424", req_id, stage="Offer")
    offer_id = _offer(session, "OFR-00002", app_id, status="PendingApproval")
    approve_offer(session, offer_id, "ACT-0003", changed_at=datetime(2026, 1, 16))
    offer = session.get(Offer, offer_id)
    assert offer.status == "Approved"
    assert offer.approved_by_actor_id == "ACT-0003"
    assert offer.approved_at == datetime(2026, 1, 16)


def test_offer_approve_by_non_approver_rejected_direct_call(session):
    """Hard-gate bypass attempt: calls offer_lifecycle.approve() directly
    (no API/UI layer) with a PROCESS_OWNER actor and asserts the service
    layer rejects it before any row is written."""
    _actors(session)
    req_id = _requisition(session, status="Open", salary_min=100000, salary_max=150000)
    app_id = _application(session, "CAND-000425", req_id, stage="Offer")
    offer_id = _offer(session, "OFR-00003", app_id, status="PendingApproval")
    with pytest.raises(OfferLifecycleError):
        approve_offer(session, offer_id, "ACT-0002", changed_at=datetime(2026, 1, 16))
    offer = session.get(Offer, offer_id)
    assert offer.status == "PendingApproval"
    assert offer.approved_by_actor_id is None
    assert session.query(OfferStatusHistory).count() == 0


def test_offer_approve_rejected_when_requisition_not_open(session):
    _actors(session)
    req_id = _requisition(session, status="OnHold", salary_min=100000, salary_max=150000)
    app_id = _application(session, "CAND-000426", req_id, stage="Offer")
    offer_id = _offer(session, "OFR-00004", app_id, status="PendingApproval")
    with pytest.raises(OfferLifecycleError):
        approve_offer(session, offer_id, "ACT-0003", changed_at=datetime(2026, 1, 16))
    offer = session.get(Offer, offer_id)
    assert offer.status == "PendingApproval"


def test_offer_full_happy_path_through_accepted_sets_hired(session):
    _actors(session)
    req_id = _requisition(session, status="Open", salary_min=100000, salary_max=150000)
    app_id = _application(session, "CAND-000427", req_id, stage="Offer")
    offer_id = _offer(session, "OFR-00005", app_id, status="Drafted")

    transition_offer(session, offer_id, "PendingApproval", "ACT-0002", changed_at=datetime(2026, 1, 16))
    transition_offer(session, offer_id, "Approved", "ACT-0003", changed_at=datetime(2026, 1, 17))
    transition_offer(
        session, offer_id, "Extended", "ACT-0002", changed_at=datetime(2026, 1, 18),
        expiry_date=date(2026, 2, 1),
    )
    transition_offer(session, offer_id, "Accepted", "ACT-0002", changed_at=datetime(2026, 1, 20))

    offer = session.get(Offer, offer_id)
    assert offer.status == "Accepted"
    assert offer.decision_at == datetime(2026, 1, 20)
    app = session.get(Application, app_id)
    assert app.stage == "Hired"
    history = session.query(ApplicationStageHistory).filter_by(application_id=app_id).all()
    assert len(history) == 1
    assert history[0].from_stage == "Offer"
    assert history[0].to_stage == "Hired"


def test_offer_transition_rollback_leaves_no_partial_state(session):
    _actors(session)
    req_id = _requisition(session, status="Open", salary_min=100000, salary_max=150000)
    app_id = _application(session, "CAND-000428", req_id, stage="Offer")
    offer_id = _offer(session, "OFR-00006", app_id, status="Drafted")
    with pytest.raises(OfferLifecycleError):
        transition_offer(session, offer_id, "PendingApproval", "ACT-9999", changed_at=datetime(2026, 1, 16))
    assert session.query(OfferStatusHistory).count() == 0
    offer = session.get(Offer, offer_id)
    assert offer.status == "Drafted"
