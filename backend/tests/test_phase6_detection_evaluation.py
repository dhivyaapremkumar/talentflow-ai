"""Phase 6 tests — independent operational detection + offline ground-
truth evaluation. Covers every scenario this phase's prompt asked for:
all five detectors, exact TP/FP/FN on controlled fixtures, precision/
recall/F1 math (including empty-denominator conventions), micro-average
aggregation, duplicate-detection category filtering, ground-truth
leakage (including the new `detect.py` coverage), ground-truth
independence of detection, evaluation changing when ground truth
changes, read-only evaluation, starter/full end-to-end, and report
reproducibility.
"""

from pathlib import Path

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.data_generation.generator import generate_dataset, load_dataset
from app.data_generation.anomalies.injector import inject_all_anomalies
from app.data_generation.entities.reference_data import EPOCH
from app.db.models import AnomalyLabel, ApplicationSubmissionAttempt
from app.db.session import make_engine
from app.validation import detect, evaluate as evaluate_module, ground_truth_leakage
from app.validation.detect import ANOMALY_TYPES, run_detectors
from app.validation.evaluate import TN_NOT_COMPUTABLE_NOTE, _f1, _metrics_for_type, evaluate
from app.validation.gate import run_baseline_gate
from app.validation.report import Finding
from app.validation.runner import APP_ROOT

from datetime import timedelta

INJECTED_AT = EPOCH + timedelta(days=450)


def _build_injected_db(tmp_path, mode: str, seed: int = 20261022, db_name: str | None = None):
    dataset = generate_dataset(mode, seed=seed)
    db_path = tmp_path / f"{db_name or mode}.db"
    load_dataset(dataset, db_path)
    engine = make_engine(str(db_path))
    with Session(engine) as session:
        run_baseline_gate(session, dataset_mode=mode)
    with Session(engine) as session:
        inject_all_anomalies(session, seed, mode, injected_at=INJECTED_AT)
        session.commit()
    return engine, db_path


@pytest.fixture(scope="module")
def injected_starter_engine(tmp_path_factory):
    engine, _ = _build_injected_db(tmp_path_factory.mktemp("p6_starter"), "starter")
    return engine


@pytest.fixture(scope="module")
def injected_full_engine(tmp_path_factory):
    engine, _ = _build_injected_db(tmp_path_factory.mktemp("p6_full"), "full")
    return engine


# --- All five detectors, exact counts ---------------------------------------


def test_all_five_detectors_run_and_return_findings(injected_starter_engine):
    with Session(injected_starter_engine) as session:
        detections = run_detectors(session)
    assert set(detections.keys()) == set(ANOMALY_TYPES)
    for anomaly_type in ANOMALY_TYPES:
        assert isinstance(detections[anomaly_type], list)


def test_detector_counts_match_injected_counts_starter(injected_starter_engine):
    with Session(injected_starter_engine) as session:
        detections = run_detectors(session)
    assert len(detections["UnavailableInterviewer"]) == 3
    assert len(detections["DuplicateApplication"]) == 3
    assert len(detections["MissingFeedbackStageAdvanced"]) == 2
    assert len(detections["SalaryOutsideBand"]) == 1
    assert len(detections["ClosedReqActiveApplications"]) == 2


def test_detector_counts_match_injected_counts_full(injected_full_engine):
    with Session(injected_full_engine) as session:
        detections = run_detectors(session)
    assert len(detections["UnavailableInterviewer"]) == 15
    assert len(detections["DuplicateApplication"]) == 15
    assert len(detections["MissingFeedbackStageAdvanced"]) == 10
    assert len(detections["SalaryOutsideBand"]) == 6
    assert len(detections["ClosedReqActiveApplications"]) == 10


def test_duplicate_application_detection_reuses_val11_not_duplicated_logic():
    """detect.py must call select_detected_duplicates(), not redefine the
    grouping/sort algorithm."""
    import inspect

    source = inspect.getsource(detect)
    assert "select_detected_duplicates" in source
    assert "recompute_canonical_assignment" not in source  # reused via duplicate_submissions, not redefined


# --- Exact TP/FP/FN on controlled fixtures (pure math, no DB) ---------------


def test_metrics_perfect_match():
    m = _metrics_for_type("X", detected_ids={"a", "b", "c"}, truth_ids={"a", "b", "c"})
    assert (m.tp, m.fp, m.fn) == (3, 0, 0)
    assert m.precision == 1.0
    assert m.recall == 1.0
    assert m.f1 == 1.0
    assert m.tn is None
    assert m.tn_note == TN_NOT_COMPUTABLE_NOTE


def test_metrics_partial_overlap():
    m = _metrics_for_type("X", detected_ids={"a", "b", "x"}, truth_ids={"a", "b", "c"})
    assert (m.tp, m.fp, m.fn) == (2, 1, 1)
    assert m.false_positive_ids == ["x"]
    assert m.false_negative_ids == ["c"]
    assert m.true_positive_ids == ["a", "b"]
    assert abs(m.precision - 2 / 3) < 1e-9
    assert abs(m.recall - 2 / 3) < 1e-9
    assert abs(m.f1 - 2 / 3) < 1e-9


def test_one_detection_cannot_count_as_multiple_true_positives():
    """A detected entity_id appearing more than once (e.g. a detector
    firing for two independent reasons) must still count as exactly one
    TP, never two."""
    detected_ids = {"a"}  # simulates de-duplication already applied upstream
    m = _metrics_for_type("X", detected_ids=detected_ids, truth_ids={"a"})
    assert m.tp == 1


def test_evaluate_dedupes_detector_output_by_entity_id(monkeypatch):
    """evaluate() itself must dedupe raw Finding lists (which could in
    principle contain the same entity_id twice) before counting, not
    just trust an already-deduped input."""

    def fake_run_detectors(session):
        return {
            "UnavailableInterviewer": [
                Finding("VAL-06", "scheduling_conflicts", "interview", "IVW-1", "msg1", "violation"),
                Finding("VAL-06", "scheduling_conflicts", "interview", "IVW-1", "msg2", "violation"),
            ],
            "DuplicateApplication": [],
            "MissingFeedbackStageAdvanced": [],
            "SalaryOutsideBand": [],
            "ClosedReqActiveApplications": [],
        }

    monkeypatch.setattr(evaluate_module, "run_detectors", fake_run_detectors)

    class FakeAnomalyLabel:
        def __init__(self, anomaly_type, entity_id):
            self.anomaly_type = anomaly_type
            self.entity_id = entity_id

    class FakeSession:
        def execute(self, stmt):
            class Result:
                def scalars(self):
                    return [FakeAnomalyLabel("UnavailableInterviewer", "IVW-1")]

            return Result()

    report = evaluate(FakeSession())
    iv_metrics = next(t for t in report["per_type"] if t["anomaly_type"] == "UnavailableInterviewer")
    assert iv_metrics["tp"] == 1  # not 2, despite two Finding rows for the same entity_id


# --- Empty-denominator behavior ----------------------------------------------


def test_empty_denominator_no_detections_no_ground_truth():
    m = _metrics_for_type("X", detected_ids=set(), truth_ids=set())
    assert (m.tp, m.fp, m.fn) == (0, 0, 0)
    assert m.precision is None
    assert m.recall is None
    assert m.f1 is None


def test_empty_denominator_detector_silent_but_ground_truth_exists():
    """TP+FP=0 (no positive predictions) -> precision undefined (None).
    TP+FN>0 (ground truth exists) -> recall defined, = 0.0.
    F1 is None because one factor (precision) is undefined, not because
    both are zero."""
    m = _metrics_for_type("X", detected_ids=set(), truth_ids={"a", "b"})
    assert m.precision is None
    assert m.recall == 0.0
    assert m.f1 is None


def test_empty_denominator_no_ground_truth_but_detector_fires():
    """TP+FN=0 (no ground truth) -> recall undefined (None).
    TP+FP>0 -> precision defined, = 0.0. F1 is None (recall undefined)."""
    m = _metrics_for_type("X", detected_ids={"a", "b"}, truth_ids=set())
    assert m.recall is None
    assert m.precision == 0.0
    assert m.f1 is None


def test_both_precision_and_recall_defined_and_zero_gives_f1_zero_not_none():
    """TP=0 but FP>0 AND FN>0: both precision and recall are defined
    (not undefined) and equal to 0.0 - the documented convention says F1
    is explicitly 0.0 here, not None, and not a 0/0 crash."""
    m = _metrics_for_type("X", detected_ids={"x", "y"}, truth_ids={"c", "d"})
    assert m.tp == 0
    assert m.precision == 0.0
    assert m.recall == 0.0
    assert m.f1 == 0.0


def test_f1_helper_directly():
    assert _f1(None, None) is None
    assert _f1(None, 1.0) is None
    assert _f1(1.0, None) is None
    assert _f1(0.0, 0.0) == 0.0
    assert _f1(1.0, 1.0) == 1.0
    assert abs(_f1(0.5, 1.0) - (2 * 0.5 * 1.0 / 1.5)) < 1e-9


# --- Overall aggregation methodology -----------------------------------------


def test_overall_is_micro_average_not_macro_average(injected_full_engine):
    with Session(injected_full_engine) as session:
        report = evaluate(session)
    sum_tp = sum(t["tp"] for t in report["per_type"])
    sum_fp = sum(t["fp"] for t in report["per_type"])
    sum_fn = sum(t["fn"] for t in report["per_type"])
    assert report["overall"]["tp"] == sum_tp
    assert report["overall"]["fp"] == sum_fp
    assert report["overall"]["fn"] == sum_fn
    expected_precision = sum_tp / (sum_tp + sum_fp) if (sum_tp + sum_fp) else None
    assert report["overall"]["precision"] == expected_precision
    assert report["overall"]["aggregation_method"].startswith("micro-average")


# --- TN explicitly not fabricated --------------------------------------------


def test_tn_is_none_with_explanation_everywhere(injected_starter_engine):
    with Session(injected_starter_engine) as session:
        report = evaluate(session)
    for t in report["per_type"]:
        assert t["tn"] is None
        assert t["tn_note"] == TN_NOT_COMPUTABLE_NOTE
    assert report["overall"]["tn"] is None
    assert report["overall"]["tn_note"] == TN_NOT_COMPUTABLE_NOTE


# --- Starter and full end-to-end, exact perfect-detection result -----------


def test_starter_end_to_end_evaluation_perfect(injected_starter_engine):
    with Session(injected_starter_engine) as session:
        report = evaluate(session)
    assert report["overall"] == {
        "tp": 11, "fp": 0, "fn": 0, "tn": None,
        "precision": 1.0, "recall": 1.0, "f1": 1.0,
        "tn_note": TN_NOT_COMPUTABLE_NOTE,
        "aggregation_method": report["overall"]["aggregation_method"],
    }


def test_full_end_to_end_evaluation_perfect(injected_full_engine):
    with Session(injected_full_engine) as session:
        report = evaluate(session)
    assert report["overall"]["tp"] == 56
    assert report["overall"]["fp"] == 0
    assert report["overall"]["fn"] == 0
    assert report["overall"]["precision"] == 1.0
    assert report["overall"]["recall"] == 1.0
    assert report["overall"]["f1"] == 1.0


# --- Reproducibility ----------------------------------------------------------


def test_evaluation_report_reproducible_across_calls(injected_full_engine):
    with Session(injected_full_engine) as session:
        report_a = evaluate(session)
    with Session(injected_full_engine) as session:
        report_b = evaluate(session)
    assert report_a == report_b


# --- Read-only evaluation -----------------------------------------------------


def test_evaluation_is_read_only(tmp_path):
    engine, db_path = _build_injected_db(tmp_path, "starter", db_name="readonly_check")

    def _row_counts(session):
        from app.db.base import Base

        return {
            name: session.execute(select(func.count()).select_from(table)).scalar_one()
            for name, table in Base.metadata.tables.items()
        }

    with Session(engine) as session:
        before = _row_counts(session)
        evaluate(session)
        after = _row_counts(session)
    assert before == after


# --- Ground-truth independence of detection ----------------------------------


def test_detection_findings_unchanged_when_ground_truth_removed(tmp_path):
    engine, db_path = _build_injected_db(tmp_path, "starter", db_name="gt_removed")

    with Session(engine) as session:
        before = run_detectors(session)
        before_ids = {t: sorted(f.entity_id for f in findings) for t, findings in before.items()}

    with Session(engine) as session:
        # Null the referencing FK before deleting the referenced rows.
        session.execute(text("UPDATE application_submission_attempt SET ground_truth_label_id = NULL"))
        session.execute(text("DELETE FROM anomaly_label"))
        session.commit()

    with Session(engine) as session:
        anomaly_count = session.execute(select(func.count()).select_from(AnomalyLabel)).scalar_one()
        assert anomaly_count == 0

        after = run_detectors(session)
        after_ids = {t: sorted(f.entity_id for f in findings) for t, findings in after.items()}

    assert before_ids == after_ids


def test_evaluation_changes_when_ground_truth_changes_detection_does_not(tmp_path):
    engine, db_path = _build_injected_db(tmp_path, "starter", db_name="gt_changes")

    with Session(engine) as session:
        detections_before = run_detectors(session)
        report_before = evaluate(session)
    assert report_before["overall"]["tp"] == 11
    assert report_before["overall"]["fp"] == 0

    with Session(engine) as session:
        # Remove exactly one ground-truth label for a type the detector
        # still independently finds -> that entity flips from TP to FP.
        one_label = session.execute(
            select(AnomalyLabel).where(AnomalyLabel.anomaly_type == "SalaryOutsideBand")
        ).scalars().first()
        session.execute(text("DELETE FROM anomaly_label WHERE label_id = :id"), {"id": one_label.label_id})
        session.commit()

    with Session(engine) as session:
        detections_after = run_detectors(session)
        report_after = evaluate(session)

    detections_before_ids = {t: sorted(f.entity_id for f in fs) for t, fs in detections_before.items()}
    detections_after_ids = {t: sorted(f.entity_id for f in fs) for t, fs in detections_after.items()}
    assert detections_before_ids == detections_after_ids  # operational findings unchanged

    assert report_after["overall"]["tp"] == 10  # one fewer TP
    assert report_after["overall"]["fp"] == 1  # the same entity is now an FP


# --- Ground-truth leakage, extended for detect.py ----------------------------


def test_ground_truth_leakage_scan_includes_detect_py_file():
    assert "validation/detect.py" in ground_truth_leakage.SCAN_FILES


def test_ground_truth_leakage_scan_catches_violation_in_detect_py(tmp_path):
    scratch_root = tmp_path / "app"
    validation_dir = scratch_root / "validation"
    validation_dir.mkdir(parents=True)
    (validation_dir / "detect.py").write_text(
        "from app.db.models import AnomalyLabel\n", encoding="utf-8"
    )
    findings = ground_truth_leakage.check(scratch_root)
    assert len(findings) == 1
    assert findings[0].entity_id == "validation/detect.py"


def test_evaluate_module_explicitly_not_scanned_for_leakage():
    """validation/evaluate.py is permitted to read ground truth and must
    never be included in SCAN_ROOTS/SCAN_FILES."""
    assert "validation/evaluate.py" not in ground_truth_leakage.SCAN_FILES
    assert not any(root.startswith("validation") and root != "validation/rules" for root in ground_truth_leakage.SCAN_ROOTS)


def test_real_detect_py_has_zero_leakage_findings():
    findings = ground_truth_leakage.check(APP_ROOT)
    assert findings == []


# --- Detection happens fully before evaluation reads ground truth -----------


def test_detect_runs_to_completion_before_ground_truth_is_read(injected_starter_engine, monkeypatch):
    """Patches run_detectors to record a call marker, then checks that by
    the time evaluate() reads any AnomalyLabel row, run_detectors has
    already returned (its result is a plain dict, not a lazy generator
    that could interleave with the ground-truth read)."""
    call_order = []

    original_run_detectors = evaluate_module.run_detectors

    def tracking_run_detectors(session):
        result = original_run_detectors(session)
        call_order.append("detect_complete")
        return result

    monkeypatch.setattr(evaluate_module, "run_detectors", tracking_run_detectors)

    with Session(injected_starter_engine) as session:
        original_execute = session.execute
        def tracking_execute(stmt, *args, **kwargs):
            if "anomaly_label" in str(stmt).lower():
                call_order.append("ground_truth_read")
            return original_execute(stmt, *args, **kwargs)
        session.execute = tracking_execute

        evaluate(session)

    assert call_order[0] == "detect_complete"
    assert "ground_truth_read" in call_order
    assert call_order.index("detect_complete") < call_order.index("ground_truth_read")
