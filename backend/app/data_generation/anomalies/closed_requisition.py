"""Anomaly type 5 — Closed requisition with active applications.
business_rules.md §9/§9a/§9b: "Pick a JobRequisition; force status=Closed
while exactly 2 (A-12) of its Application rows remain in a non-terminal
stage." 5 incidents (full) / 1 (starter); 2 affected `Application` rows
per incident (10/2 total) -> one `AnomalyLabel` row per affected
`Application` (`entity_type=Application`, `entity_id`=that application,
`related_entity_id`=the closed requisition, repeated across the
incident's labels as context only, data_dictionary.md §16/§9b).

**A real implementation decision, flagged (not silent):** A-12 requires
*exactly* 2 active applications per incident, but a requisition chosen
from the baseline may already have more than 2 non-terminal applications
(most do, at full scale). Rather than limit incidents to the rare
requisitions that happen to already have exactly 2, this injector
deterministically selects 2 to leave active (the labeled ones) and
rejects any *other* non-terminal applications on that same requisition
as part of constructing this one incident — realistic (closing a
requisition legitimately resolves its other open candidates) and
necessary to make "exactly 2" true of the resulting data, not just the
label count. Only Screening/Interviewing-stage excess applications are
rejected this way (a single legal hop to `Rejected` per business_rules.md
§3); Applied-stage (would need two hops) and Offer-stage (would leave an
orphaned live `Offer` row) excess applications are never touched —
requisitions whose excess is entirely in those stages are skipped in
favor of another candidate.
"""

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.data_generation.seeding import make_rng
from app.db.models import (
    Application,
    ApplicationStageHistory,
    JobRequisition,
    Offer,
    RequisitionStatusHistory,
    SystemActor,
)

ANOMALY_TYPE = "ClosedReqActiveApplications"
ENTITY_TYPE = "Application"
TERMINAL_STAGES = {"Hired", "Rejected", "Withdrawn"}
REJECTABLE_STAGES = {"Screening", "Interviewing"}


def _find_candidate_requisitions(session: Session) -> list[tuple]:
    """Returns (requisition, non_terminal_apps) pairs for Open requisitions
    with >=2 non-terminal applications, where any *excess* beyond 2 is
    entirely in a rejectable stage."""
    requisitions = (
        session.execute(select(JobRequisition).where(JobRequisition.status == "Open")).scalars().all()
    )
    candidates = []
    for req in requisitions:
        apps = (
            session.execute(
                select(Application).where(Application.requisition_id == req.requisition_id)
            )
            .scalars()
            .all()
        )
        non_terminal = sorted(
            [a for a in apps if a.stage not in TERMINAL_STAGES], key=lambda a: a.application_id
        )
        if len(non_terminal) < 2:
            continue
        excess = non_terminal[2:]
        if all(a.stage in REJECTABLE_STAGES for a in excess):
            candidates.append((req, non_terminal))
    candidates.sort(key=lambda pair: pair[0].requisition_id)
    return candidates


def _next_seq(session: Session, model, pk_attr: str, prefix: str) -> int:
    """Starting sequence number for new rows of this type — queried once
    per `inject()` call, then incremented locally in Python. The session
    has `autoflush=False` (app/db/session.py), so repeatedly re-querying
    the DB inside a loop would not see this same function's own
    not-yet-flushed inserts from an earlier iteration and would hand out
    the same number twice — a real bug caught before this module was ever
    run, fixed by computing the starting point once and counting forward
    in memory instead."""
    rows = session.execute(select(getattr(model, pk_attr))).scalars().all()
    nums = [int(v.split("-")[1]) for v in rows if v.startswith(prefix + "-")]
    return (max(nums) + 1) if nums else 1


def inject(session: Session, seed: int, count: int) -> list[dict]:
    rng = make_rng(seed, "anomaly_closed_requisition")
    process_owner_ids = [
        a.actor_id
        for a in session.execute(select(SystemActor).where(SystemActor.role == "PROCESS_OWNER")).scalars()
    ]

    candidates = _find_candidate_requisitions(session)
    if len(candidates) < count:
        raise ValueError(
            f"Only {len(candidates)} eligible JobRequisition rows, need {count} for the "
            "closed-requisition anomaly"
        )
    chosen_indices = rng.sample(range(len(candidates)), count)
    chosen = sorted((candidates[i] for i in chosen_indices), key=lambda pair: pair[0].requisition_id)

    next_aph_num = _next_seq(session, ApplicationStageHistory, "history_id", "APH")
    next_rqh_num = _next_seq(session, RequisitionStatusHistory, "history_id", "RQH")

    label_rows: list[dict] = []
    for req, non_terminal in chosen:
        actor_id = rng.choice(process_owner_ids)
        stays_active = non_terminal[:2]
        excess = non_terminal[2:]

        # closed_at must be after EVERY event already on file for this
        # requisition — not just its still-non-terminal applications. A
        # real bug, caught before this was ever considered done: an
        # already-Hired/Rejected application's Offer can have an
        # approved_at/extended_at/decision_at later than any non-terminal
        # application's updated_at, and VAL-09 (offer_approval)
        # reconstructs "was the requisition Open at approved_at" from
        # RequisitionStatusHistory — closing the requisition too early
        # retroactively makes a perfectly valid historical approval look
        # like it happened against an already-closed requisition.
        all_apps_for_req = (
            session.execute(select(Application).where(Application.requisition_id == req.requisition_id))
            .scalars()
            .all()
        )
        candidate_timestamps = [a.updated_at for a in all_apps_for_req] + [req.created_at]
        app_ids = [a.application_id for a in all_apps_for_req]
        offers = (
            session.execute(select(Offer).where(Offer.application_id.in_(app_ids))).scalars().all()
        )
        for offer in offers:
            for ts in (offer.approved_at, offer.extended_at, offer.decision_at):
                if ts is not None:
                    candidate_timestamps.append(ts)

        latest_updated = max(candidate_timestamps)
        closed_at_dt = latest_updated + timedelta(days=rng.randint(5, 20))
        closed_at = closed_at_dt.date()

        for app in excess:
            previous_stage = app.stage
            app.stage = "Rejected"
            app.rejected_reason = "Requisition closed before a decision was recorded."
            app.updated_at = closed_at_dt
            session.add(
                ApplicationStageHistory(
                    history_id=f"APH-{next_aph_num:06d}",
                    application_id=app.application_id,
                    from_stage=previous_stage,
                    to_stage="Rejected",
                    changed_at=closed_at_dt,
                    actor_id=actor_id,
                    reason_text="Requisition closed before a decision was recorded.",
                )
            )
            next_aph_num += 1

        req.status = "Closed"
        req.closed_at = closed_at
        session.add(
            RequisitionStatusHistory(
                history_id=f"RQH-{next_rqh_num:06d}",
                requisition_id=req.requisition_id,
                from_status="Open",
                to_status="Closed",
                changed_at=closed_at_dt,
                actor_id=actor_id,
                reason_text="Position(s) filled or role no longer open.",
            )
        )
        next_rqh_num += 1
        session.flush()

        for app in stays_active:
            label_rows.append(
                {
                    "entity_type": ENTITY_TYPE,
                    "entity_id": app.application_id,
                    "anomaly_type": ANOMALY_TYPE,
                    "related_entity_id": req.requisition_id,
                    "description": (
                        f"Requisition {req.requisition_id} closed while application "
                        f"{app.application_id} remains at non-terminal stage {app.stage!r}."
                    ),
                }
            )

    return label_rows
