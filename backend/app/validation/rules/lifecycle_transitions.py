"""VAL-07a/VAL-07b — Requisition lifecycle / Application lifecycle,
validation_strategy.md §7, state graphs from `business_rules.md` §2/§3.

Checks: every history row is a legal edge in its graph; the entity's
current state agrees with its latest history row; every history row's
actor_id resolves to an active SystemActor; and `changed_at` is strictly
increasing per parent id (the ordering half of this check, grouped here
with transition legality rather than in VAL-04, since both read the same
three history tables for the same underlying purpose).

**Offer lifecycle — flagged catalog gap, not a silent addition:**
`validation_strategy.md` §7's prose says this check covers "the three
history tables," but the formal VAL-nn catalog (§21) only names VAL-07a
(Requisition) and VAL-07b (Application) — there is no dedicated VAL-ID
for `OfferStatusHistory`, even though `business_rules.md` §3 defines its
state graph too. Rather than inventing a new rule ID (out of scope — "do
not invent or change business rules") or silently skipping it (the
prose's own stated scope), Offer-graph findings are checked here and
reported under the existing VAL-07b number with an honest, distinct
`rule_category` ("offer_lifecycle") so they're never confused with
Application-stage findings.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    Application,
    ApplicationStageHistory,
    JobRequisition,
    Offer,
    OfferStatusHistory,
    RequisitionStatusHistory,
    SystemActor,
)
from app.validation.report import Finding

RULE_ID_REQ = "VAL-07a"
RULE_ID_APP = "VAL-07b"
RULE_ID_OFFER = "VAL-07b"
RULE_CATEGORY_REQ = "requisition_lifecycle"
RULE_CATEGORY_APP = "application_lifecycle"
RULE_CATEGORY_OFFER = "offer_lifecycle"

OFFER_LEGAL_EDGES = {
    (None, "Drafted"),
    ("Drafted", "PendingApproval"),
    ("PendingApproval", "Approved"),
    ("Approved", "Extended"),
    ("Extended", "Accepted"),
    ("Extended", "Declined"),
    ("Approved", "Rescinded"),
    ("Extended", "Rescinded"),
    ("Extended", "Expired"),
}

REQUISITION_LEGAL_EDGES = {
    (None, "Draft"),
    ("Draft", "PendingApproval"),
    ("PendingApproval", "Approved"),
    ("Approved", "Open"),
    ("Open", "OnHold"),
    ("OnHold", "Open"),
    ("Open", "Closed"),
    ("Draft", "Cancelled"),
    ("PendingApproval", "Cancelled"),
    ("Approved", "Cancelled"),
    ("Open", "Cancelled"),
    ("OnHold", "Cancelled"),
}

APPLICATION_LEGAL_EDGES = {
    (None, "Applied"),
    ("Applied", "Screening"),
    ("Screening", "Interviewing"),
    ("Interviewing", "Offer"),
    ("Offer", "Hired"),
    ("Applied", "Withdrawn"),
    ("Screening", "Withdrawn"),
    ("Interviewing", "Withdrawn"),
    ("Offer", "Withdrawn"),
    ("Screening", "Rejected"),
    ("Interviewing", "Rejected"),
    ("Offer", "Rejected"),
}


def _check_history_chain(
    session: Session,
    rule_id: str,
    rule_category: str,
    entity_type: str,
    history_rows: list,
    parent_id_attr: str,
    from_attr: str,
    to_attr: str,
    legal_edges: set,
    current_state_by_parent_id: dict,
    active_actor_ids: set,
) -> list[Finding]:
    findings: list[Finding] = []

    by_parent: dict[str, list] = {}
    for row in history_rows:
        by_parent.setdefault(getattr(row, parent_id_attr), []).append(row)

    for parent_id, rows in by_parent.items():
        ordered = sorted(rows, key=lambda r: r.changed_at)

        prev_changed_at = None
        for row in ordered:
            edge = (getattr(row, from_attr), getattr(row, to_attr))
            if edge not in legal_edges:
                findings.append(
                    Finding(
                        rule_id, rule_category, entity_type, parent_id,
                        f"illegal transition {edge[0]!r} -> {edge[1]!r} in history row {row.history_id}",
                        "violation",
                    )
                )
            if prev_changed_at is not None and row.changed_at <= prev_changed_at:
                findings.append(
                    Finding(
                        rule_id, rule_category, entity_type, parent_id,
                        f"history row {row.history_id} changed_at {row.changed_at} is not strictly "
                        f"after the previous row's {prev_changed_at}",
                        "violation",
                    )
                )
            prev_changed_at = row.changed_at

            if row.actor_id not in active_actor_ids:
                findings.append(
                    Finding(
                        rule_id, rule_category, entity_type, parent_id,
                        f"history row {row.history_id} actor_id {row.actor_id!r} does not resolve "
                        "to an active SystemActor",
                        "violation",
                    )
                )

        last_to_state = getattr(ordered[-1], to_attr) if ordered else None
        current_state = current_state_by_parent_id.get(parent_id)
        if ordered and current_state is not None and last_to_state != current_state:
            findings.append(
                Finding(
                    rule_id, rule_category, entity_type, parent_id,
                    f"current state {current_state!r} does not match the latest history row's "
                    f"to-state {last_to_state!r}",
                    "violation",
                )
            )

    return findings


def check(session: Session) -> list[Finding]:
    findings: list[Finding] = []

    active_actor_ids = {
        a.actor_id for a in session.execute(select(SystemActor)).scalars() if a.is_active
    }

    requisitions = {r.requisition_id: r.status for r in session.execute(select(JobRequisition)).scalars()}
    req_history = list(session.execute(select(RequisitionStatusHistory)).scalars())
    findings.extend(
        _check_history_chain(
            session, RULE_ID_REQ, RULE_CATEGORY_REQ, "job_requisition", req_history,
            "requisition_id", "from_status", "to_status", REQUISITION_LEGAL_EDGES,
            requisitions, active_actor_ids,
        )
    )

    applications = {a.application_id: a.stage for a in session.execute(select(Application)).scalars()}
    app_history = list(session.execute(select(ApplicationStageHistory)).scalars())
    findings.extend(
        _check_history_chain(
            session, RULE_ID_APP, RULE_CATEGORY_APP, "application", app_history,
            "application_id", "from_stage", "to_stage", APPLICATION_LEGAL_EDGES,
            applications, active_actor_ids,
        )
    )

    offers = {o.offer_id: o.status for o in session.execute(select(Offer)).scalars()}
    offer_history = list(session.execute(select(OfferStatusHistory)).scalars())
    findings.extend(
        _check_history_chain(
            session, RULE_ID_OFFER, RULE_CATEGORY_OFFER, "offer", offer_history,
            "offer_id", "from_status", "to_status", OFFER_LEGAL_EDGES,
            offers, active_actor_ids,
        )
    )

    return findings
