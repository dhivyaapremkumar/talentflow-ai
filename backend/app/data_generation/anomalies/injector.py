"""Top-level anomaly injection orchestrator — business_rules.md §9,
run only after the Phase 4 baseline gate has passed with zero violations
(enforced by the caller, `data_generation/generator.py`, not by this
module — this module has no gate-bypass path of its own).

Runs the five injectors in a fixed order, assigns sequential `ANOM-nnnn`
ids across all of them combined (generation order, per architecture.md
§4's "each injector writes its own AnomalyLabel row(s) in the same step
it mutates or adds the anomalous row"), and inserts every `AnomalyLabel`
row. The injector never touches the same source row for two different
anomaly types (business_rules.md §9's row-level "no overlap" guarantee)
— structurally true here because each injector only ever selects from
its own table (Interview / ApplicationSubmissionAttempt / Application /
Offer / JobRequisition+Application) and the five calls run once each,
in sequence, never re-visiting an earlier injector's output.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.data_generation.anomalies import (
    closed_requisition,
    duplicate_application,
    missing_feedback,
    salary_band,
    unavailable_interviewer,
)
from app.data_generation.volumes import volumes_for_mode
from app.db.models import AnomalyLabel, ApplicationSubmissionAttempt

INJECTION_ORDER = [
    ("unavailable_interviewer", unavailable_interviewer),
    ("duplicate_application", duplicate_application),
    ("missing_feedback", missing_feedback),
    ("salary_band", salary_band),
    ("closed_requisition", closed_requisition),
]


def inject_all_anomalies(session: Session, seed: int, mode: str, injected_at) -> list[dict]:
    anomaly_counts = volumes_for_mode(mode)["anomaly_counts"]

    existing_labels = session.execute(select(AnomalyLabel.label_id)).scalars().all()
    next_label_num = (
        max(int(v.split("-")[1]) for v in existing_labels) + 1 if existing_labels else 1
    )

    all_label_rows: list[dict] = []
    for key, module in INJECTION_ORDER:
        count = anomaly_counts[key]
        raw_labels = module.inject(session, seed, count)

        for raw in raw_labels:
            label_id = f"ANOM-{next_label_num:04d}"
            next_label_num += 1

            new_attempt_id = raw.pop("_new_attempt_id", None)
            if new_attempt_id is not None:
                attempt = session.get(ApplicationSubmissionAttempt, new_attempt_id)
                attempt.ground_truth_label_id = label_id

            session.add(
                AnomalyLabel(
                    label_id=label_id,
                    entity_type=raw["entity_type"],
                    entity_id=raw["entity_id"],
                    anomaly_type=raw["anomaly_type"],
                    related_entity_id=raw["related_entity_id"],
                    injected_at=injected_at,
                    description=raw["description"][:200],
                )
            )
            all_label_rows.append({**raw, "label_id": label_id})

        session.flush()

    return all_label_rows
