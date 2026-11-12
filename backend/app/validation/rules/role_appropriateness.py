"""VAL-14 — Role-appropriateness, validation_strategy.md §14,
business_rules.md §11.

Severity split (A-14): `"violation"` for the two hard-enforced rows
(RequisitionStatusHistory PendingApproval->Approved,
OfferStatusHistory PendingApproval->Approved / Offer.approved_by_actor_id)
— a hit there means a service-layer gate was bypassed, which should never
happen in data produced through the service layer. `"warning"` for every
other row (soft, reported-only convention).

**Flagged scope boundary, not a silent gap:** validation_strategy.md §14
also specifies `test_hard_role_checks_cannot_be_bypassed`, which calls
`services/requisition_lifecycle.py:approve()` / `services/
offer_lifecycle.py:approve()` with a non-APPROVER actor and asserts the
*service layer* rejects it before any row is written. Those service
modules are Phase 7/8 work (`architecture.md` §7's directory tree) and do
not exist yet — Phase 4's scope is the validation engine, not the
workflow/service layer. This module implements the full defensive,
read-only check (confirming the baseline dataset has zero role
mismatches of either severity, which is testable now); the
service-layer-bypass-proof test is deferred until Phase 7 builds those
two functions.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    Application,
    ApplicationStageHistory,
    GenerationRun,
    JobRequisition,
    Offer,
    OfferStatusHistory,
    RequisitionStatusHistory,
    SystemActor,
)
from app.validation.report import Finding

RULE_ID = "VAL-14"
RULE_CATEGORY = "role_appropriateness"

# (table, from, to) -> (expected roles, severity)
REQUISITION_EXPECTATIONS = {
    ("Draft", "PendingApproval"): ({"BUSINESS_REQUESTER"}, "warning"),
    ("PendingApproval", "Approved"): ({"APPROVER"}, "violation"),
    ("Approved", "Open"): ({"PROCESS_OWNER"}, "warning"),
    ("Open", "OnHold"): ({"PROCESS_OWNER"}, "warning"),
    ("OnHold", "Open"): ({"PROCESS_OWNER"}, "warning"),
    ("Open", "Closed"): ({"PROCESS_OWNER"}, "warning"),
}
REQUISITION_CANCELLED_ROLES = {"APPROVER", "PROCESS_OWNER"}

OFFER_EXPECTATIONS = {
    ("Drafted", "PendingApproval"): ({"PROCESS_OWNER"}, "warning"),
    ("PendingApproval", "Approved"): ({"APPROVER"}, "violation"),
    ("Approved", "Extended"): ({"PROCESS_OWNER"}, "warning"),
    ("Extended", "Accepted"): ({"PROCESS_OWNER"}, "warning"),
    ("Extended", "Declined"): ({"PROCESS_OWNER"}, "warning"),
    ("Approved", "Rescinded"): ({"APPROVER"}, "warning"),
    ("Extended", "Rescinded"): ({"APPROVER"}, "warning"),
    ("Extended", "Expired"): ({"SYSTEM_ADMINISTRATOR"}, "warning"),
}


def _role_of(actors: dict, actor_id: str | None) -> str | None:
    actor = actors.get(actor_id)
    return actor.role if actor else None


def check(session: Session) -> list[Finding]:
    findings: list[Finding] = []
    actors = {a.actor_id: a for a in session.execute(select(SystemActor)).scalars()}

    for h in session.execute(select(RequisitionStatusHistory)).scalars():
        if h.from_status is None:
            continue
        role = _role_of(actors, h.actor_id)
        if h.to_status == "Cancelled":
            expected_roles, severity = REQUISITION_CANCELLED_ROLES, "warning"
        else:
            expectation = REQUISITION_EXPECTATIONS.get((h.from_status, h.to_status))
            if expectation is None:
                continue
            expected_roles, severity = expectation
        if role not in expected_roles:
            findings.append(
                Finding(
                    RULE_ID, RULE_CATEGORY, "requisition_status_history", h.history_id,
                    f"{h.from_status}->{h.to_status} performed by role {role!r}, expected one of "
                    f"{sorted(expected_roles)}",
                    severity,
                )
            )

    for h in session.execute(select(ApplicationStageHistory)).scalars():
        if h.from_stage is None:
            continue
        role = _role_of(actors, h.actor_id)
        if role != "PROCESS_OWNER":
            findings.append(
                Finding(
                    RULE_ID, RULE_CATEGORY, "application_stage_history", h.history_id,
                    f"{h.from_stage}->{h.to_stage} performed by role {role!r}, expected PROCESS_OWNER",
                    "warning",
                )
            )

    for h in session.execute(select(OfferStatusHistory)).scalars():
        if h.from_status is None:
            continue
        role = _role_of(actors, h.actor_id)
        expectation = OFFER_EXPECTATIONS.get((h.from_status, h.to_status))
        if expectation is None:
            continue
        expected_roles, severity = expectation
        if role not in expected_roles:
            findings.append(
                Finding(
                    RULE_ID, RULE_CATEGORY, "offer_status_history", h.history_id,
                    f"{h.from_status}->{h.to_status} performed by role {role!r}, expected one of "
                    f"{sorted(expected_roles)}",
                    severity,
                )
            )

    for offer in session.execute(select(Offer)).scalars():
        if offer.approved_by_actor_id is None:
            continue
        role = _role_of(actors, offer.approved_by_actor_id)
        if role != "APPROVER":
            findings.append(
                Finding(
                    RULE_ID, RULE_CATEGORY, "offer", offer.offer_id,
                    f"approved_by_actor_id resolves to role {role!r}, expected APPROVER",
                    "violation",
                )
            )

    for req in session.execute(select(JobRequisition)).scalars():
        role = _role_of(actors, req.requested_by_actor_id)
        if role != "BUSINESS_REQUESTER":
            findings.append(
                Finding(
                    RULE_ID, RULE_CATEGORY, "job_requisition", req.requisition_id,
                    f"requested_by_actor_id resolves to role {role!r}, expected BUSINESS_REQUESTER",
                    "warning",
                )
            )

    for run in session.execute(select(GenerationRun)).scalars():
        role = _role_of(actors, run.generated_by_actor_id)
        if role != "SYSTEM_ADMINISTRATOR":
            findings.append(
                Finding(
                    RULE_ID, RULE_CATEGORY, "generation_run", run.run_id,
                    f"generated_by_actor_id resolves to role {role!r}, expected SYSTEM_ADMINISTRATOR",
                    "warning",
                )
            )

    return findings
