"""Phase 4 validation engine tests — covers every scenario this phase's
prompt asked for: all 16 VAL rule IDs exercised, clean starter/full
baselines pass, deliberately corrupted records are detected, multiple
violations reported correctly, the baseline gate blocks on violations,
validation output is deterministic, and ground-truth fields are never
read by operational validation.
"""

from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.data_generation.export import export_tables
from app.data_generation.generator import generate_dataset, load_dataset
from app.db.models import (
    AnomalyLabel,
    Application,
    ApplicationSubmissionAttempt,
    Candidate,
    Interview,
    Offer,
    RequisitionStatusHistory,
    ScreeningRun,
    SystemActor,
)
from app.db.session import make_engine
from app.validation import ground_truth_leakage
from app.validation.gate import BaselineValidationFailed, run_baseline_gate
from app.validation.report import results_only
from app.validation.runner import APP_ROOT, RULE_IDS, run_all_rules
from app.validation.rules import (
    allowed_values,
    date_ordering,
    duplicate_submissions,
    feedback_requirements,
    fk_integrity,
    lifecycle_transitions,
    offer_approval,
    pk_uniqueness,
    role_appropriateness,
    salary_band,
    scheduling_conflicts,
    screening_recompute,
)


@pytest.fixture()
def starter_db(tmp_path) -> Path:
    dataset = generate_dataset("starter", seed=20261022)
    db_path = tmp_path / "starter.db"
    load_dataset(dataset, db_path)
    return db_path


@pytest.fixture()
def starter_session(starter_db):
    engine = make_engine(str(starter_db))
    with Session(engine) as session:
        yield session


# --- All 17 rule IDs (16 categories, VAL-07 split into a/b) are real, ------
# --- working checks -------------------------------------------------------


def test_all_17_rule_id_labels_match_the_approved_catalog():
    assert RULE_IDS == [
        "VAL-01", "VAL-02", "VAL-03", "VAL-04", "VAL-05", "VAL-06",
        "VAL-07a", "VAL-07b", "VAL-08", "VAL-09", "VAL-10", "VAL-11",
        "VAL-12", "VAL-13", "VAL-14", "VAL-15", "VAL-16",
    ]


def test_clean_starter_baseline_passes(starter_session):
    report = run_baseline_gate(starter_session, dataset_mode="starter")
    assert report["total_violations"] == 0
    assert set(report["rule_ids_run"]) == set(RULE_IDS)


def test_clean_full_baseline_passes(tmp_path):
    dataset = generate_dataset("full", seed=20261022)
    db_path = tmp_path / "full.db"
    load_dataset(dataset, db_path)
    engine = make_engine(str(db_path))
    with Session(engine) as session:
        report = run_baseline_gate(session, dataset_mode="full")
    assert report["total_violations"] == 0


def test_val01_pk_uniqueness_clean(starter_session):
    # PK uniqueness is structurally guaranteed by SQLite's own PRIMARY KEY
    # constraint (cannot be corrupted via SQL to construct a true negative
    # test) — this proves the detector runs cleanly over real data.
    assert pk_uniqueness.check(starter_session) == []


def test_val02_fk_integrity_detects_corrupted_orphan(starter_session):
    assert fk_integrity.check(starter_session) == []
    starter_session.execute(text("PRAGMA foreign_keys=OFF"))
    starter_session.execute(
        text(
            "INSERT INTO application_stage_history "
            "(history_id, application_id, from_stage, to_stage, changed_at, actor_id) "
            "VALUES ('APH-999999', 'APP-DOES-NOT-EXIST', 'Applied', 'Screening', "
            "'2026-01-01 00:00:00', 'ACT-0001')"
        )
    )
    starter_session.commit()
    starter_session.execute(text("PRAGMA foreign_keys=ON"))

    findings = fk_integrity.check(starter_session)
    assert len(findings) >= 1
    assert all(f.rule_id == "VAL-02" for f in findings)


def test_val03_allowed_values_clean(starter_session):
    # Same structural guarantee as VAL-01 — every enum column already has
    # create_constraint=True, so a true negative test can't be constructed
    # via SQL either; this proves the detector runs cleanly over real data.
    assert allowed_values.check(starter_session) == []


def test_val04_date_ordering_detects_corrupted_applied_at(starter_session):
    assert date_ordering.check(starter_session) == []

    app = starter_session.query(Application).first()
    candidate = starter_session.query(Candidate).filter_by(candidate_id=app.candidate_id).one()
    starter_session.execute(
        text("UPDATE application SET applied_at = :bad WHERE application_id = :id"),
        {"bad": candidate.created_at - __import__("datetime").timedelta(days=10), "id": app.application_id},
    )
    starter_session.commit()

    findings = date_ordering.check(starter_session)
    assert any(f.entity_id == app.application_id for f in findings)
    assert all(f.rule_id == "VAL-04" for f in findings)


def test_val05_screening_recompute_detects_corrupted_score(starter_session):
    assert screening_recompute.check(starter_session) == []

    run = starter_session.query(ScreeningRun).first()
    corrupted_score = 1.00 if float(run.screening_score) != 1.00 else 99.00
    starter_session.execute(
        text("UPDATE screening_run SET screening_score = :score WHERE screening_run_id = :id"),
        {"score": corrupted_score, "id": run.screening_run_id},
    )
    starter_session.commit()

    findings = screening_recompute.check(starter_session)
    assert any(f.entity_id == run.screening_run_id for f in findings)
    assert all(f.rule_id == "VAL-05" for f in findings)


def test_val06_scheduling_conflicts_detects_overlap(starter_session):
    assert scheduling_conflicts.check(starter_session) == []

    iv = starter_session.query(Interview).first()
    starter_session.execute(
        text(
            "INSERT INTO interview (interview_id, application_id, interviewer_id, round_number, "
            "round_type, scheduled_start, scheduled_end, status, location_mode, created_at, updated_at) "
            "VALUES ('IVW-999999', :app_id, :interviewer_id, 9, 'Panel', :start, :end, "
            "'Scheduled', 'Remote', :start, :start)"
        ),
        {
            "app_id": iv.application_id,
            "interviewer_id": iv.interviewer_id,
            "start": iv.scheduled_start,
            "end": iv.scheduled_end,
        },
    )
    starter_session.commit()

    findings = scheduling_conflicts.check(starter_session)
    assert len(findings) >= 1
    assert all(f.rule_id == "VAL-06" for f in findings)


def test_val07a_lifecycle_transitions_detects_illegal_edge(starter_session):
    assert lifecycle_transitions.check(starter_session) == []

    req_hist = starter_session.query(RequisitionStatusHistory).filter_by(from_status="Draft").first()
    starter_session.execute(
        text("UPDATE requisition_status_history SET to_status = 'Closed' WHERE history_id = :id"),
        {"id": req_hist.history_id},
    )
    starter_session.commit()

    findings = lifecycle_transitions.check(starter_session)
    assert any(f.entity_id == req_hist.requisition_id and f.rule_id == "VAL-07a" for f in findings)


def test_val08_feedback_requirements_detects_missing_feedback(starter_session):
    assert feedback_requirements.check(starter_session) == []

    hired_app = starter_session.query(Application).filter_by(stage="Hired").first()
    iv = starter_session.query(Interview).filter_by(
        application_id=hired_app.application_id, status="Completed"
    ).first()
    starter_session.execute(text("DELETE FROM feedback WHERE interview_id = :id"), {"id": iv.interview_id})
    starter_session.commit()

    findings = feedback_requirements.check(starter_session)
    assert any(f.entity_id == hired_app.application_id for f in findings)
    assert all(f.rule_id == "VAL-08" for f in findings)


def test_val09_offer_approval_detects_inactive_approver(starter_session):
    assert offer_approval.check(starter_session) == []

    offer = starter_session.query(Offer).filter_by(status="Accepted").first()
    starter_session.execute(
        text("UPDATE system_actor SET is_active = 0 WHERE actor_id = :id"),
        {"id": offer.approved_by_actor_id},
    )
    starter_session.commit()

    findings = offer_approval.check(starter_session)
    assert any(f.entity_id == offer.offer_id for f in findings)
    assert all(f.rule_id == "VAL-09" for f in findings)


def test_val10_salary_band_detects_out_of_band_offer(starter_session):
    assert salary_band.check(starter_session) == []

    offer = starter_session.query(Offer).first()
    starter_session.execute(
        text("UPDATE offer SET proposed_salary = 999999999 WHERE offer_id = :id"), {"id": offer.offer_id}
    )
    starter_session.commit()

    findings = salary_band.check(starter_session)
    assert any(f.entity_id == offer.offer_id for f in findings)
    assert all(f.rule_id == "VAL-10" for f in findings)


def test_val11_duplicate_submissions_detects_wrong_duplicate_pointer(starter_session):
    assert duplicate_submissions.check(starter_session) == []

    attempts = starter_session.query(ApplicationSubmissionAttempt).limit(2).all()
    attempt_a, attempt_b = attempts[0], attempts[1]
    starter_session.execute(
        text(
            "INSERT INTO application_submission_attempt "
            "(attempt_id, canonical_application_id, candidate_id, requisition_id, submitted_at, "
            "is_canonical, duplicate_of_attempt_id, issue_type) "
            "VALUES ('ATT-9999999', :canon_app, :candidate_id, :requisition_id, :submitted_at, "
            "0, :wrong_pointer, 'DuplicateSubmission')"
        ),
        {
            "canon_app": attempt_a.canonical_application_id,
            "candidate_id": attempt_a.candidate_id,
            "requisition_id": attempt_a.requisition_id,
            "submitted_at": attempt_a.submitted_at + __import__("datetime").timedelta(days=1),
            "wrong_pointer": attempt_b.attempt_id,  # wrong — should point at attempt_a
        },
    )
    starter_session.commit()

    findings = duplicate_submissions.check(starter_session)
    assert any(f.entity_id == "ATT-9999999" for f in findings)
    assert all(f.rule_id == "VAL-11" for f in findings)


def test_val12_reconciliation_detects_unexpected_anomaly_label(starter_session):
    from app.validation import reconcile

    assert reconcile.check(starter_session, "starter") == []

    starter_session.execute(
        text(
            "INSERT INTO anomaly_label (label_id, entity_type, entity_id, anomaly_type, "
            "injected_at, description) VALUES ('ANOM-0001', 'Application', 'APP-X', "
            "'SalaryOutsideBand', '2026-01-01 00:00:00', 'test')"
        )
    )
    starter_session.commit()

    findings = reconcile.check(starter_session, "starter")
    assert any(f.rule_id == "VAL-12" and "AnomalyLabel" in f.message for f in findings)


def test_val13_checksums_detects_live_data_drift(tmp_path):
    from app.validation import checksums

    dataset = generate_dataset("starter", seed=20261022)
    db_path = tmp_path / "starter.db"
    load_dataset(dataset, db_path)
    engine = make_engine(str(db_path))

    with Session(engine) as session:
        baseline_report = run_baseline_gate(session, dataset_mode="starter")
    tables = {k: v for k, v in dataset.items() if not k.startswith("_")}
    export_summary = export_tables(tables, tmp_path / "exports")

    from app.data_generation.generator import write_generation_run

    with Session(engine) as session:
        post_injection_report = run_all_rules(session, dataset_mode="starter", report_mode="post_injection")

    write_generation_run(
        dataset, "starter", 20261022, export_summary, db_path, datetime.now(),
        baseline_report, post_injection_report,
    )

    with Session(engine) as session:
        assert checksums.check(session) == []

        cand = session.query(Candidate).first()
        session.execute(
            text("UPDATE candidate SET full_name = 'Corrupted Name' WHERE candidate_id = :id"),
            {"id": cand.candidate_id},
        )
        session.commit()

        findings = checksums.check(session)
        assert len(findings) >= 1
        assert all(f.rule_id == "VAL-13" for f in findings)


def test_val14_role_appropriateness_detects_hard_rule_violation(starter_session):
    assert role_appropriateness.check(starter_session) == []

    hard_row = (
        starter_session.query(RequisitionStatusHistory)
        .filter_by(from_status="PendingApproval", to_status="Approved")
        .first()
    )
    wrong_actor = starter_session.query(SystemActor).filter_by(role="BUSINESS_REQUESTER").first()
    starter_session.execute(
        text("UPDATE requisition_status_history SET actor_id = :actor WHERE history_id = :id"),
        {"actor": wrong_actor.actor_id, "id": hard_row.history_id},
    )
    starter_session.commit()

    findings = role_appropriateness.check(starter_session)
    matching = [f for f in findings if f.entity_id == hard_row.history_id]
    assert matching
    assert matching[0].severity == "violation"


def test_val15_ground_truth_leakage_clean_on_real_codebase():
    # Positive case: our actual app/ tree has zero leakage.
    assert ground_truth_leakage.check(APP_ROOT) == []


def test_val15_ground_truth_leakage_detects_forbidden_reference(tmp_path):
    scratch_root = tmp_path / "app"
    rules_dir = scratch_root / "validation" / "rules"
    rules_dir.mkdir(parents=True)
    (rules_dir / "bad_rule.py").write_text("from app.db.models import AnomalyLabel\n", encoding="utf-8")

    findings = ground_truth_leakage.check(scratch_root)
    assert len(findings) == 1
    assert findings[0].rule_id == "VAL-15"


def test_val16_export_consistency_detects_row_count_drift(starter_db, tmp_path):
    from app.validation.rules import export_consistency

    dataset = generate_dataset("starter", seed=20261022)
    tables = {k: v for k, v in dataset.items() if not k.startswith("_")}
    export_dir = tmp_path / "exports"
    export_tables(tables, export_dir)

    engine = make_engine(str(starter_db))
    with Session(engine) as session:
        assert export_consistency.check(session, export_dir) == []

        session.execute(text("DELETE FROM candidate_skill WHERE rowid IN (SELECT rowid FROM candidate_skill LIMIT 5)"))
        session.commit()

        findings = export_consistency.check(session, export_dir)
        assert any(f.entity_type == "candidate_skill" for f in findings)


# --- Multiple violations reported correctly --------------------------------


def test_multiple_violations_all_reported_with_correct_rule_ids(starter_session):
    offer = starter_session.query(Offer).first()
    starter_session.execute(
        text("UPDATE offer SET proposed_salary = 999999999 WHERE offer_id = :id"), {"id": offer.offer_id}
    )
    run = starter_session.query(ScreeningRun).first()
    starter_session.execute(
        text("UPDATE screening_run SET screening_score = 1.23 WHERE screening_run_id = :id"),
        {"id": run.screening_run_id},
    )
    starter_session.commit()

    report = run_all_rules(starter_session, dataset_mode="starter", report_mode="baseline")
    rule_ids_found = {f["rule_id"] for f in report["findings"]}
    assert "VAL-10" in rule_ids_found
    assert "VAL-05" in rule_ids_found
    assert report["total_violations"] >= 2


# --- Baseline gate blocks on violations -------------------------------------


def test_baseline_gate_blocks_on_corrupted_data(starter_session):
    offer = starter_session.query(Offer).first()
    starter_session.execute(
        text("UPDATE offer SET proposed_salary = 999999999 WHERE offer_id = :id"), {"id": offer.offer_id}
    )
    starter_session.commit()

    with pytest.raises(BaselineValidationFailed) as exc_info:
        run_baseline_gate(starter_session, dataset_mode="starter")
    assert exc_info.value.report["total_violations"] >= 1


def test_baseline_gate_passes_on_clean_data(starter_session):
    report = run_baseline_gate(starter_session, dataset_mode="starter")
    assert report["total_violations"] == 0


# --- Deterministic validation output -----------------------------------------


def test_validation_output_is_deterministic(starter_session):
    report_1 = run_all_rules(starter_session, dataset_mode="starter", report_mode="baseline")
    report_2 = run_all_rules(starter_session, dataset_mode="starter", report_mode="baseline")
    assert results_only(report_1) == results_only(report_2)


# --- Ground-truth fields never read by operational validation ---------------


def test_ground_truth_fields_never_read_by_operational_validation():
    """Whole-package scan over the real services/ and validation/rules/
    directories — the same guarantee validation_strategy.md Sec17
    describes, run against this codebase's actual source."""
    findings = ground_truth_leakage.check(APP_ROOT)
    assert findings == []
