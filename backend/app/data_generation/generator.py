"""Deterministic baseline data generator — Phase 3. Entrypoint:

    python -m app.data_generation.generator --mode starter|full [--seed N]

Populates all 22 tables in the dependency order fixed by architecture.md
§4, deterministically under the fixed seed (PROJECT_SPEC.md §5). Does not
inject anomalies (`AnomalyLabel` stays empty, Phase 5's job) and does not
run the FastAPI server. Calls `app.validation` after loading the baseline
— the hard gate from business_rules.md §13 — which is a permitted
dependency (architecture.md §6 only forbids `data_generation/` importing
`api/`/`services/`, not `validation/`).
"""

import argparse
import json
import time
from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import SEED
from app.data_generation import volumes as volumes_module
from app.data_generation.entities import candidates as candidates_entity
from app.data_generation.entities import history as history_entity
from app.data_generation.entities import interviews as interviews_entity
from app.data_generation.entities import offers as offers_entity
from app.data_generation.entities import reference_data
from app.data_generation.entities import requisitions as requisitions_entity
from app.data_generation.entities.applications import generate_applications
from app.data_generation.export import export_tables
from app.db.base import Base
from app.db.models import (
    AnomalyLabel,
    Application,
    ApplicationStageHistory,
    ApplicationSubmissionAttempt,
    Candidate,
    CandidateSkill,
    Department,
    Feedback,
    GenerationRun,
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
from app.validation.gate import run_baseline_gate
from app.validation.report import results_only
from app.validation.runner import run_all_rules

GENERATOR_VERSION = "0.1.0"


def _strip_private(rows: list[dict]) -> list[dict]:
    return [{k: v for k, v in row.items() if not k.startswith("_")} for row in rows]


def generate_dataset(mode: str, seed: int = SEED) -> dict:
    """Builds the full in-memory dataset for one mode. Returns a dict of
    table_name -> list[dict], plus '_funnel' and '_actor_roles' for
    reporting/testing convenience."""
    volumes = volumes_module.volumes_for_mode(mode)
    funnel = volumes["funnel"]

    departments = reference_data.generate_departments(seed)
    skills = reference_data.generate_skills(seed)
    department_ids = [d["department_id"] for d in departments]
    department_names_by_id = {d["department_id"]: d["name"] for d in departments}
    skill_ids = [s["skill_id"] for s in skills]

    system_actors = reference_data.generate_system_actors(seed, department_ids)
    actor_ids_by_role: dict[str, list[str]] = {}
    for actor in system_actors:
        actor_ids_by_role.setdefault(actor["role"], []).append(actor["actor_id"])

    interviewers = reference_data.generate_interviewers(seed, department_ids)
    interviewer_ids = [i["interviewer_id"] for i in interviewers]
    availability_slots = reference_data.generate_availability_slots(seed, interviewer_ids, window_days=500)

    requisitions = requisitions_entity.generate_requisitions(
        seed, volumes["job_requisition"], department_ids, department_names_by_id, actor_ids_by_role
    )
    requisitions_by_id = {r["requisition_id"]: r for r in requisitions}
    requisition_skills = requisitions_entity.generate_requisition_skills(seed, requisitions, skill_ids)
    screening_rules = requisitions_entity.generate_screening_rules(seed, requisitions)

    candidates = candidates_entity.generate_candidates(seed, volumes["candidate"])
    resume_artifacts = candidates_entity.generate_resume_artifacts(seed, candidates)
    candidate_skills = candidates_entity.generate_candidate_skills(seed, candidates, skill_ids)

    applications, attempts, screening_runs, applications_by_bucket = generate_applications(
        seed,
        requisitions,
        requisition_skills,
        screening_rules,
        candidates,
        candidate_skills,
        resume_artifacts,
        funnel,
    )

    interviews, feedback_rows = interviews_entity.generate_interviews_and_feedback(
        seed, applications_by_bucket, funnel, interviewer_ids, availability_slots
    )

    offers = offers_entity.generate_offers(
        seed, applications_by_bucket, requisitions_by_id, actor_ids_by_role["APPROVER"]
    )
    offers_by_app_id = {o["application_id"]: o for o in offers}

    requisition_status_history = history_entity.generate_requisition_status_history(
        seed, requisitions, actor_ids_by_role
    )
    application_stage_history = history_entity.generate_application_stage_history(
        seed, applications, offers_by_app_id, actor_ids_by_role
    )
    offer_status_history = history_entity.generate_offer_status_history(seed, offers, actor_ids_by_role)

    return {
        "department": departments,
        "skill": skills,
        "system_actor": system_actors,
        "interviewer": interviewers,
        "interviewer_availability_slot": availability_slots,
        "job_requisition": requisitions,
        "job_requisition_skill": requisition_skills,
        "screening_rule": screening_rules,
        "candidate": candidates,
        "resume_artifact": resume_artifacts,
        "candidate_skill": candidate_skills,
        "application": applications,
        "application_submission_attempt": attempts,
        "screening_run": screening_runs,
        "interview": interviews,
        "feedback": feedback_rows,
        "offer": offers,
        "requisition_status_history": requisition_status_history,
        "application_stage_history": application_stage_history,
        "offer_status_history": offer_status_history,
        "anomaly_label": [],  # Phase 5 only — the baseline never injects anomalies.
        "_funnel": funnel,
        "_actor_ids_by_role": actor_ids_by_role,
        "_volumes": volumes,
    }


MODEL_BY_TABLE = {
    "department": Department,
    "skill": Skill,
    "system_actor": SystemActor,
    "interviewer": Interviewer,
    "interviewer_availability_slot": InterviewerAvailabilitySlot,
    "job_requisition": JobRequisition,
    "job_requisition_skill": JobRequisitionSkill,
    "screening_rule": ScreeningRule,
    "candidate": Candidate,
    "resume_artifact": ResumeArtifact,
    "candidate_skill": CandidateSkill,
    "application_submission_attempt": ApplicationSubmissionAttempt,
    "screening_run": ScreeningRun,
    "interview": Interview,
    "feedback": Feedback,
    "offer": Offer,
    "requisition_status_history": RequisitionStatusHistory,
    "application_stage_history": ApplicationStageHistory,
    "offer_status_history": OfferStatusHistory,
    "anomaly_label": AnomalyLabel,
}

# Application is handled specially (two-phase insert, see load_dataset).
LOAD_ORDER = [
    "department",
    "skill",
    "system_actor",
    "interviewer",
    "interviewer_availability_slot",
    "job_requisition",
    "job_requisition_skill",
    "screening_rule",
    "candidate",
    "resume_artifact",
    "candidate_skill",
    # application (phase 1: latest_screening_run_id=NULL) goes here
    "application_submission_attempt",
    "screening_run",
    # application (phase 2: UPDATE latest_screening_run_id) goes here
    "interview",
    "feedback",
    "offer",
    "requisition_status_history",
    "application_stage_history",
    "offer_status_history",
    "anomaly_label",
]


def load_dataset(dataset: dict, db_path: Path) -> None:
    """Two-phase Application insert, per data_dictionary.md §8b: insert
    Application with latest_screening_run_id=NULL first (satisfies the
    circular FK against ScreeningRun, which doesn't exist yet), insert
    ApplicationSubmissionAttempt + ScreeningRun, then bulk-UPDATE
    Application.latest_screening_run_id now that those rows exist."""
    engine = make_engine(str(db_path))
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        for table_name in LOAD_ORDER:
            if table_name == "application_submission_attempt":
                applications_phase1 = [
                    {**row, "latest_screening_run_id": None} for row in _strip_private(dataset["application"])
                ]
                session.bulk_insert_mappings(Application, applications_phase1)
                session.flush()

            rows = _strip_private(dataset[table_name])
            if rows:
                session.bulk_insert_mappings(MODEL_BY_TABLE[table_name], rows)
                session.flush()

        latest_run_updates = [
            {"application_id": row["application_id"], "latest_screening_run_id": row["latest_screening_run_id"]}
            for row in dataset["application"]
        ]
        session.bulk_update_mappings(Application, latest_run_updates)
        session.commit()


def write_generation_run(
    dataset: dict,
    mode: str,
    seed: int,
    export_summary: dict,
    db_path: Path,
    started_at: datetime,
    baseline_report: dict,
    export_dir: Path | None = None,
) -> dict:
    """`baseline_report` must be the real report the baseline gate already
    produced (`validation.gate.run_baseline_gate`) — never recomputed or
    fabricated here. `post_injection_validation_report_json` is a second,
    equally real run of the same validation suite, labeled "post_injection"
    for forward schema-compatibility — honestly noted as identical to the
    baseline, since Phase 5 (anomaly injection) does not exist yet in this
    codebase. Neither field is ever a placeholder claiming a result that
    wasn't actually computed."""
    engine = make_engine(str(db_path))
    sys_admin_id = dataset["_actor_ids_by_role"]["SYSTEM_ADMINISTRATOR"][0]
    generated_at = datetime.now()

    with Session(engine) as session:
        post_injection_report = run_all_rules(
            session, dataset_mode=mode, report_mode="post_injection", export_dir=export_dir
        )
    post_injection_report["note"] = (
        "Phase 5 (anomaly injection) has not run yet in this codebase — this is the "
        "same validation suite genuinely re-run against the unmodified baseline, "
        "included for forward-compatibility with the GenerationRun schema. The "
        "documented non-zero counts for VAL-06/08/10/11/12 (validation_strategy.md "
        "Sec21) will only appear once Phase 5 exists and has actually injected anomalies."
    )

    run_row = {
        "run_id": "GEN-0001",
        "seed": seed,
        "mode": mode,
        "generator_version": GENERATOR_VERSION,
        "generated_by_actor_id": sys_admin_id,
        "generated_at": generated_at,
        "entity_counts_json": json.dumps(export_summary["entity_counts"]),
        "table_checksums_json": json.dumps(export_summary["table_checksums"]),
        "overall_checksum": export_summary["overall_checksum"],
        "baseline_validation_report_json": json.dumps(results_only(baseline_report)),
        "post_injection_validation_report_json": json.dumps(results_only(post_injection_report)),
    }

    with Session(engine) as session:
        session.bulk_insert_mappings(GenerationRun, [run_row])
        session.commit()

    return run_row


def main():
    parser = argparse.ArgumentParser(description="TalentFlow AI deterministic baseline data generator")
    parser.add_argument("--mode", choices=["starter", "full"], required=True)
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--db-path", type=str, default=None)
    parser.add_argument("--export-dir", type=str, default=None)
    args = parser.parse_args()

    started_at = datetime.now()
    t0 = time.monotonic()
    dataset = generate_dataset(args.mode, args.seed)
    gen_elapsed = time.monotonic() - t0

    db_path = Path(args.db_path) if args.db_path else Path(f"data/talentflow_{args.mode}.db")
    if db_path.exists():
        db_path.unlink()
    db_path.parent.mkdir(parents=True, exist_ok=True)

    t1 = time.monotonic()
    load_dataset(dataset, db_path)
    load_elapsed = time.monotonic() - t1

    # business_rules.md Sec13's gate: run before anomaly injection would be
    # imported (Phase 5, not implemented) and before anything is exported or
    # finalized. A non-empty violation list raises BaselineValidationFailed,
    # an uncaught exception that halts the process right here.
    engine = make_engine(str(db_path))
    with Session(engine) as session:
        baseline_report = run_baseline_gate(session, dataset_mode=args.mode)

    export_dir = Path(args.export_dir) if args.export_dir else Path(f"data/exports/{args.mode}")
    export_tables_input = {k: v for k, v in dataset.items() if not k.startswith("_")}
    export_summary = export_tables(export_tables_input, export_dir)

    run_row = write_generation_run(
        dataset, args.mode, args.seed, export_summary, db_path, started_at, baseline_report, export_dir
    )

    print(f"Mode: {args.mode}  Seed: {args.seed}  Generator version: {GENERATOR_VERSION}")
    print(f"Generation time: {gen_elapsed:.2f}s  DB load time: {load_elapsed:.2f}s")
    print(f"Database: {db_path}")
    print(f"Export dir: {export_dir}")
    print("Entity counts:")
    for table, count in export_summary["entity_counts"].items():
        print(f"  {table}: {count}")
    print(f"Overall checksum: {export_summary['overall_checksum']}")
    print(
        f"Baseline validation: {baseline_report['total_violations']} violations, "
        f"{baseline_report['total_warnings']} warnings across {len(baseline_report['rule_ids_run'])} rules"
    )
    print(f"GenerationRun: {run_row['run_id']}")


if __name__ == "__main__":
    main()
