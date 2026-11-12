"""Phase 3 generator tests — covers every scenario the accelerated-
implementation prompt asked for: starter succeeds, all 22 tables
populated appropriately, FK relationships valid, same-seed reproducible,
different-seed differs, GenerationRun metadata correct, full-mode
volumes match requirements.
"""

import json
import sqlite3

from sqlalchemy.orm import Session

from app.data_generation.export import TABLE_ORDER, export_tables
from app.data_generation.generator import generate_dataset, load_dataset, write_generation_run
from app.data_generation.volumes import volumes_for_mode

ALL_22_TABLES = TABLE_ORDER + ["generation_run"]


def test_all_22_tables_accounted_for():
    assert len(ALL_22_TABLES) == 22


def test_starter_generation_succeeds_and_populates_tables_appropriately(tmp_path):
    dataset = generate_dataset("starter", seed=20261022)
    volumes = volumes_for_mode("starter")

    assert len(dataset["job_requisition"]) == volumes["job_requisition"] == 10
    assert len(dataset["candidate"]) == volumes["candidate"] == 100
    assert len(dataset["application"]) == volumes["application"] == 150
    assert len(dataset["interview"]) == volumes["interview"] == 30
    assert len(dataset["offer"]) == volumes["offer"] == 8
    # 1:1 shadow of Application, per data_dictionary.md Sec8b.
    assert len(dataset["screening_run"]) == len(dataset["application"])
    assert len(dataset["application_submission_attempt"]) == len(dataset["application"])
    # Baseline never injects anomalies — AnomalyLabel stays empty (Phase 5 only).
    assert dataset["anomaly_label"] == []

    for table in TABLE_ORDER:
        assert table in dataset, f"missing table {table} in generated dataset"


def test_full_mode_volumes_match_mandated_requirements():
    dataset = generate_dataset("full", seed=20261022)
    assert len(dataset["job_requisition"]) == 100
    assert len(dataset["candidate"]) == 2000
    assert len(dataset["application"]) == 3000
    assert len(dataset["interview"]) == 600
    assert len(dataset["offer"]) == 150
    assert len(dataset["screening_run"]) == 3000
    assert dataset["anomaly_label"] == []


def test_starter_fk_relationships_valid_in_loaded_database(tmp_path):
    dataset = generate_dataset("starter", seed=20261022)
    db_path = tmp_path / "starter.db"
    load_dataset(dataset, db_path)

    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys=ON")
    violations = conn.execute("PRAGMA foreign_key_check").fetchall()
    assert violations == [], f"FK violations found: {violations}"

    # Every Application must have its latest_screening_run_id resolved
    # (the two-phase insert's bulk UPDATE actually ran).
    null_runs = conn.execute(
        "SELECT COUNT(*) FROM application WHERE latest_screening_run_id IS NULL"
    ).fetchone()[0]
    assert null_runs == 0

    # No application in a non-terminal stage against a Closed/Cancelled
    # requisition — that would be the ClosedReqActiveApplications anomaly,
    # which the clean baseline must never produce.
    leaked_anomaly = conn.execute(
        """
        SELECT COUNT(*) FROM application a JOIN job_requisition r
            ON a.requisition_id = r.requisition_id
        WHERE r.status IN ('Closed', 'Cancelled')
          AND a.stage NOT IN ('Hired', 'Rejected', 'Withdrawn')
        """
    ).fetchone()[0]
    assert leaked_anomaly == 0

    # Every requisition's required-skill weights sum to exactly 100.
    bad_weights = conn.execute(
        "SELECT requisition_id FROM job_requisition_skill GROUP BY requisition_id "
        "HAVING SUM(weight_pct) != 100"
    ).fetchall()
    assert bad_weights == []

    # Every Completed interview has feedback.
    missing_feedback = conn.execute(
        """
        SELECT COUNT(*) FROM interview i WHERE i.status = 'Completed'
          AND NOT EXISTS (SELECT 1 FROM feedback f WHERE f.interview_id = i.interview_id)
        """
    ).fetchone()[0]
    assert missing_feedback == 0

    conn.close()


def test_same_seed_produces_identical_checksums(tmp_path):
    dataset_a = generate_dataset("starter", seed=20261022)
    dataset_b = generate_dataset("starter", seed=20261022)

    tables_a = {k: v for k, v in dataset_a.items() if not k.startswith("_")}
    tables_b = {k: v for k, v in dataset_b.items() if not k.startswith("_")}

    summary_a = export_tables(tables_a, tmp_path / "export_a")
    summary_b = export_tables(tables_b, tmp_path / "export_b")

    assert summary_a["overall_checksum"] == summary_b["overall_checksum"]
    assert summary_a["table_checksums"] == summary_b["table_checksums"]
    assert summary_a["entity_counts"] == summary_b["entity_counts"]


def test_different_seed_produces_different_checksum(tmp_path):
    dataset_a = generate_dataset("starter", seed=20261022)
    dataset_b = generate_dataset("starter", seed=99999)

    tables_a = {k: v for k, v in dataset_a.items() if not k.startswith("_")}
    tables_b = {k: v for k, v in dataset_b.items() if not k.startswith("_")}

    summary_a = export_tables(tables_a, tmp_path / "export_a")
    summary_b = export_tables(tables_b, tmp_path / "export_b")

    assert summary_a["overall_checksum"] != summary_b["overall_checksum"]


def test_generation_run_metadata_correct(tmp_path):
    dataset = generate_dataset("starter", seed=20261022)
    db_path = tmp_path / "starter.db"
    load_dataset(dataset, db_path)

    tables = {k: v for k, v in dataset.items() if not k.startswith("_")}
    export_summary = export_tables(tables, tmp_path / "exports")

    from datetime import datetime

    from app.db.session import make_engine
    from app.validation.gate import run_baseline_gate

    from app.validation.runner import run_all_rules

    engine = make_engine(str(db_path))
    with Session(engine) as session:
        baseline_report = run_baseline_gate(session, dataset_mode="starter")
    assert baseline_report["total_violations"] == 0

    with Session(engine) as session:
        post_injection_report = run_all_rules(session, dataset_mode="starter", report_mode="post_injection")

    run_row = write_generation_run(
        dataset, "starter", 20261022, export_summary, db_path, datetime.now(),
        baseline_report, post_injection_report,
    )

    assert run_row["run_id"] == "GEN-0001"
    assert run_row["seed"] == 20261022
    assert run_row["mode"] == "starter"
    assert run_row["overall_checksum"] == export_summary["overall_checksum"]
    assert json.loads(run_row["entity_counts_json"]) == export_summary["entity_counts"]
    assert json.loads(run_row["table_checksums_json"]) == export_summary["table_checksums"]

    conn = sqlite3.connect(str(db_path))
    row = conn.execute(
        "SELECT seed, mode, generated_by_actor_id, overall_checksum FROM generation_run"
    ).fetchone()
    assert row == (20261022, "starter", run_row["generated_by_actor_id"], export_summary["overall_checksum"])
    conn.close()


def test_generation_run_rejects_non_mandated_seed(tmp_path):
    """The GenerationRun.seed CHECK constraint only accepts 20261022 — a
    non-mandated seed can be used to generate content in memory (tested
    above) but can never be persisted as an official run."""
    import pytest
    from sqlalchemy.exc import IntegrityError

    dataset = generate_dataset("starter", seed=99999)
    db_path = tmp_path / "starter.db"
    load_dataset(dataset, db_path)
    tables = {k: v for k, v in dataset.items() if not k.startswith("_")}
    export_summary = export_tables(tables, tmp_path / "exports")

    from datetime import datetime

    from app.db.session import make_engine
    from app.validation.gate import run_baseline_gate
    from app.validation.runner import run_all_rules

    engine = make_engine(str(db_path))
    with Session(engine) as session:
        baseline_report = run_baseline_gate(session, dataset_mode="starter")
    with Session(engine) as session:
        post_injection_report = run_all_rules(session, dataset_mode="starter", report_mode="post_injection")

    with pytest.raises(IntegrityError):
        write_generation_run(
            dataset, "starter", 99999, export_summary, db_path, datetime.now(),
            baseline_report, post_injection_report,
        )
