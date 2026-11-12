"""CSV export + checksums — data_dictionary.md §17. `table_checksums_json`
covers the 21 operational/reference tables (every table except
`GenerationRun` itself); `overall_checksum` is the SHA-256 of their
concatenation in this fixed order, so re-running with the same
seed+mode+generator_version is byte-comparable.
"""

import csv
import hashlib
import io
import json
from datetime import date, datetime
from pathlib import Path

# Fixed table order, matching architecture.md §4's generation order
# (history tables + AnomalyLabel appended at the end, per the pipeline
# diagram) — this exact order is what overall_checksum concatenates over.
TABLE_ORDER = [
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
    "application",
    "application_submission_attempt",
    "screening_run",
    "interview",
    "feedback",
    "offer",
    "requisition_status_history",
    "application_stage_history",
    "offer_status_history",
    "anomaly_label",
]

# Canonical column order per table, matching data_dictionary.md field
# order exactly. The first column(s) listed are treated as the sort/PK key.
TABLE_COLUMNS = {
    "department": ["department_id", "name", "cost_center_code", "created_at"],
    "skill": ["skill_id", "name", "category", "is_active"],
    "system_actor": ["actor_id", "full_name", "role", "department_id", "email", "is_active", "created_at"],
    "interviewer": ["interviewer_id", "full_name", "email", "department_id", "title", "is_active"],
    "interviewer_availability_slot": [
        "slot_id",
        "interviewer_id",
        "start_datetime",
        "end_datetime",
        "is_booked",
    ],
    "job_requisition": [
        "requisition_id",
        "department_id",
        "title",
        "level",
        "employment_type",
        "status",
        "salary_min",
        "salary_max",
        "headcount",
        "requested_by_actor_id",
        "opened_at",
        "target_close_date",
        "closed_at",
        "created_at",
    ],
    "job_requisition_skill": [
        "requisition_id",
        "skill_id",
        "min_proficiency_level",
        "is_mandatory",
        "weight_pct",
    ],
    "screening_rule": [
        "screening_rule_id",
        "requisition_id",
        "is_current",
        "version",
        "min_years_experience",
        "min_education_level",
        "skill_weight_pct",
        "experience_weight_pct",
        "education_weight_pct",
        "pass_threshold_score",
        "created_at",
    ],
    "candidate": [
        "candidate_id",
        "full_name",
        "email",
        "phone",
        "location_city",
        "location_country",
        "years_experience",
        "highest_education_level",
        "source_channel",
        "created_at",
    ],
    "resume_artifact": [
        "resume_artifact_id",
        "candidate_id",
        "file_name",
        "file_format",
        "parsed_years_experience",
        "parsed_education_level",
        "is_latest",
        "uploaded_at",
    ],
    "candidate_skill": [
        "candidate_id",
        "skill_id",
        "proficiency_level",
        "years_of_experience",
        "source",
        "updated_at",
    ],
    "application": [
        "application_id",
        "candidate_id",
        "requisition_id",
        "resume_artifact_id",
        "applied_at",
        "source_channel",
        "stage",
        "screening_score",
        "screening_skill_component",
        "screening_experience_component",
        "screening_education_component",
        "screening_education_gate_passed",
        "screening_decision",
        "screening_rule_version",
        "screening_computed_at",
        "screening_explanation",
        "latest_screening_run_id",
        "rejected_reason",
        "withdrawn_at",
        "created_at",
        "updated_at",
    ],
    "application_submission_attempt": [
        "attempt_id",
        "canonical_application_id",
        "candidate_id",
        "requisition_id",
        "submitted_at",
        "is_canonical",
        "duplicate_of_attempt_id",
        "issue_type",
        "ground_truth_label_id",
    ],
    "screening_run": [
        "screening_run_id",
        "application_id",
        "screening_rule_id",
        "is_latest",
        "screening_rule_version",
        "screening_skill_component",
        "screening_experience_component",
        "screening_education_component",
        "screening_education_gate_passed",
        "screening_score",
        "screening_decision",
        "screening_explanation",
        "computed_at",
    ],
    "interview": [
        "interview_id",
        "application_id",
        "interviewer_id",
        "round_number",
        "round_type",
        "scheduled_start",
        "scheduled_end",
        "status",
        "location_mode",
        "created_at",
        "updated_at",
    ],
    "feedback": [
        "feedback_id",
        "interview_id",
        "interviewer_id",
        "recommendation",
        "overall_score",
        "strengths_text",
        "concerns_text",
        "submitted_at",
    ],
    "offer": [
        "offer_id",
        "application_id",
        "proposed_salary",
        "currency",
        "equity_amount",
        "status",
        "approved_by_actor_id",
        "approved_at",
        "extended_at",
        "decision_at",
        "expiry_date",
        "created_at",
    ],
    "requisition_status_history": [
        "history_id",
        "requisition_id",
        "from_status",
        "to_status",
        "changed_at",
        "actor_id",
        "reason_text",
    ],
    "application_stage_history": [
        "history_id",
        "application_id",
        "from_stage",
        "to_stage",
        "changed_at",
        "actor_id",
        "reason_text",
    ],
    "offer_status_history": [
        "history_id",
        "offer_id",
        "from_status",
        "to_status",
        "changed_at",
        "actor_id",
        "reason_text",
    ],
    "anomaly_label": [
        "label_id",
        "entity_type",
        "entity_id",
        "anomaly_type",
        "related_entity_id",
        "injected_at",
        "description",
    ],
}


def _cell(value) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return str(value)


def _canonical_csv(table_name: str, rows: list[dict]) -> str:
    columns = TABLE_COLUMNS[table_name]
    pk_len = 2 if table_name in ("job_requisition_skill", "candidate_skill") else 1
    sorted_rows = sorted(rows, key=lambda r: tuple(_cell(r[c]) for c in columns[:pk_len]))
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(columns)
    for row in sorted_rows:
        writer.writerow([_cell(row.get(c)) for c in columns])
    return buf.getvalue()


def export_tables(tables: dict[str, list[dict]], export_dir: Path) -> dict:
    export_dir.mkdir(parents=True, exist_ok=True)
    table_checksums = {}
    entity_counts = {}

    for table_name in TABLE_ORDER:
        rows = tables.get(table_name, [])
        csv_text = _canonical_csv(table_name, rows)
        (export_dir / f"{table_name}.csv").write_text(csv_text, encoding="utf-8", newline="")
        checksum = hashlib.sha256(csv_text.encode("utf-8")).hexdigest()
        table_checksums[table_name] = checksum
        entity_counts[table_name] = len(rows)

    overall_checksum = hashlib.sha256(
        "".join(table_checksums[t] for t in TABLE_ORDER).encode("utf-8")
    ).hexdigest()

    (export_dir / "table_checksums.json").write_text(
        json.dumps(table_checksums, indent=2), encoding="utf-8"
    )
    (export_dir / "entity_counts.json").write_text(json.dumps(entity_counts, indent=2), encoding="utf-8")

    return {
        "entity_counts": entity_counts,
        "table_checksums": table_checksums,
        "overall_checksum": overall_checksum,
    }
