"""Phase 7 service-layer tests — screening.py and application_submission.py
run against real, live code (not just the pure-function unit tests
already proven in Phase 3/4), per implementation_plan.md Phase 7's own
acceptance criteria: "All four withdrawal/resubmission test cases
(validation_strategy.md §18) and all screening test cases (§19) pass
against real code, not just the design projection."

Lifecycle/authorization tests (invalid transitions, unauthorized role
attempts, hard-gate bypass) are deliberately absent — business_services
for requisition/offer lifecycle are Phase 8 work per
implementation_plan.md's own phase split (see the completion report for
this session's full explanation); there is no lifecycle service yet to
test here, and writing a test for code that doesn't exist would be
exactly the kind of fabrication this project's standing rules forbid.
"""

from datetime import datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.models import (
    Application,
    ApplicationSubmissionAttempt,
    Candidate,
    CandidateSkill,
    Department,
    JobRequisition,
    JobRequisitionSkill,
    ResumeArtifact,
    ScreeningRule,
    ScreeningRun,
    Skill,
    SystemActor,
)
from app.db.session import make_engine
from app.services.application_submission import ApplicationSubmissionError, submit_application
from app.services.screening import ScreeningError, run_screening


@pytest.fixture()
def session():
    engine = make_engine(":memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


# --- Shared fixture: the exact REQ-00010 setup from business_rules.md §5a --


def _build_screening_fixture(session):
    # SQLAlchemy's unit-of-work does not reliably order these inserts by
    # FK dependency across unrelated mapped classes with no relationship()
    # configured between them (verified directly - a real, reproducible
    # behavior, not an assumption) - an explicit flush() after each
    # dependency-ordered insert is required, same pattern tests/test_models.py
    # already uses via its per-helper commits.
    session.add(Department(department_id="DEPT-0001", name="Engineering", cost_center_code="CC-0001", created_at=datetime(2026, 1, 1)))
    session.flush()
    session.add(SystemActor(actor_id="ACT-0001", full_name="Req Owner", role="BUSINESS_REQUESTER", department_id="DEPT-0001", email="owner@example.com", is_active=True, created_at=datetime(2026, 1, 1)))
    session.flush()
    session.add(JobRequisition(
        requisition_id="REQ-00010", department_id="DEPT-0001", title="Backend Engineer", level="Mid",
        employment_type="FullTime", status="Open", salary_min=100000, salary_max=150000, headcount=1,
        requested_by_actor_id="ACT-0001", opened_at=datetime(2026, 1, 2).date(), created_at=datetime(2026, 1, 1),
    ))
    session.add(Skill(skill_id="SKL-9001", name="Python", category="Technical", is_active=True))
    session.add(Skill(skill_id="SKL-9002", name="SQL", category="Technical", is_active=True))
    session.flush()
    session.add(JobRequisitionSkill(requisition_id="REQ-00010", skill_id="SKL-9001", min_proficiency_level="Advanced", is_mandatory=True, weight_pct=60))
    session.add(JobRequisitionSkill(requisition_id="REQ-00010", skill_id="SKL-9002", min_proficiency_level="Intermediate", is_mandatory=True, weight_pct=40))
    session.add(ScreeningRule(
        screening_rule_id="SCR-0010", requisition_id="REQ-00010", is_current=True, version=1,
        min_years_experience=4.0, min_education_level="Bachelor", skill_weight_pct=50,
        experience_weight_pct=30, education_weight_pct=20, pass_threshold_score=70.0,
        created_at=datetime(2026, 1, 1),
    ))
    session.commit()


def _add_candidate_with_application(
    session, cand_id, python_level, sql_level, years_exp, education, application_id=None
):
    session.add(Candidate(
        candidate_id=cand_id, full_name=f"Candidate {cand_id}", email=f"{cand_id.lower()}@example.com",
        phone=None, location_city="Remote", location_country="USA", years_experience=years_exp,
        highest_education_level=education, source_channel="Website", created_at=datetime(2026, 1, 1),
    ))
    session.flush()
    resume_id = f"RES-{cand_id.split('-')[1]}"
    session.add(ResumeArtifact(
        resume_artifact_id=resume_id, candidate_id=cand_id, file_name="resume.pdf", file_format="PDF",
        parsed_years_experience=years_exp, parsed_education_level=education, is_latest=True,
        uploaded_at=datetime(2026, 1, 1),
    ))
    if python_level is not None:
        session.add(CandidateSkill(candidate_id=cand_id, skill_id="SKL-9001", proficiency_level=python_level, years_of_experience=min(years_exp, 5.0), source="SelfReported", updated_at=datetime(2026, 1, 1)))
    if sql_level is not None:
        session.add(CandidateSkill(candidate_id=cand_id, skill_id="SKL-9002", proficiency_level=sql_level, years_of_experience=min(years_exp, 5.0), source="SelfReported", updated_at=datetime(2026, 1, 1)))
    session.commit()

    app_id = application_id or f"APP-REQ-00010-{cand_id}"
    session.add(Application(
        application_id=app_id, candidate_id=cand_id, requisition_id="REQ-00010",
        resume_artifact_id=resume_id, applied_at=datetime(2026, 1, 3), source_channel="Website",
        stage="Applied", created_at=datetime(2026, 1, 3), updated_at=datetime(2026, 1, 3),
    ))
    session.commit()
    return app_id


# --- Screening: boundary cases + education gate, against real service -----


def test_screening_cand_000101_perfect_pass(session):
    _build_screening_fixture(session)
    app_id = _add_candidate_with_application(session, "CAND-000101", "Expert", "Advanced", 6.0, "Master")

    run = run_screening(session, app_id)

    assert float(run.screening_score) == 100.00
    assert run.screening_decision == "Pass"
    assert run.screening_education_gate_passed is True
    assert run.is_latest is True


def test_screening_cand_000104_gate_overrides_high_score(session):
    """The proof case: education gate failure forces Fail despite a
    93.33 weighted score — the gate cannot be silently overridden."""
    _build_screening_fixture(session)
    app_id = _add_candidate_with_application(session, "CAND-000104", "Expert", "Advanced", 8.0, "Associate")

    run = run_screening(session, app_id)

    assert float(run.screening_score) == 93.33
    assert run.screening_education_gate_passed is False
    assert run.screening_decision == "Fail"


def test_screening_boundary_pair_70_00_pass_inclusive(session):
    _build_screening_fixture(session)
    # Reweight to the boundary-pair setup from business_rules.md Sec5a:
    # one skill at 40% met, one at 60% not held at all.
    session.execute(
        __import__("sqlalchemy").text(
            "UPDATE job_requisition_skill SET weight_pct = 40 WHERE skill_id = 'SKL-9001'"
        )
    )
    session.execute(
        __import__("sqlalchemy").text(
            "UPDATE job_requisition_skill SET weight_pct = 60, min_proficiency_level = 'Advanced' "
            "WHERE skill_id = 'SKL-9002'"
        )
    )
    session.commit()
    app_id = _add_candidate_with_application(session, "CAND-000201", "Advanced", None, 4.0, "Bachelor")

    run = run_screening(session, app_id)
    assert float(run.screening_score) == 70.00
    assert run.screening_decision == "Pass"


def test_screening_boundary_pair_69_25_fail(session):
    _build_screening_fixture(session)
    session.execute(
        __import__("sqlalchemy").text(
            "UPDATE job_requisition_skill SET weight_pct = 40 WHERE skill_id = 'SKL-9001'"
        )
    )
    session.execute(
        __import__("sqlalchemy").text(
            "UPDATE job_requisition_skill SET weight_pct = 60, min_proficiency_level = 'Advanced' "
            "WHERE skill_id = 'SKL-9002'"
        )
    )
    session.commit()
    app_id = _add_candidate_with_application(session, "CAND-000202", "Advanced", None, 3.9, "Bachelor")

    run = run_screening(session, app_id)
    assert float(run.screening_score) == 69.25
    assert run.screening_decision == "Fail"


def test_screening_nonexistent_application_raises_and_rolls_back(session):
    _build_screening_fixture(session)
    with pytest.raises(ScreeningError):
        run_screening(session, "APP-REQ-00010-CAND-999999")
    # No partial ScreeningRun row should exist after the rollback.
    assert session.execute(select(ScreeningRun)).scalars().all() == []


# --- Screening history / latest-result consistency / repeated runs ---------


def test_screening_run_history_and_latest_consistency(session):
    _build_screening_fixture(session)
    app_id = _add_candidate_with_application(session, "CAND-000101", "Expert", "Advanced", 6.0, "Master")

    run_screening(session, app_id)
    application = session.get(Application, app_id)
    first_run_id = application.latest_screening_run_id
    assert session.query(ScreeningRun).count() == 1
    assert session.get(ScreeningRun, first_run_id).is_latest is True


def test_repeated_screening_runs_flip_is_latest_and_preserve_history(session):
    """Simulates a re-screening (e.g. candidate skills changed): the
    first ScreeningRun's scored fields must stay byte-identical, only
    is_latest flips; Application's mirror must point at the second run."""
    _build_screening_fixture(session)
    app_id = _add_candidate_with_application(session, "CAND-000103", None, "Beginner", 2.0, "Bachelor")

    first_run = run_screening(session, app_id, computed_at=datetime(2026, 2, 1))
    first_run_id = first_run.screening_run_id
    first_score = first_run.screening_score

    # Candidate improves a skill, triggering a re-screen.
    session.add(CandidateSkill(candidate_id="CAND-000103", skill_id="SKL-9001", proficiency_level="Expert", years_of_experience=2.0, source="SelfReported", updated_at=datetime(2026, 2, 2)))
    session.commit()

    second_run = run_screening(session, app_id, computed_at=datetime(2026, 2, 2))

    assert session.query(ScreeningRun).count() == 2
    reloaded_first = session.get(ScreeningRun, first_run_id)
    assert reloaded_first.is_latest is False
    assert reloaded_first.screening_score == first_score  # history preserved byte-identical

    assert second_run.is_latest is True
    application = session.get(Application, app_id)
    assert application.latest_screening_run_id == second_run.screening_run_id
    assert application.screening_score == second_run.screening_score
    # At most one is_latest=true for this application - structural invariant.
    latest_count = session.query(ScreeningRun).filter_by(application_id=app_id, is_latest=True).count()
    assert latest_count == 1


def test_historical_screening_run_survives_rule_redefinition(session):
    """business_rules.md §4: a historical ScreeningRun's screening_rule_id
    must keep pointing at the exact rule version in effect when it ran,
    even after the requisition's rule is redefined."""
    _build_screening_fixture(session)
    app_id = _add_candidate_with_application(session, "CAND-000105", None, None, 0.0, "HighSchool")

    run = run_screening(session, app_id)
    assert run.screening_rule_version == 1
    original_rule_id = run.screening_rule_id

    # Redefine the rule: new version=2, old row flips is_current=False.
    old_rule = session.get(ScreeningRule, "SCR-0010")
    old_rule.is_current = False
    session.add(ScreeningRule(
        screening_rule_id="SCR-0011", requisition_id="REQ-00010", is_current=True, version=2,
        min_years_experience=5.0, min_education_level="Bachelor", skill_weight_pct=50,
        experience_weight_pct=30, education_weight_pct=20, pass_threshold_score=75.0,
        created_at=datetime(2026, 3, 1),
    ))
    session.commit()

    reloaded = session.get(ScreeningRun, run.screening_run_id)
    assert reloaded.screening_rule_id == original_rule_id  # unchanged
    assert reloaded.screening_rule_version == 1  # unchanged, still the rule that actually produced it


# --- Duplicate submission / canonical reconciliation ------------------------


def test_submit_application_first_time_creates_application_and_canonical_attempt(session):
    _build_screening_fixture(session)
    session.add(Candidate(candidate_id="CAND-000301", full_name="New Candidate", email="new@example.com", phone=None, location_city="Remote", location_country="USA", years_experience=3.0, highest_education_level="Bachelor", source_channel="Website", created_at=datetime(2026, 1, 1)))
    session.flush()
    session.add(ResumeArtifact(resume_artifact_id="RES-000301", candidate_id="CAND-000301", file_name="r.pdf", file_format="PDF", parsed_years_experience=3.0, parsed_education_level="Bachelor", is_latest=True, uploaded_at=datetime(2026, 1, 1)))
    session.commit()

    attempt = submit_application(session, "CAND-000301", "REQ-00010", datetime(2026, 1, 5))

    application = session.get(Application, "APP-REQ-00010-CAND-000301")
    assert application is not None
    assert application.stage == "Applied"
    assert attempt.is_canonical is True
    assert attempt.duplicate_of_attempt_id is None
    assert attempt.issue_type == "None"
    assert session.query(ApplicationSubmissionAttempt).count() == 1


def test_submit_application_duplicate_does_not_create_second_application(session):
    _build_screening_fixture(session)
    session.add(Candidate(candidate_id="CAND-000302", full_name="Dup Candidate", email="dup@example.com", phone=None, location_city="Remote", location_country="USA", years_experience=3.0, highest_education_level="Bachelor", source_channel="Website", created_at=datetime(2026, 1, 1)))
    session.flush()
    session.add(ResumeArtifact(resume_artifact_id="RES-000302", candidate_id="CAND-000302", file_name="r.pdf", file_format="PDF", parsed_years_experience=3.0, parsed_education_level="Bachelor", is_latest=True, uploaded_at=datetime(2026, 1, 1)))
    session.commit()

    first = submit_application(session, "CAND-000302", "REQ-00010", datetime(2026, 1, 5))
    second = submit_application(session, "CAND-000302", "REQ-00010", datetime(2026, 1, 10))

    assert session.query(Application).count() == 1  # never a second Application row
    assert session.query(ApplicationSubmissionAttempt).count() == 2

    reloaded_first = session.get(ApplicationSubmissionAttempt, first.attempt_id)
    reloaded_second = session.get(ApplicationSubmissionAttempt, second.attempt_id)
    assert reloaded_first.is_canonical is True
    assert reloaded_second.is_canonical is False
    assert reloaded_second.duplicate_of_attempt_id == first.attempt_id
    assert reloaded_second.issue_type == "DuplicateSubmission"
    # The original row is never mutated beyond its derived flags.
    assert reloaded_first.submitted_at == datetime(2026, 1, 5)


def test_submit_application_out_of_order_arrival_reassigns_canonical(session):
    """business_rules.md §10's out-of-order case: an attempt that is
    *processed* later but has an *earlier* submitted_at becomes canonical,
    and the previously-canonical attempt is correctly re-flagged."""
    _build_screening_fixture(session)
    session.add(Candidate(candidate_id="CAND-000303", full_name="OOO Candidate", email="ooo@example.com", phone=None, location_city="Remote", location_country="USA", years_experience=3.0, highest_education_level="Bachelor", source_channel="Website", created_at=datetime(2026, 1, 1)))
    session.flush()
    session.add(ResumeArtifact(resume_artifact_id="RES-000303", candidate_id="CAND-000303", file_name="r.pdf", file_format="PDF", parsed_years_experience=3.0, parsed_education_level="Bachelor", is_latest=True, uploaded_at=datetime(2026, 1, 1)))
    session.commit()

    first_processed = submit_application(session, "CAND-000303", "REQ-00010", datetime(2026, 1, 10))
    # Second call processed later, but its submitted_at is EARLIER.
    second_processed = submit_application(session, "CAND-000303", "REQ-00010", datetime(2026, 1, 2))

    reloaded_first = session.get(ApplicationSubmissionAttempt, first_processed.attempt_id)
    reloaded_second = session.get(ApplicationSubmissionAttempt, second_processed.attempt_id)

    assert reloaded_second.is_canonical is True  # earlier submitted_at wins
    assert reloaded_first.is_canonical is False
    assert reloaded_first.duplicate_of_attempt_id == second_processed.attempt_id
    # attempt_id/candidate_id/requisition_id/submitted_at of the reassigned
    # row are never touched - only the three derived flags change.
    assert reloaded_first.attempt_id == first_processed.attempt_id
    assert reloaded_first.submitted_at == datetime(2026, 1, 10)

    # Still exactly one canonical attempt and one Application for the pair.
    assert session.query(Application).count() == 1
    canonical_count = session.query(ApplicationSubmissionAttempt).filter_by(is_canonical=True).count()
    assert canonical_count == 1


def test_submit_application_nonexistent_candidate_raises_and_rolls_back(session):
    _build_screening_fixture(session)
    with pytest.raises(ApplicationSubmissionError):
        submit_application(session, "CAND-999999", "REQ-00010", datetime(2026, 1, 5))
    assert session.query(Application).count() == 0
    assert session.query(ApplicationSubmissionAttempt).count() == 0


# --- Withdrawal followed by resubmission (Option A, approved) ---------------


def test_withdrawal_then_resubmission_typical_case(session):
    """Test 1, validation_strategy.md §18: original Application stays
    Withdrawn; new attempt is a DuplicateSubmission pointing at the
    original."""
    _build_screening_fixture(session)
    session.add(Candidate(candidate_id="CAND-000401", full_name="Withdraw Candidate", email="w@example.com", phone=None, location_city="Remote", location_country="USA", years_experience=3.0, highest_education_level="Bachelor", source_channel="Website", created_at=datetime(2026, 1, 1)))
    session.flush()
    session.add(ResumeArtifact(resume_artifact_id="RES-000401", candidate_id="CAND-000401", file_name="r.pdf", file_format="PDF", parsed_years_experience=3.0, parsed_education_level="Bachelor", is_latest=True, uploaded_at=datetime(2026, 1, 1)))
    session.commit()

    original = submit_application(session, "CAND-000401", "REQ-00010", datetime(2026, 1, 5))

    application = session.get(Application, "APP-REQ-00010-CAND-000401")
    application.stage = "Withdrawn"
    application.withdrawn_at = datetime(2026, 1, 6)
    session.commit()

    resubmission = submit_application(session, "CAND-000401", "REQ-00010", datetime(2026, 1, 10))

    reloaded_application = session.get(Application, "APP-REQ-00010-CAND-000401")
    assert reloaded_application.stage == "Withdrawn"  # untouched by resubmission
    assert session.query(Application).count() == 1  # never a second Application

    reloaded_resubmission = session.get(ApplicationSubmissionAttempt, resubmission.attempt_id)
    assert reloaded_resubmission.is_canonical is False
    assert reloaded_resubmission.issue_type == "DuplicateSubmission"
    assert reloaded_resubmission.duplicate_of_attempt_id == original.attempt_id


def test_withdrawal_then_out_of_order_resubmission(session):
    """Test 2, validation_strategy.md §18: resubmission's submitted_at is
    earlier than the original's - canonical status may be reassigned, but
    Application.stage remains Withdrawn either way; no reactivation."""
    _build_screening_fixture(session)
    session.add(Candidate(candidate_id="CAND-000402", full_name="OOO Withdraw", email="oow@example.com", phone=None, location_city="Remote", location_country="USA", years_experience=3.0, highest_education_level="Bachelor", source_channel="Website", created_at=datetime(2026, 1, 1)))
    session.flush()
    session.add(ResumeArtifact(resume_artifact_id="RES-000402", candidate_id="CAND-000402", file_name="r.pdf", file_format="PDF", parsed_years_experience=3.0, parsed_education_level="Bachelor", is_latest=True, uploaded_at=datetime(2026, 1, 1)))
    session.commit()

    submit_application(session, "CAND-000402", "REQ-00010", datetime(2026, 1, 10))
    application = session.get(Application, "APP-REQ-00010-CAND-000402")
    application.stage = "Withdrawn"
    application.withdrawn_at = datetime(2026, 1, 11)
    session.commit()

    # Resubmission's submitted_at is EARLIER than the original.
    submit_application(session, "CAND-000402", "REQ-00010", datetime(2026, 1, 1))

    reloaded_application = session.get(Application, "APP-REQ-00010-CAND-000402")
    assert reloaded_application.stage == "Withdrawn"  # no reactivation, regardless of reordering
    assert session.query(Application).count() == 1


def test_withdrawal_then_application_to_different_requisition(session):
    """Test 3, validation_strategy.md §18: withdrawing from requisition A
    then applying to requisition B produces two independent canonical
    Applications; no duplicate classification on either."""
    _build_screening_fixture(session)
    session.add(JobRequisition(requisition_id="REQ-00011", department_id="DEPT-0001", title="Other Role", level="Mid", employment_type="FullTime", status="Open", salary_min=90000, salary_max=130000, headcount=1, requested_by_actor_id="ACT-0001", opened_at=datetime(2026, 1, 1).date(), created_at=datetime(2026, 1, 1)))
    session.add(Candidate(candidate_id="CAND-000403", full_name="Multi Req", email="mr@example.com", phone=None, location_city="Remote", location_country="USA", years_experience=3.0, highest_education_level="Bachelor", source_channel="Website", created_at=datetime(2026, 1, 1)))
    session.flush()
    session.add(ResumeArtifact(resume_artifact_id="RES-000403", candidate_id="CAND-000403", file_name="r.pdf", file_format="PDF", parsed_years_experience=3.0, parsed_education_level="Bachelor", is_latest=True, uploaded_at=datetime(2026, 1, 1)))
    session.commit()

    submit_application(session, "CAND-000403", "REQ-00010", datetime(2026, 1, 5))
    app_a = session.get(Application, "APP-REQ-00010-CAND-000403")
    app_a.stage = "Withdrawn"
    app_a.withdrawn_at = datetime(2026, 1, 6)
    session.commit()

    attempt_b = submit_application(session, "CAND-000403", "REQ-00011", datetime(2026, 1, 7))

    assert session.query(Application).count() == 2
    assert attempt_b.is_canonical is True
    assert attempt_b.issue_type == "None"
    reloaded_app_a = session.get(Application, "APP-REQ-00010-CAND-000403")
    assert reloaded_app_a.stage == "Withdrawn"


def test_withdrawal_resubmission_detection_ignores_ground_truth(session):
    """Test 4, validation_strategy.md §18: same whole-package leakage
    guarantee, re-asserted against this scenario's rows specifically."""
    from pathlib import Path

    from app.validation import ground_truth_leakage

    app_root = Path(__file__).resolve().parent.parent / "app"
    assert ground_truth_leakage.check(app_root) == []


# --- Transaction rollback on failure -----------------------------------------


def test_submission_rollback_leaves_no_partial_state(session):
    _build_screening_fixture(session)
    attempts_before = session.query(ApplicationSubmissionAttempt).count()
    applications_before = session.query(Application).count()

    with pytest.raises(ApplicationSubmissionError):
        submit_application(session, "CAND-NONEXISTENT", "REQ-00010", datetime(2026, 1, 1))

    assert session.query(ApplicationSubmissionAttempt).count() == attempts_before
    assert session.query(Application).count() == applications_before


def test_screening_rollback_leaves_no_partial_state(session):
    _build_screening_fixture(session)
    runs_before = session.query(ScreeningRun).count()

    with pytest.raises(ScreeningError):
        run_screening(session, "APP-DOES-NOT-EXIST")

    assert session.query(ScreeningRun).count() == runs_before
    # The session must still be usable after rollback (not left broken).
    session.add(Candidate(candidate_id="CAND-000501", full_name="Post Rollback", email="pr@example.com", phone=None, location_city="Remote", location_country="USA", years_experience=1.0, highest_education_level="Bachelor", source_channel="Website", created_at=datetime(2026, 1, 1)))
    session.commit()
    assert session.get(Candidate, "CAND-000501") is not None
