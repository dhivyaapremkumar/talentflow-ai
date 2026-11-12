"""RequisitionStatusHistory, ApplicationStageHistory, OfferStatusHistory —
backfilled from each entity's already-decided final status/stage, so
every chain is a legal forward-only transition sequence (business_rules.md
§2/§3) with strictly increasing `changed_at` per parent id, ending exactly
at that entity's generated final state.
"""

from datetime import datetime, timedelta

from app.data_generation.seeding import make_rng


def generate_requisition_status_history(seed: int, requisitions: list[dict], actor_ids_by_role: dict):
    rng = make_rng(seed, "requisition_status_history")
    rows = []
    counter = 0

    def add(requisition_id, from_status, to_status, changed_at, actor_id, reason=None):
        nonlocal counter
        counter += 1
        rows.append(
            {
                "history_id": f"RQH-{counter:06d}",
                "requisition_id": requisition_id,
                "from_status": from_status,
                "to_status": to_status,
                "changed_at": changed_at,
                "actor_id": actor_id,
                "reason_text": reason,
            }
        )

    for req in requisitions:
        req_id = req["requisition_id"]
        created_at = req["created_at"]
        requester = req["requested_by_actor_id"]
        approver = rng.choice(actor_ids_by_role["APPROVER"])
        process_owner = rng.choice(actor_ids_by_role["PROCESS_OWNER"])

        add(req_id, None, "Draft", created_at, requester)
        add(req_id, "Draft", "PendingApproval", created_at + timedelta(days=1), requester)
        add(req_id, "PendingApproval", "Approved", created_at + timedelta(days=3), approver)

        opened_dt = datetime.combine(req["opened_at"], datetime.min.time()).replace(hour=9)
        add(req_id, "Approved", "Open", opened_dt, process_owner)

        status = req["status"]
        if status == "OnHold":
            add(req_id, "Open", "OnHold", opened_dt + timedelta(days=30), process_owner)
        elif status == "Closed":
            closed_dt = datetime.combine(req["closed_at"], datetime.min.time()).replace(hour=17)
            add(req_id, "Open", "Closed", closed_dt, process_owner, "Position(s) filled.")
        elif status == "Cancelled":
            closed_dt = datetime.combine(req["closed_at"], datetime.min.time()).replace(hour=17)
            add(req_id, "Open", "Cancelled", closed_dt, process_owner, "Requisition cancelled.")
    return rows


def generate_application_stage_history(seed: int, applications: list[dict], offers_by_app_id: dict, actor_ids_by_role: dict):
    rng = make_rng(seed, "application_stage_history")
    rows = []
    counter = 0

    def add(application_id, from_stage, to_stage, changed_at, reason=None):
        nonlocal counter
        counter += 1
        actor_id = rng.choice(actor_ids_by_role["PROCESS_OWNER"])
        rows.append(
            {
                "history_id": f"APH-{counter:06d}",
                "application_id": application_id,
                "from_stage": from_stage,
                "to_stage": to_stage,
                "changed_at": changed_at,
                "actor_id": actor_id,
                "reason_text": reason,
            }
        )

    for app in applications:
        bucket = app["_bucket"]
        app_id = app["application_id"]
        add(app_id, None, "Applied", app["applied_at"])

        if bucket == "still_applied":
            continue

        screening_time = app["screening_computed_at"] + timedelta(hours=2)
        add(app_id, "Applied", "Screening", screening_time)

        if bucket == "still_at_screening":
            continue
        if bucket == "rejected_at_screening":
            add(app_id, "Screening", "Rejected", screening_time + timedelta(days=rng.randint(1, 5)), "Did not pass screening.")
            continue
        if bucket == "withdrawn":
            add(app_id, "Screening", "Withdrawn", app["withdrawn_at"], "Candidate withdrew application.")
            continue

        interviewing_time = app.get("_first_interview_start") or (screening_time + timedelta(days=1))
        interviewing_time = interviewing_time - timedelta(hours=1)
        add(app_id, "Screening", "Interviewing", interviewing_time)

        if bucket == "still_interviewing":
            continue
        if bucket == "rejected_after_interview":
            add(
                app_id,
                "Interviewing",
                "Rejected",
                app["_last_interview_end"] + timedelta(days=rng.randint(1, 3)),
                "Not selected after interview rounds.",
            )
            continue

        offer = offers_by_app_id[app_id]
        add(app_id, "Interviewing", "Offer", offer["created_at"])

        if bucket == "offer_pending":
            continue
        if bucket == "hired":
            add(app_id, "Offer", "Hired", offer["decision_at"])
        elif bucket == "offer_declined":
            add(app_id, "Offer", "Rejected", offer["decision_at"], "Candidate declined the extended offer.")

    return rows


def generate_offer_status_history(seed: int, offers: list[dict], actor_ids_by_role: dict):
    rng = make_rng(seed, "offer_status_history")
    rows = []
    counter = 0

    def add(offer_id, from_status, to_status, changed_at, actor_id):
        nonlocal counter
        counter += 1
        rows.append(
            {
                "history_id": f"OFH-{counter:06d}",
                "offer_id": offer_id,
                "from_status": from_status,
                "to_status": to_status,
                "changed_at": changed_at,
                "actor_id": actor_id,
                "reason_text": None,
            }
        )

    for offer in offers:
        offer_id = offer["offer_id"]
        # business_rules.md Sec11: only PendingApproval->Approved (and the
        # Offer.approved_by_actor_id field it shares a gate with) is
        # APPROVER - every other OfferStatusHistory transition here is
        # PROCESS_OWNER. Reusing the approver actor for all of them was a
        # real bug, caught by VAL-14 the first time this generator's
        # output was actually validated.
        approver = offer["approved_by_actor_id"]
        process_owner = rng.choice(actor_ids_by_role["PROCESS_OWNER"])
        add(offer_id, None, "Drafted", offer["created_at"], process_owner)
        add(
            offer_id, "Drafted", "PendingApproval", offer["created_at"] + timedelta(hours=4), process_owner
        )
        add(offer_id, "PendingApproval", "Approved", offer["approved_at"], approver)
        add(offer_id, "Approved", "Extended", offer["extended_at"], process_owner)
        if offer["status"] == "Accepted":
            add(offer_id, "Extended", "Accepted", offer["decision_at"], process_owner)
        elif offer["status"] == "Declined":
            add(offer_id, "Extended", "Declined", offer["decision_at"], process_owner)
    return rows
