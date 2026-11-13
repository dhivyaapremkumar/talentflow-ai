"""Phase 9 tests — analytics/funnel.py and analytics/anomaly_summary.py.

Two fixture strategies, matching this project's established pattern
(test_phase6_detection_evaluation.py's `_build_injected_db`):

- A deterministically-generated, injected starter/full database (same
  seed the whole project uses) for "does this metric match a value
  computable by hand from the known seeded dataset" (implementation_plan.md's
  Phase 9 acceptance criterion) — numbers below were independently
  verified against this session's own generator run before being hard-
  coded here, not invented.
- Small controlled fixtures (empty database, single-row edge cases) for
  the safe-handling requirements (empty datasets, zero denominators,
  missing values) that the generated dataset doesn't naturally exercise.
"""

import json
from datetime import timedelta

import pytest
from sqlalchemy.orm import Session

from app.analytics.anomaly_summary import (
    ANOMALY_TYPES,
    evaluation_summary_from_report,
    export_operational_anomaly_summary,
    operational_anomaly_summary,
)
from app.analytics.funnel import (
    build_funnel_report,
    compute_duplicate_submission_rate,
    compute_interviewer_load,
    compute_offer_acceptance_rate,
    compute_requisition_funnel,
    compute_time_in_stage,
    export_funnel_report,
)
from app.data_generation.anomalies.injector import inject_all_anomalies
from app.data_generation.entities.reference_data import EPOCH
from app.data_generation.generator import generate_dataset, load_dataset
from app.db.base import Base
from app.db.models import AnomalyLabel, ApplicationSubmissionAttempt
from app.db.session import make_engine
from app.validation.evaluate import evaluate
from app.validation.gate import run_baseline_gate

INJECTED_AT = EPOCH + timedelta(days=450)


def _build_injected_db(tmp_path, mode: str, seed: int = 20261022):
    dataset = generate_dataset(mode, seed=seed)
    db_path = tmp_path / f"{mode}.db"
    load_dataset(dataset, db_path)
    engine = make_engine(str(db_path))
    with Session(engine) as session:
        run_baseline_gate(session, dataset_mode=mode)
    with Session(engine) as session:
        inject_all_anomalies(session, seed, mode, injected_at=INJECTED_AT)
        session.commit()
    return engine


@pytest.fixture(scope="module")
def starter_engine(tmp_path_factory):
    return _build_injected_db(tmp_path_factory.mktemp("p9_starter"), "starter")


@pytest.fixture(scope="module")
def full_engine(tmp_path_factory):
    return _build_injected_db(tmp_path_factory.mktemp("p9_full"), "full")


@pytest.fixture()
def empty_session():
    engine = make_engine(":memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


# --- Known-value tests against the real seeded dataset --------------------


def test_requisition_funnel_overall_matches_known_starter_counts(starter_engine):
    with Session(starter_engine) as session:
        rows = compute_requisition_funnel(session, group_by=None)
    assert len(rows) == 1
    reached = rows[0]["reached_counts"]
    assert reached["Applied"] == 150
    assert reached["Screening"] == 147
    assert reached["Interviewing"] == 22
    assert reached["Offer"] == 8
    assert reached["Hired"] == 6
    rates = rows[0]["conversion_rates"]
    assert rates["Applied->Screening"] == pytest.approx(147 / 150)
    assert rates["Screening->Interviewing"] == pytest.approx(22 / 147)
    assert rates["Interviewing->Offer"] == pytest.approx(8 / 22)
    assert rates["Offer->Hired"] == pytest.approx(6 / 8)


def test_requisition_funnel_by_requisition_sums_to_overall(starter_engine):
    with Session(starter_engine) as session:
        by_req = compute_requisition_funnel(session, group_by="requisition")
        overall = compute_requisition_funnel(session, group_by=None)[0]
    total_applied = sum(row["reached_counts"]["Applied"] for row in by_req)
    assert total_applied == overall["reached_counts"]["Applied"]


def test_requisition_funnel_by_department_groups_by_department_id(starter_engine):
    with Session(starter_engine) as session:
        rows = compute_requisition_funnel(session, group_by="department")
    assert all(row["group_key"].startswith("DEPT-") for row in rows)
    total_applied = sum(row["reached_counts"]["Applied"] for row in rows)
    assert total_applied == 150


def test_time_in_stage_reports_only_measurable_stages(starter_engine):
    with Session(starter_engine) as session:
        result = compute_time_in_stage(session)
    # "Hired" is terminal with no outgoing transition, so it is never a
    # "from" stage in any pair and must never appear here.
    assert "Hired" not in result
    for stage, stats in result.items():
        assert stats["sample_size"] > 0
        assert stats["mean_days"] >= 0


def test_offer_acceptance_rate_matches_known_starter_counts(starter_engine):
    with Session(starter_engine) as session:
        rows = compute_offer_acceptance_rate(session, group_by=None)
    assert len(rows) == 1
    assert rows[0]["accepted_count"] == 6
    assert rows[0]["extended_count"] == 8
    assert rows[0]["acceptance_rate"] == pytest.approx(0.75)


def test_duplicate_submission_rate_by_requisition_is_at_least_one(starter_engine):
    with Session(starter_engine) as session:
        rows = compute_duplicate_submission_rate(session, group_by="requisition")
    assert len(rows) == 10  # starter mode: 10 requisitions
    for row in rows:
        assert row["attempt_count"] >= row["canonical_application_count"]
        assert row["attempts_per_application"] >= 1.0


def test_interviewer_load_ratio_is_bounded_and_defined(starter_engine):
    with Session(starter_engine) as session:
        rows = compute_interviewer_load(session)
    assert len(rows) > 0
    for row in rows:
        if row["availability_slot_count"] == 0:
            assert row["load_ratio"] is None
        else:
            assert row["load_ratio"] >= 0


def test_operational_anomaly_summary_matches_known_starter_breakdown(starter_engine):
    with Session(starter_engine) as session:
        summary = operational_anomaly_summary(session)
    assert summary["counts_by_anomaly_type"] == {
        "UnavailableInterviewer": 3,
        "MissingFeedbackStageAdvanced": 2,
        "SalaryOutsideBand": 1,
        "DuplicateApplication": 3,
        "ClosedReqActiveApplications": 2,
    }
    assert summary["total_violations"] == 11


def test_operational_anomaly_summary_matches_known_full_breakdown(full_engine):
    with Session(full_engine) as session:
        summary = operational_anomaly_summary(session)
    assert summary["counts_by_anomaly_type"] == {
        "UnavailableInterviewer": 15,
        "MissingFeedbackStageAdvanced": 10,
        "SalaryOutsideBand": 6,
        "DuplicateApplication": 15,
        "ClosedReqActiveApplications": 10,
    }
    assert summary["total_violations"] == 56


# --- Ground-truth isolation (requirement 8/9) ------------------------------


def test_operational_anomaly_summary_unaffected_by_deleting_ground_truth(tmp_path):
    """Mirrors Phase 6's own ground-truth-independence test: deleting
    every AnomalyLabel row (and nulling the one FK referencing it) must
    not change a single operational count, because this function never
    reads AnomalyLabel in the first place.

    Uses its own isolated engine (not the shared module-scoped
    `starter_engine`) because this test destructively deletes data —
    sharing the module fixture here would starve every later test in
    this module of ground truth, exactly the kind of cross-test
    contamination `tmp_path` (function-scoped) avoids.
    """
    engine = _build_injected_db(tmp_path, "starter")
    with Session(engine) as session:
        before = operational_anomaly_summary(session)

        # ApplicationSubmissionAttempt.ground_truth_label_id is the only FK
        # referencing AnomalyLabel; null it first so the delete below does
        # not violate it.
        for attempt in session.query(ApplicationSubmissionAttempt).all():
            attempt.ground_truth_label_id = None
        session.query(AnomalyLabel).delete()
        session.commit()

        after = operational_anomaly_summary(session)

    assert before["counts_by_anomaly_type"] == after["counts_by_anomaly_type"]
    assert before["total_violations"] == after["total_violations"]


def test_anomaly_types_covers_all_five_seeded_types():
    assert set(ANOMALY_TYPES) == {
        "UnavailableInterviewer",
        "DuplicateApplication",
        "MissingFeedbackStageAdvanced",
        "SalaryOutsideBand",
        "ClosedReqActiveApplications",
    }


# --- Evaluation-report reuse (requirement 4) -------------------------------


def test_evaluation_summary_from_report_reuses_phase6_report_verbatim(starter_engine, tmp_path):
    with Session(starter_engine) as session:
        computed = evaluate(session)
    report_path = tmp_path / "starter.json"
    report_path.write_text(json.dumps(computed, indent=2), encoding="utf-8")

    loaded = evaluation_summary_from_report(report_path)
    assert loaded == computed
    assert loaded["overall"]["tp"] == 11
    assert loaded["overall"]["fp"] == 0
    assert loaded["overall"]["fn"] == 0


def test_evaluation_summary_from_report_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        evaluation_summary_from_report(tmp_path / "does_not_exist.json")


# --- Exports (requirement 5) -----------------------------------------------


def test_export_funnel_report_writes_json_and_csvs(starter_engine, tmp_path):
    with Session(starter_engine) as session:
        report = export_funnel_report(session, tmp_path)

    json_path = tmp_path / "funnel_report.json"
    assert json_path.exists()
    on_disk = json.loads(json_path.read_text(encoding="utf-8"))
    assert on_disk == report

    assert (tmp_path / "requisition_funnel_by_requisition.csv").exists()
    assert (tmp_path / "offer_acceptance_rate_by_department.csv").exists()
    assert (tmp_path / "duplicate_submission_rate_by_department.csv").exists()
    assert (tmp_path / "interviewer_load.csv").exists()


def test_export_operational_anomaly_summary_writes_json(starter_engine, tmp_path):
    with Session(starter_engine) as session:
        summary = export_operational_anomaly_summary(session, tmp_path)
    json_path = tmp_path / "anomaly_summary_operational.json"
    assert json_path.exists()
    on_disk = json.loads(json_path.read_text(encoding="utf-8"))
    assert on_disk["counts_by_anomaly_type"] == summary["counts_by_anomaly_type"]


# --- Safe handling of empty datasets and missing values (requirement 6) ---


def test_funnel_report_on_empty_database_returns_empty_structures(empty_session):
    report = build_funnel_report(empty_session)
    assert report["requisition_funnel_overall"] == []
    assert report["requisition_funnel_by_requisition"] == []
    assert report["time_in_stage"] == {}
    assert report["interviewer_load"] == []
    assert report["offer_acceptance_rate_overall"] == []
    assert report["duplicate_submission_rate_by_requisition"] == []


def test_offer_acceptance_rate_on_empty_database_has_no_rows(empty_session):
    assert compute_offer_acceptance_rate(empty_session, group_by="department") == []


def test_duplicate_submission_rate_on_empty_database_has_no_rows(empty_session):
    assert compute_duplicate_submission_rate(empty_session, group_by="requisition") == []


def test_interviewer_load_on_empty_database_has_no_rows(empty_session):
    assert compute_interviewer_load(empty_session) == []


def test_operational_anomaly_summary_on_empty_database_is_all_zero(empty_session):
    summary = operational_anomaly_summary(empty_session)
    assert summary["total_violations"] == 0
    assert all(count == 0 for count in summary["counts_by_anomaly_type"].values())


def test_invalid_group_by_raises_value_error(empty_session):
    with pytest.raises(ValueError):
        compute_requisition_funnel(empty_session, group_by="not_a_real_grouping")
    with pytest.raises(ValueError):
        compute_offer_acceptance_rate(empty_session, group_by="not_a_real_grouping")
    with pytest.raises(ValueError):
        compute_duplicate_submission_rate(empty_session, group_by="not_a_real_grouping")


def test_export_funnel_report_on_empty_database_still_writes_files(empty_session, tmp_path):
    report = export_funnel_report(empty_session, tmp_path)
    assert report["requisition_funnel_overall"] == []
    assert (tmp_path / "funnel_report.json").exists()
    # An empty list-of-dicts metric still gets a (header-less) CSV file,
    # not a crash from indexing row[0] on an empty list.
    assert (tmp_path / "requisition_funnel_overall.csv").exists()
