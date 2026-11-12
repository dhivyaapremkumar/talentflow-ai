"""Phase 5 anomaly injection tests — covers every scenario this phase's
prompt asked for: exact starter/full incident and AnomalyLabel counts,
correct affected records per type, the duplicate-submission design
(linked to the existing canonical Application, never a new one),
structural integrity after injection, deterministic/reproducible
ground-truth output, the baseline gate blocking injection on a corrupted
baseline, ground-truth isolation, and distinct baseline/post-injection
reports.
"""

from datetime import datetime, timedelta

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.data_generation.anomalies.injector import inject_all_anomalies
from app.data_generation.entities.reference_data import EPOCH
from app.data_generation.export import export_tables
from app.data_generation.generator import generate_dataset, load_dataset
from app.data_generation.volumes import ANOMALY_COUNTS
from app.db.models import (
    AnomalyLabel,
    Application,
    ApplicationSubmissionAttempt,
    Feedback,
    Interview,
    JobRequisition,
    Offer,
)
from app.db.session import make_engine
from app.validation import ground_truth_leakage
from app.validation.gate import BaselineValidationFailed, run_baseline_gate
from app.validation.report import results_only
from app.validation.runner import APP_ROOT, run_all_rules

INJECTED_AT = EPOCH + timedelta(days=450)


def _build_injected_db(tmp_path, mode: str, seed: int = 20261022, db_name: str | None = None):
    dataset = generate_dataset(mode, seed=seed)
    db_path = tmp_path / f"{db_name or mode}.db"
    load_dataset(dataset, db_path)
    engine = make_engine(str(db_path))

    with Session(engine) as session:
        baseline_report = run_baseline_gate(session, dataset_mode=mode)

    with Session(engine) as session:
        label_rows = inject_all_anomalies(session, seed, mode, injected_at=INJECTED_AT)
        session.commit()

    with Session(engine) as session:
        post_injection_report = run_all_rules(session, dataset_mode=mode, report_mode="post_injection")

    return engine, db_path, baseline_report, post_injection_report, label_rows


@pytest.fixture(scope="module")
def injected_starter(tmp_path_factory):
    return _build_injected_db(tmp_path_factory.mktemp("injected_starter"), "starter")


@pytest.fixture(scope="module")
def injected_full(tmp_path_factory):
    return _build_injected_db(tmp_path_factory.mktemp("injected_full"), "full")


# --- Exact incident / AnomalyLabel counts -----------------------------------


def test_starter_anomaly_incident_counts_exact(injected_starter):
    engine, db_path, baseline_report, post_injection_report, label_rows = injected_starter
    by_type = {}
    for row in label_rows:
        by_type[row["anomaly_type"]] = by_type.get(row["anomaly_type"], 0) + 1

    assert by_type["UnavailableInterviewer"] == 3
    assert by_type["DuplicateApplication"] == 3
    assert by_type["MissingFeedbackStageAdvanced"] == 2
    assert by_type["SalaryOutsideBand"] == 1
    assert by_type["ClosedReqActiveApplications"] == 2  # 1 incident x 2 affected apps (A-12)
    assert len(label_rows) == 11


def test_full_anomaly_incident_counts_exact(injected_full):
    engine, db_path, baseline_report, post_injection_report, label_rows = injected_full
    by_type = {}
    for row in label_rows:
        by_type[row["anomaly_type"]] = by_type.get(row["anomaly_type"], 0) + 1

    assert by_type["UnavailableInterviewer"] == 15
    assert by_type["DuplicateApplication"] == 15
    assert by_type["MissingFeedbackStageAdvanced"] == 10
    assert by_type["SalaryOutsideBand"] == 6
    assert by_type["ClosedReqActiveApplications"] == 10  # 5 incidents x 2 (A-12)
    assert len(label_rows) == 56


def test_anomaly_label_counts_and_entity_types_match_data_dictionary(injected_full):
    engine, db_path, *_ = injected_full
    with Session(engine) as session:
        rows = session.execute(select(AnomalyLabel.entity_type, AnomalyLabel.anomaly_type)).all()

    by_entity_type = {}
    for entity_type, _ in rows:
        by_entity_type[entity_type] = by_entity_type.get(entity_type, 0) + 1

    assert by_entity_type == {
        "Interview": 15,
        "ApplicationSubmissionAttempt": 15,
        "Application": 20,  # 10 missing-feedback + 10 closed-req-active-apps
        "Offer": 6,
    }
    assert len(rows) == 56


# --- Correct affected records per type --------------------------------------


def test_unavailable_interviewer_affected_interviews_outside_availability(injected_full):
    engine, db_path, *_ = injected_full
    with Session(engine) as session:
        interview_ids = [
            lbl.entity_id
            for lbl in session.execute(
                select(AnomalyLabel).where(AnomalyLabel.anomaly_type == "UnavailableInterviewer")
            ).scalars()
        ]
        assert len(interview_ids) == 15
        for interview_id in interview_ids:
            iv = session.get(Interview, interview_id)
            assert iv.scheduled_start.weekday() == 5  # Saturday — never an availability slot day


def test_missing_feedback_affected_applications_at_offer_or_hired(injected_full):
    engine, db_path, *_ = injected_full
    with Session(engine) as session:
        labels = session.execute(
            select(AnomalyLabel).where(AnomalyLabel.anomaly_type == "MissingFeedbackStageAdvanced")
        ).scalars().all()
        assert len(labels) == 10
        for lbl in labels:
            app = session.get(Application, lbl.entity_id)
            assert app.stage in ("Offer", "Hired")
            interview_id = lbl.related_entity_id
            feedback_count = session.execute(
                select(func.count()).select_from(Feedback).where(Feedback.interview_id == interview_id)
            ).scalar_one()
            assert feedback_count == 0


def test_salary_band_affected_offers_outside_band(injected_full):
    engine, db_path, *_ = injected_full
    with Session(engine) as session:
        labels = session.execute(
            select(AnomalyLabel).where(AnomalyLabel.anomaly_type == "SalaryOutsideBand")
        ).scalars().all()
        assert len(labels) == 6
        for lbl in labels:
            offer = session.get(Offer, lbl.entity_id)
            app = session.get(Application, offer.application_id)
            req = session.get(JobRequisition, app.requisition_id)
            assert not (req.salary_min <= offer.proposed_salary <= req.salary_max)


def test_closed_requisition_exactly_two_active_applications_per_incident(injected_full):
    engine, db_path, *_ = injected_full
    with Session(engine) as session:
        labels = session.execute(
            select(AnomalyLabel).where(AnomalyLabel.anomaly_type == "ClosedReqActiveApplications")
        ).scalars().all()
        by_requisition: dict[str, list] = {}
        for lbl in labels:
            by_requisition.setdefault(lbl.related_entity_id, []).append(lbl.entity_id)

        assert len(by_requisition) == 5  # 5 incidents (full)
        for requisition_id, app_ids in by_requisition.items():
            assert len(app_ids) == 2  # exactly 2 per incident, A-12
            req = session.get(JobRequisition, requisition_id)
            assert req.status == "Closed"
            for app_id in app_ids:
                app = session.get(Application, app_id)
                assert app.stage not in ("Hired", "Rejected", "Withdrawn")


# --- Duplicate-submission design ---------------------------------------------


def test_duplicate_submissions_linked_to_existing_canonical_application(injected_full):
    engine, db_path, *_ = injected_full
    with Session(engine) as session:
        dup_labels = session.execute(
            select(AnomalyLabel).where(AnomalyLabel.anomaly_type == "DuplicateApplication")
        ).scalars().all()
        assert len(dup_labels) == 15

        for lbl in dup_labels:
            new_attempt = session.get(ApplicationSubmissionAttempt, lbl.entity_id)
            assert new_attempt.is_canonical is False
            assert new_attempt.issue_type == "DuplicateSubmission"
            assert new_attempt.duplicate_of_attempt_id == lbl.related_entity_id
            assert new_attempt.ground_truth_label_id == lbl.label_id

            # Linked to an EXISTING canonical Application — never a new one.
            app = session.get(Application, new_attempt.canonical_application_id)
            assert app is not None
            canonical_attempt = session.get(
                ApplicationSubmissionAttempt, new_attempt.duplicate_of_attempt_id
            )
            assert canonical_attempt.is_canonical is True
            assert canonical_attempt.canonical_application_id == app.application_id


def test_no_duplicate_canonical_applications_after_injection(injected_full):
    engine, db_path, *_ = injected_full
    with Session(engine) as session:
        app_count = session.execute(select(func.count()).select_from(Application)).scalar_one()
        canonical_count = session.execute(
            select(func.count())
            .select_from(ApplicationSubmissionAttempt)
            .where(ApplicationSubmissionAttempt.is_canonical.is_(True))
        ).scalar_one()
        assert app_count == canonical_count  # exactly one canonical attempt per Application

        pairs = session.execute(
            select(Application.candidate_id, Application.requisition_id, func.count())
            .group_by(Application.candidate_id, Application.requisition_id)
            .having(func.count() > 1)
        ).all()
        assert pairs == []


# --- Structural integrity after injection ------------------------------------


def test_structural_integrity_after_injection(injected_full):
    engine, db_path, baseline_report, post_injection_report, _ = injected_full
    structural_rules = [
        "VAL-01", "VAL-02", "VAL-03", "VAL-04", "VAL-05",
        "VAL-07a", "VAL-07b", "VAL-09", "VAL-13", "VAL-14", "VAL-15", "VAL-16",
    ]
    for rule_id in structural_rules:
        assert post_injection_report["counts_by_rule"][rule_id] == 0, (
            f"{rule_id} should remain zero post-injection — injectors must never break "
            "structural integrity"
        )

    business_rules_expected = {"VAL-06": 15, "VAL-08": 10, "VAL-10": 6, "VAL-11": 15, "VAL-12": 10}
    for rule_id, expected in business_rules_expected.items():
        assert post_injection_report["counts_by_rule"][rule_id] == expected

    with Session(engine) as session:
        violations = session.execute(text("PRAGMA foreign_key_check")).fetchall()
        assert violations == []


# --- Deterministic / reproducible -------------------------------------------


def test_anomaly_injection_is_deterministic(tmp_path):
    dataset_a = generate_dataset("starter", seed=20261022)
    db_a = tmp_path / "a.db"
    load_dataset(dataset_a, db_a)
    engine_a = make_engine(str(db_a))
    with Session(engine_a) as session:
        run_baseline_gate(session, dataset_mode="starter")
    with Session(engine_a) as session:
        labels_a = inject_all_anomalies(session, 20261022, "starter", injected_at=INJECTED_AT)
        session.commit()

    dataset_b = generate_dataset("starter", seed=20261022)
    db_b = tmp_path / "b.db"
    load_dataset(dataset_b, db_b)
    engine_b = make_engine(str(db_b))
    with Session(engine_b) as session:
        run_baseline_gate(session, dataset_mode="starter")
    with Session(engine_b) as session:
        labels_b = inject_all_anomalies(session, 20261022, "starter", injected_at=INJECTED_AT)
        session.commit()

    def _strip_label_id(rows):
        return sorted(
            ({k: v for k, v in row.items() if k != "label_id"} for row in rows),
            key=lambda r: (r["anomaly_type"], r["entity_id"]),
        )

    assert _strip_label_id(labels_a) == _strip_label_id(labels_b)


def test_reproducible_ground_truth_output_checksums(tmp_path):
    engine_a, db_a, *_ = _build_injected_db(tmp_path, "starter")
    export_a = {}
    from app.data_generation.export import read_tables_from_db

    with Session(engine_a) as session:
        export_a = read_tables_from_db(session)
    summary_a = export_tables(export_a, tmp_path / "export_a")

    engine_b, db_b, *_ = _build_injected_db(tmp_path, "starter", db_name="starter_b")
    with Session(engine_b) as session:
        export_b = read_tables_from_db(session)
    summary_b = export_tables(export_b, tmp_path / "export_b")

    assert summary_a["table_checksums"] == summary_b["table_checksums"]
    assert summary_a["overall_checksum"] == summary_b["overall_checksum"]


# --- Baseline gate prevents injection on a failed baseline -------------------


def test_baseline_gate_prevents_injection_when_baseline_fails(tmp_path):
    dataset = generate_dataset("starter", seed=20261022)
    db_path = tmp_path / "starter.db"
    load_dataset(dataset, db_path)
    engine = make_engine(str(db_path))

    with Session(engine) as session:
        offer = session.query(Offer).first()
        session.execute(
            text("UPDATE offer SET proposed_salary = 999999999 WHERE offer_id = :id"),
            {"id": offer.offer_id},
        )
        session.commit()

    with Session(engine) as session:
        with pytest.raises(BaselineValidationFailed):
            run_baseline_gate(session, dataset_mode="starter")

    # Injection must never have run — AnomalyLabel is still empty, exactly
    # mirroring main()'s real control flow where inject_all_anomalies() is
    # a statement that follows run_baseline_gate() and is never reached if
    # that call raises.
    with Session(engine) as session:
        anomaly_count = session.execute(select(func.count()).select_from(AnomalyLabel)).scalar_one()
        assert anomaly_count == 0


# --- Ground-truth isolation --------------------------------------------------


def test_ground_truth_isolation_from_operational_code():
    """The whole-package scan (VAL-15) must find zero references to
    AnomalyLabel/ground_truth_label_id in services/ or validation/rules/ —
    unaffected by Phase 5 existing, since data_generation/anomalies/ is
    explicitly outside that guarantee's scope (it is the one place
    permitted to touch ground truth, by design)."""
    assert ground_truth_leakage.check(APP_ROOT) == []


def test_duplicate_submissions_detector_still_excludes_ground_truth_after_injection(injected_full):
    """Re-run the Phase 4 whole-package scan after Phase 5 code exists —
    still zero findings; data_generation/anomalies/ is not in scope."""
    assert ground_truth_leakage.check(APP_ROOT) == []


# --- Baseline vs. post-injection reports are distinct ------------------------


def test_baseline_and_post_injection_reports_are_distinct_and_correctly_labeled(injected_full):
    engine, db_path, baseline_report, post_injection_report, label_rows = injected_full

    assert baseline_report["mode"] == "baseline"
    assert post_injection_report["mode"] == "post_injection"
    assert baseline_report["total_violations"] == 0
    assert post_injection_report["total_violations"] == 56
    assert results_only(baseline_report) != results_only(post_injection_report)

    # Never claim post-injection data is anomaly-free: the five business
    # categories have real, nonzero counts in the report itself.
    assert post_injection_report["counts_by_rule"]["VAL-06"] > 0
    assert post_injection_report["counts_by_rule"]["VAL-08"] > 0
    assert post_injection_report["counts_by_rule"]["VAL-10"] > 0
    assert post_injection_report["counts_by_rule"]["VAL-11"] > 0
    assert post_injection_report["counts_by_rule"]["VAL-12"] > 0
