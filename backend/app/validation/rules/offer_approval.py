"""VAL-09 — Offer approval rules, validation_strategy.md §9.

Check: every `Offer` with `status in {Approved, Extended, Accepted}` has
`approved_at`/`approved_by_actor_id` set, that actor exists and is
active, and `JobRequisition.status` was `Open` at `approved_at` time
(reconstructed from `RequisitionStatusHistory`, not the requisition's
current status — the requisition may have since moved on).
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Application, Offer, RequisitionStatusHistory, SystemActor
from app.validation.report import Finding

RULE_ID = "VAL-09"
RULE_CATEGORY = "offer_approval"

REQUIRES_APPROVAL = {"Approved", "Extended", "Accepted"}


def check(session: Session) -> list[Finding]:
    findings: list[Finding] = []

    actors = {a.actor_id: a for a in session.execute(select(SystemActor)).scalars()}
    applications = {a.application_id: a for a in session.execute(select(Application)).scalars()}

    history_by_req: dict[str, list] = {}
    for h in session.execute(select(RequisitionStatusHistory)).scalars():
        history_by_req.setdefault(h.requisition_id, []).append(h)
    for rows in history_by_req.values():
        rows.sort(key=lambda h: h.changed_at)

    for offer in session.execute(select(Offer)).scalars():
        if offer.status not in REQUIRES_APPROVAL:
            continue

        if offer.approved_at is None or offer.approved_by_actor_id is None:
            findings.append(
                Finding(
                    RULE_ID, RULE_CATEGORY, "offer", offer.offer_id,
                    f"status={offer.status!r} requires approved_at and approved_by_actor_id to be set",
                    "violation",
                )
            )
            continue

        actor = actors.get(offer.approved_by_actor_id)
        if actor is None or not actor.is_active:
            findings.append(
                Finding(
                    RULE_ID, RULE_CATEGORY, "offer", offer.offer_id,
                    f"approved_by_actor_id {offer.approved_by_actor_id!r} does not resolve to an "
                    "active SystemActor",
                    "violation",
                )
            )

        app = applications.get(offer.application_id)
        if app is None:
            continue
        rows = history_by_req.get(app.requisition_id, [])
        status_at_approval = None
        for h in rows:
            if h.changed_at <= offer.approved_at:
                status_at_approval = h.to_status
            else:
                break
        if status_at_approval != "Open":
            findings.append(
                Finding(
                    RULE_ID, RULE_CATEGORY, "offer", offer.offer_id,
                    f"requisition {app.requisition_id} status was {status_at_approval!r}, not "
                    f"'Open', at approved_at {offer.approved_at}",
                    "violation",
                )
            )

    return findings
