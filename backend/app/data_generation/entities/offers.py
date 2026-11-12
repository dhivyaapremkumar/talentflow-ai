"""Offer — generated only for the hired/offer_declined/offer_pending
buckets (exactly `funnel.offer_or_beyond` rows, 1:1 with those
applications). `proposed_salary` is kept within the requisition's
approved band here — SalaryOutsideBand is a Phase 5 anomaly, never part
of the clean baseline.
"""

from datetime import timedelta

from app.data_generation.seeding import make_rng

OFFER_BUCKETS = ("hired", "offer_declined", "offer_pending")


def generate_offers(
    seed: int, applications_by_bucket: dict, requisitions_by_id: dict, approver_actor_ids: list[str]
):
    rng = make_rng(seed, "offer")
    offers: list[dict] = []
    offer_counter = 0

    for bucket in OFFER_BUCKETS:
        for app in applications_by_bucket[bucket]:
            req = requisitions_by_id[app["requisition_id"]]
            offer_counter += 1
            proposed_salary = rng.randint(req["salary_min"], req["salary_max"])

            base = app.get("_last_interview_end") or app["screening_computed_at"]
            created_at = base + timedelta(days=rng.randint(1, 4))
            approved_at = created_at + timedelta(days=rng.randint(1, 3))
            extended_at = approved_at + timedelta(days=rng.randint(1, 3))

            if bucket == "hired":
                status = "Accepted"
                decision_at = extended_at + timedelta(days=rng.randint(2, 10))
            elif bucket == "offer_declined":
                status = "Declined"
                decision_at = extended_at + timedelta(days=rng.randint(2, 10))
            else:
                status = "Extended"
                decision_at = None

            expiry_date = (extended_at + timedelta(days=14)).date()

            offer_row = {
                "offer_id": f"OFR-{offer_counter:05d}",
                "application_id": app["application_id"],
                "proposed_salary": proposed_salary,
                "currency": "USD",
                "equity_amount": rng.choice([0, 5000, 10000, 15000, 20000]),
                "status": status,
                "approved_by_actor_id": rng.choice(approver_actor_ids),
                "approved_at": approved_at,
                "extended_at": extended_at,
                "decision_at": decision_at,
                "expiry_date": expiry_date,
                "created_at": created_at,
                "_bucket": bucket,
            }
            offers.append(offer_row)

            last_ts = decision_at or extended_at
            app["updated_at"] = max(app["updated_at"], last_ts)

    return offers
