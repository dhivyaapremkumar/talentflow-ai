"""Phase 10 — API layer tests. One test class per router: happy path,
the hard-enforcement rejection case (where applicable), and at least one
validation-error case per endpoint (implementation_plan.md's Phase 8
"Tests required" line, now actually exercised through the HTTP layer
this phase adds).

Uses `app.dependency_overrides[get_db]` to point every request at a
fresh, in-memory, controlled-fixture database (same style as
`test_lifecycle.py`) — never the generated starter/full dataset, so
these tests are independent of its incidental current state.
"""

from datetime import date, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.deps import get_db
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
from app.main import app


@pytest.fixture()
def session():
    # TestClient dispatches requests on a worker thread distinct from the
    # test's own thread; a plain in-memory SQLite connection is thread-
    # affine, so StaticPool + check_same_thread=False (not
    # app.db.session.make_engine's default) keeps one shared connection
    # usable from both.
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


@pytest.fixture()
def client(session):
    def _override():
        yield session

    app.dependency_overrides[get_db] = _override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _seed_actors(session):
    session.add(Department(department_id="DEPT-0001", name="Engineering", cost_center_code="CC-0001", created_at=datetime(2026, 1, 1)))
    session.flush()
    session.add_all([
        SystemActor(actor_id="ACT-0001", full_name="Requester", role="BUSINESS_REQUESTER", department_id="DEPT-0001", email="req@example.com", is_active=True, created_at=datetime(2026, 1, 1)),
        SystemActor(actor_id="ACT-0002", full_name="Owner", role="PROCESS_OWNER", department_id="DEPT-0001", email="owner@example.com", is_active=True, created_at=datetime(2026, 1, 1)),
        SystemActor(actor_id="ACT-0003", full_name="Approver", role="APPROVER", department_id=None, email="approver@example.com", is_active=True, created_at=datetime(2026, 1, 1)),
    ])
    session.commit()


def _seed_requisition(session, req_id="REQ-00020", status="Draft", salary_min=100000, salary_max=150000, with_rule_and_skill=True):
    session.add(JobRequisition(
        requisition_id=req_id, department_id="DEPT-0001", title="Backend Engineer", level="Mid",
        employment_type="FullTime", status=status, salary_min=salary_min, salary_max=salary_max, headcount=1,
        requested_by_actor_id="ACT-0001", created_at=datetime(2026, 1, 1),
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


def _seed_application(session, cand_id, req_id, stage="Applied", screening_computed_at=None):
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
        screening_computed_at=screening_computed_at, created_at=datetime(2026, 1, 3), updated_at=datetime(2026, 1, 3),
    ))
    session.commit()
    return app_id


def _seed_interviewer(session, interviewer_id="IVR-0001"):
    session.add(Interviewer(
        interviewer_id=interviewer_id, full_name="Pat Interviewer", email=f"{interviewer_id.lower()}@example.com",
        department_id="DEPT-0001", title="Senior Engineer", is_active=True,
    ))
    session.commit()
    return interviewer_id


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


class TestReference:
    def test_list_departments_actors_interviewers(self, client, session):
        _seed_actors(session)
        _seed_interviewer(session)
        assert client.get("/api/v1/departments").json()[0]["department_id"] == "DEPT-0001"
        actors = client.get("/api/v1/actors").json()
        assert {a["actor_id"] for a in actors} == {"ACT-0001", "ACT-0002", "ACT-0003"}
        assert client.get("/api/v1/interviewers").json()[0]["interviewer_id"] == "IVR-0001"


class TestRequisitions:
    def test_list_and_get(self, client, session):
        _seed_actors(session)
        _seed_requisition(session, status="Open")
        page = client.get("/api/v1/requisitions").json()
        assert page["total"] == 1
        detail = client.get("/api/v1/requisitions/REQ-00020").json()
        assert detail["status"] == "Open"

    def test_get_missing_returns_404_with_error_shape(self, client, session):
        _seed_actors(session)
        resp = client.get("/api/v1/requisitions/REQ-99999")
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "not_found"

    def test_transition_success(self, client, session):
        _seed_actors(session)
        _seed_requisition(session, status="PendingApproval")
        resp = client.post(
            "/api/v1/requisitions/REQ-00020/transition",
            json={"to_status": "Approved", "actor_id": "ACT-0003"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "Approved"

    def test_transition_hard_gate_rejects_non_approver(self, client, session):
        """The hard-enforcement rejection case, exercised through the HTTP
        layer — a PROCESS_OWNER cannot approve a requisition, even via a
        direct API call."""
        _seed_actors(session)
        _seed_requisition(session, status="PendingApproval")
        resp = client.post(
            "/api/v1/requisitions/REQ-00020/transition",
            json={"to_status": "Approved", "actor_id": "ACT-0002"},
        )
        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == "role_not_permitted"

    def test_transition_illegal_edge_is_validation_error(self, client, session):
        _seed_actors(session)
        _seed_requisition(session, status="Draft")
        resp = client.post(
            "/api/v1/requisitions/REQ-00020/transition",
            json={"to_status": "Open", "actor_id": "ACT-0001"},
        )
        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == "invalid_transition"


class TestCandidates:
    def test_list_search_get_skills_resumes(self, client, session):
        _seed_actors(session)
        _seed_requisition(session, status="Open")
        _seed_application(session, "CAND-000401", "REQ-00020")

        page = client.get("/api/v1/candidates").json()
        assert page["total"] == 1

        search_hit = client.get("/api/v1/candidates", params={"search": "cand-000401"}).json()
        assert search_hit["total"] == 1
        search_miss = client.get("/api/v1/candidates", params={"search": "nobody"}).json()
        assert search_miss["total"] == 0

        detail = client.get("/api/v1/candidates/CAND-000401").json()
        assert detail["candidate_id"] == "CAND-000401"

        assert client.get("/api/v1/candidates/CAND-000401/skills").json() == []
        resumes = client.get("/api/v1/candidates/CAND-000401/resumes").json()
        assert resumes[0]["resume_artifact_id"] == "RES-000401"

    def test_get_missing_candidate_404(self, client, session):
        _seed_actors(session)
        assert client.get("/api/v1/candidates/CAND-999999").status_code == 404


class TestApplications:
    def test_submit_screen_and_transition(self, client, session):
        _seed_actors(session)
        _seed_requisition(session, status="Open")
        session.add(Candidate(
            candidate_id="CAND-000402", full_name="Jamie Doe", email="jamie@example.com", phone=None,
            location_city="Remote", location_country="USA", years_experience=5.0,
            highest_education_level="Bachelor", source_channel="Website", created_at=datetime(2026, 1, 1),
        ))
        session.flush()
        session.add(ResumeArtifact(
            resume_artifact_id="RES-000402", candidate_id="CAND-000402", file_name="r.pdf", file_format="PDF",
            parsed_years_experience=5.0, parsed_education_level="Bachelor", is_latest=True, uploaded_at=datetime(2026, 1, 1),
        ))
        session.commit()

        submit_resp = client.post(
            "/api/v1/applications",
            json={"candidate_id": "CAND-000402", "requisition_id": "REQ-00020"},
        )
        assert submit_resp.status_code == 201
        app_id = submit_resp.json()["application_id"]
        assert submit_resp.json()["candidate_name"] == "Jamie Doe"

        screen_resp = client.post(f"/api/v1/applications/{app_id}/screen")
        assert screen_resp.status_code == 200
        assert screen_resp.json()["screening_decision"] in ("Pass", "Fail")

        transition_resp = client.post(
            f"/api/v1/applications/{app_id}/transition",
            json={"to_stage": "Screening", "actor_id": "ACT-0002"},
        )
        assert transition_resp.status_code == 200
        assert transition_resp.json()["stage"] == "Screening"

        runs = client.get(f"/api/v1/applications/{app_id}/screening-runs").json()
        assert len(runs) == 1
        attempts = client.get(f"/api/v1/applications/{app_id}/attempts").json()
        assert len(attempts) == 1

    def test_transition_without_required_rejected_reason_is_validation_error(self, client, session):
        _seed_actors(session)
        _seed_requisition(session, status="Open")
        app_id = _seed_application(session, "CAND-000403", "REQ-00020", stage="Screening")
        resp = client.post(
            f"/api/v1/applications/{app_id}/transition",
            json={"to_stage": "Rejected", "actor_id": "ACT-0002"},
        )
        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == "business_rule_violation"

    def test_filters_by_requisition_and_stage(self, client, session):
        _seed_actors(session)
        _seed_requisition(session, status="Open")
        _seed_application(session, "CAND-000404", "REQ-00020", stage="Applied")
        page = client.get("/api/v1/applications", params={"requisition_id": "REQ-00020", "stage": "Applied"}).json()
        assert page["total"] == 1


class TestInterviews:
    def test_schedule_status_and_feedback(self, client, session):
        _seed_actors(session)
        _seed_requisition(session, status="Open")
        app_id = _seed_application(session, "CAND-000405", "REQ-00020", stage="Interviewing", screening_computed_at=datetime(2026, 1, 3))
        _seed_interviewer(session, "IVR-0001")
        session.add(InterviewerAvailabilitySlot(
            slot_id="AVAIL-000001", interviewer_id="IVR-0001",
            start_datetime=datetime(2026, 12, 10, 9), end_datetime=datetime(2026, 12, 10, 17), is_booked=False,
        ))
        session.commit()

        availability = client.get("/api/v1/interviews/availability/IVR-0001").json()
        assert len(availability) == 1

        schedule_resp = client.post(
            "/api/v1/interviews",
            json={
                "application_id": app_id, "interviewer_id": "IVR-0001", "round_type": "Technical",
                "scheduled_start": "2026-12-10T10:00:00", "scheduled_end": "2026-12-10T11:00:00",
            },
        )
        assert schedule_resp.status_code == 201
        interview_id = schedule_resp.json()["interview_id"]

        conflict_resp = client.post(
            "/api/v1/interviews",
            json={
                "application_id": app_id, "interviewer_id": "IVR-0001", "round_type": "Phone",
                "scheduled_start": "2026-12-10T10:30:00", "scheduled_end": "2026-12-10T11:30:00",
            },
        )
        assert conflict_resp.status_code == 400

        status_resp = client.post(f"/api/v1/interviews/{interview_id}/status", json={"to_status": "Completed"})
        assert status_resp.status_code == 200
        assert status_resp.json()["status"] == "Completed"

        feedback_resp = client.post(
            f"/api/v1/interviews/{interview_id}/feedback",
            json={
                "interviewer_id": "IVR-0001", "recommendation": "Yes", "overall_score": 4,
                "submitted_at": "2026-12-10T11:30:00",
            },
        )
        assert feedback_resp.status_code == 201
        assert client.get(f"/api/v1/interviews/{interview_id}/feedback").json()["recommendation"] == "Yes"


class TestOffers:
    def test_create_outside_band_is_validation_error(self, client, session):
        _seed_actors(session)
        _seed_requisition(session, status="Open", salary_min=100000, salary_max=150000)
        app_id = _seed_application(session, "CAND-000406", "REQ-00020", stage="Offer")
        resp = client.post("/api/v1/offers", json={"application_id": app_id, "proposed_salary": 200000})
        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == "business_rule_violation"

    def test_create_and_transition_hard_gate(self, client, session):
        _seed_actors(session)
        _seed_requisition(session, status="Open", salary_min=100000, salary_max=150000)
        app_id = _seed_application(session, "CAND-000407", "REQ-00020", stage="Offer")
        create_resp = client.post("/api/v1/offers", json={"application_id": app_id, "proposed_salary": 120000})
        assert create_resp.status_code == 201
        offer_id = create_resp.json()["offer_id"]

        client.post(f"/api/v1/offers/{offer_id}/transition", json={"to_status": "PendingApproval", "actor_id": "ACT-0002"})

        rejected = client.post(f"/api/v1/offers/{offer_id}/transition", json={"to_status": "Approved", "actor_id": "ACT-0002"})
        assert rejected.status_code == 400
        assert rejected.json()["error"]["code"] == "role_not_permitted"

        approved = client.post(f"/api/v1/offers/{offer_id}/transition", json={"to_status": "Approved", "actor_id": "ACT-0003"})
        assert approved.status_code == 200
        assert approved.json()["status"] == "Approved"
        assert approved.json()["approved_by_actor_id"] == "ACT-0003"


class TestAnalytics:
    def test_funnel_and_anomaly_summary_on_empty_database(self, client, session):
        funnel = client.get("/api/v1/analytics/funnel").json()
        assert funnel["requisition_funnel_overall"] == []
        summary = client.get("/api/v1/analytics/anomaly-summary").json()
        assert summary["total_violations"] == 0

    def test_funnel_reflects_seeded_data(self, client, session):
        _seed_actors(session)
        _seed_requisition(session, status="Open")
        _seed_application(session, "CAND-000408", "REQ-00020", stage="Applied")
        funnel = client.get("/api/v1/analytics/funnel").json()
        assert funnel["requisition_funnel_overall"][0]["reached_counts"]["Applied"] == 1


class TestExports:
    def test_export_funnel_and_anomaly_summary_download_headers(self, client, session):
        _seed_actors(session)
        _seed_requisition(session, status="Open")
        _seed_application(session, "CAND-000409", "REQ-00020", stage="Applied")
        resp = client.get("/api/v1/exports/funnel.json")
        assert resp.status_code == 200
        assert "attachment" in resp.headers["content-disposition"]
        assert resp.json()["requisition_funnel_overall"][0]["reached_counts"]["Applied"] == 1

        resp2 = client.get("/api/v1/exports/anomaly-summary.json")
        assert resp2.status_code == 200
        assert "attachment" in resp2.headers["content-disposition"]


class TestValidationErrorContract:
    """B1 (Phase 10 pre-push review, P032/P033): FastAPI's built-in
    request-validation failures must use the same documented
    `{"error": {"code","message","field"}}` shape as every other 4xx/5xx,
    not the framework's default `{"detail": [...]}` body."""

    def test_missing_required_field_returns_documented_error_shape(self, client, session):
        _seed_actors(session)
        _seed_requisition(session, status="PendingApproval")
        resp = client.post("/api/v1/requisitions/REQ-00020/transition", json={"to_status": "Approved"})
        assert resp.status_code == 422
        body = resp.json()
        assert "detail" not in body
        assert body["error"]["code"] == "validation_error"
        assert body["error"]["field"] == "actor_id"
        assert "required" in body["error"]["message"].lower()

    def test_malformed_json_returns_documented_error_shape(self, client, session):
        resp = client.post(
            "/api/v1/offers",
            content=b"not json",
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 422
        body = resp.json()
        assert "detail" not in body
        assert body["error"]["code"] == "validation_error"
        assert body["error"]["message"]

    def test_existing_404_contract_unchanged(self, client, session):
        _seed_actors(session)
        resp = client.get("/api/v1/requisitions/REQ-99999")
        assert resp.status_code == 404
        assert resp.json() == {
            "error": {"code": "not_found", "message": "JobRequisition 'REQ-99999' does not exist", "field": None}
        }

    def test_existing_business_rule_error_contract_unchanged(self, client, session):
        _seed_actors(session)
        _seed_requisition(session, status="Draft")
        resp = client.post(
            "/api/v1/requisitions/REQ-00020/transition",
            json={"to_status": "Open", "actor_id": "ACT-0001"},
        )
        assert resp.status_code == 400
        body = resp.json()
        assert body["error"]["code"] == "invalid_transition"
        assert "field" in body["error"] and body["error"]["field"] is None
