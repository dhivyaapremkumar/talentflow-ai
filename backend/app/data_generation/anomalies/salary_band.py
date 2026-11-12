"""Anomaly type 4 — Offer salary outside the approved band.
business_rules.md §9: "Pick an Offer; rewrite proposed_salary to fall
outside [salary_min, salary_max] by a random 5-20% margin." 6 incidents
(full) / 1 (starter), `entity_type=Offer`.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.data_generation.seeding import make_rng
from app.db.models import Application, JobRequisition, Offer

ANOMALY_TYPE = "SalaryOutsideBand"
ENTITY_TYPE = "Offer"


def inject(session: Session, seed: int, count: int) -> list[dict]:
    rng = make_rng(seed, "anomaly_salary_band")

    offers = session.execute(select(Offer)).scalars().all()
    offers.sort(key=lambda o: o.offer_id)
    if len(offers) < count:
        raise ValueError(f"Only {len(offers)} Offer rows, need {count} for the salary-band anomaly")
    chosen = rng.sample(offers, count)
    chosen.sort(key=lambda o: o.offer_id)

    applications = {a.application_id: a for a in session.execute(select(Application)).scalars()}
    requisitions = {r.requisition_id: r for r in session.execute(select(JobRequisition)).scalars()}

    label_rows: list[dict] = []
    for offer in chosen:
        app = applications[offer.application_id]
        req = requisitions[app.requisition_id]
        margin = rng.uniform(0.05, 0.20)
        above = rng.random() < 0.5

        if above:
            new_salary = round(req.salary_max * (1 + margin))
        else:
            new_salary = max(0, round(req.salary_min * (1 - margin)))

        offer.proposed_salary = new_salary
        session.flush()

        label_rows.append(
            {
                "entity_type": ENTITY_TYPE,
                "entity_id": offer.offer_id,
                "anomaly_type": ANOMALY_TYPE,
                "related_entity_id": None,
                "description": (
                    f"Offer {offer.offer_id} proposed_salary rewritten to {new_salary}, outside "
                    f"requisition {req.requisition_id}'s band [{req.salary_min}, {req.salary_max}]."
                ),
            }
        )

    return label_rows
