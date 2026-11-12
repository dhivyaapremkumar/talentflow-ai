"""Anomaly type 3 — Missing feedback but application stage advanced.
business_rules.md §9: "Pick an Application at stage Offer/Hired; delete
the Feedback row for one of its Completed interviews." 10 incidents
(full) / 2 (starter), `entity_type=Application`, `related_entity_id` =
the specific Interview left without Feedback (data_dictionary.md §16).
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.data_generation.seeding import make_rng
from app.db.models import Application, Feedback, Interview

ANOMALY_TYPE = "MissingFeedbackStageAdvanced"
ENTITY_TYPE = "Application"


def inject(session: Session, seed: int, count: int) -> list[dict]:
    rng = make_rng(seed, "anomaly_missing_feedback")

    candidates = (
        session.execute(select(Application).where(Application.stage.in_(["Offer", "Hired"])))
        .scalars()
        .all()
    )
    eligible = []
    for app in candidates:
        completed_with_feedback = (
            session.execute(
                select(Interview)
                .join(Feedback, Feedback.interview_id == Interview.interview_id)
                .where(Interview.application_id == app.application_id, Interview.status == "Completed")
            )
            .scalars()
            .all()
        )
        if completed_with_feedback:
            eligible.append((app, sorted(completed_with_feedback, key=lambda iv: iv.interview_id)[0]))

    eligible.sort(key=lambda pair: pair[0].application_id)
    if len(eligible) < count:
        raise ValueError(
            f"Only {len(eligible)} eligible Application rows, need {count} for "
            "the missing-feedback anomaly"
        )
    chosen = rng.sample(eligible, count)
    chosen.sort(key=lambda pair: pair[0].application_id)

    label_rows: list[dict] = []
    for app, interview in chosen:
        feedback = (
            session.execute(select(Feedback).where(Feedback.interview_id == interview.interview_id))
            .scalars()
            .one()
        )
        session.delete(feedback)
        session.flush()

        label_rows.append(
            {
                "entity_type": ENTITY_TYPE,
                "entity_id": app.application_id,
                "anomaly_type": ANOMALY_TYPE,
                "related_entity_id": interview.interview_id,
                "description": (
                    f"Application {app.application_id} at stage {app.stage!r} has a Completed "
                    f"interview {interview.interview_id} with no Feedback row."
                ),
            }
        )

    return label_rows
