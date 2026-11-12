"""Anomaly type 2 — Duplicate candidate application. business_rules.md
§9: "For an existing Application, insert one extra
ApplicationSubmissionAttempt for the same (candidate_id, requisition_id)
with a later submitted_at, is_canonical=false, duplicate_of_attempt_id
-> the original attempt, issue_type left for the detector to
(re)compute, ground_truth_label_id -> the new AnomalyLabel row." 15
incidents (full) / 3 (starter). Never a second `Application` row.

Reuses `app.validation.rules.duplicate_submissions.
recompute_canonical_assignment` — the one shared implementation of the
business_rules.md §10 algorithm (architecture.md §6: "one implementation,
two call sites") — to (re)derive is_canonical/duplicate_of_attempt_id/
issue_type for the pair after the new attempt is added, exactly as the
live write path (`workflow.md` §2a) would.
"""

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.data_generation.seeding import make_rng
from app.db.models import Application, ApplicationSubmissionAttempt
from app.validation.rules.duplicate_submissions import AttemptInput, recompute_canonical_assignment

ANOMALY_TYPE = "DuplicateApplication"
ENTITY_TYPE = "ApplicationSubmissionAttempt"


def inject(session: Session, seed: int, count: int) -> list[dict]:
    rng = make_rng(seed, "anomaly_duplicate_application")

    applications = session.execute(select(Application)).scalars().all()
    applications.sort(key=lambda a: a.application_id)
    if len(applications) < count:
        raise ValueError(
            f"Only {len(applications)} Application rows, need {count} for the "
            "duplicate-application anomaly"
        )
    chosen = rng.sample(applications, count)
    chosen.sort(key=lambda a: a.application_id)

    existing_attempt_count = session.execute(
        select(ApplicationSubmissionAttempt)
    ).scalars().all()
    next_attempt_num = max(int(a.attempt_id.split("-")[1]) for a in existing_attempt_count) + 1

    label_rows: list[dict] = []
    for app in chosen:
        canonical_attempt = (
            session.execute(
                select(ApplicationSubmissionAttempt).where(
                    ApplicationSubmissionAttempt.canonical_application_id == app.application_id,
                    ApplicationSubmissionAttempt.is_canonical.is_(True),
                )
            )
            .scalars()
            .one()
        )

        new_attempt_id = f"ATT-{next_attempt_num:07d}"
        next_attempt_num += 1
        new_submitted_at = canonical_attempt.submitted_at + timedelta(
            hours=rng.randint(2, 72)
        )

        new_attempt = ApplicationSubmissionAttempt(
            attempt_id=new_attempt_id,
            canonical_application_id=app.application_id,
            candidate_id=app.candidate_id,
            requisition_id=app.requisition_id,
            submitted_at=new_submitted_at,
            is_canonical=False,
            duplicate_of_attempt_id=canonical_attempt.attempt_id,
            issue_type="DuplicateSubmission",
            ground_truth_label_id=None,  # set after the AnomalyLabel row exists
        )
        session.add(new_attempt)
        session.flush()

        # Re-derive canonical assignment over every attempt now on file for
        # this pair, exactly as the live write path would — never just
        # trust the placeholder flags set above.
        group_attempts = (
            session.execute(
                select(ApplicationSubmissionAttempt).where(
                    ApplicationSubmissionAttempt.candidate_id == app.candidate_id,
                    ApplicationSubmissionAttempt.requisition_id == app.requisition_id,
                )
            )
            .scalars()
            .all()
        )
        inputs = [
            AttemptInput(
                attempt_id=a.attempt_id,
                candidate_id=a.candidate_id,
                requisition_id=a.requisition_id,
                submitted_at=a.submitted_at,
                is_canonical=a.is_canonical,
                duplicate_of_attempt_id=a.duplicate_of_attempt_id,
                issue_type=a.issue_type,
            )
            for a in group_attempts
        ]
        recomputed = recompute_canonical_assignment(inputs)
        by_id = {a.attempt_id: a for a in group_attempts}
        for attempt_id, fields in recomputed.items():
            row = by_id[attempt_id]
            row.is_canonical = fields["is_canonical"]
            row.duplicate_of_attempt_id = fields["duplicate_of_attempt_id"]
            row.issue_type = fields["issue_type"]

        label_rows.append(
            {
                "entity_type": ENTITY_TYPE,
                "entity_id": new_attempt_id,
                "anomaly_type": ANOMALY_TYPE,
                "related_entity_id": canonical_attempt.attempt_id,
                "description": (
                    f"Duplicate submission {new_attempt_id} for "
                    f"(candidate {app.candidate_id}, requisition {app.requisition_id}), "
                    f"canonical attempt {canonical_attempt.attempt_id}."
                ),
                "_new_attempt_id": new_attempt_id,
            }
        )

    session.flush()
    return label_rows
