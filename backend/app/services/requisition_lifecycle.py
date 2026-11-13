"""The live requisition-lifecycle service — Phase 8,
implementation_plan.md's Phase 8 row: `services/requisition_lifecycle.py`
hard-rejects a `PendingApproval->Approved` transition when the actor's
role isn't `APPROVER` (business_rules.md §11); every other transition
stays soft/advisory.

Reuses `validation.rules.lifecycle_transitions.REQUISITION_LEGAL_EDGES`
verbatim — the same edge set `validation/rules/lifecycle_transitions.py`
already audits the generated dataset against (architecture.md §6: "one
implementation, never duplicated or allowed to drift"). This module never
redefines the transition graph.

**Hard vs. soft, exactly as business_rules.md §11 states it:**
`Draft->PendingApproval` (expects `BUSINESS_REQUESTER`), `Approved->Open`/
`Open<->OnHold`/`Open->Closed` (expects `PROCESS_OWNER`), and `*->Cancelled`
(expects `APPROVER` or `PROCESS_OWNER`) are all **soft** — the actor_id
must resolve to an existing `SystemActor`, but a role mismatch is never
blocked here; `validation/rules/role_appropriateness.py` reports it as a
`"warning"` finding after the fact. Only `PendingApproval->Approved` is
**hard**: this service rejects the call outright (no row written) if the
actor's role is not `APPROVER`.

**Separate hard precondition, not a role check:** `business_rules.md` §2 —
"a requisition may only move to `Open` if it has exactly one `ScreeningRule`
with `is_current=true` and at least one `JobRequisitionSkill` row." This is
checked whenever `to_status == "Open"`, regardless of role, for both the
`Approved->Open` and `OnHold->Open` edges.
"""

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import JobRequisition, JobRequisitionSkill, ScreeningRule, SystemActor
from app.db.models.history import RequisitionStatusHistory
from app.validation.rules.lifecycle_transitions import REQUISITION_LEGAL_EDGES

HARD_APPROVAL_EDGE = ("PendingApproval", "Approved")


class RequisitionLifecycleError(Exception):
    """Raised when a requisition transition cannot proceed — the service
    rolls back the session before raising, so the caller is never left
    mid-transaction."""


def _next_history_id(session: Session) -> str:
    existing = session.execute(select(RequisitionStatusHistory.history_id)).scalars().all()
    nums = [int(v.split("-")[1]) for v in existing]
    next_num = (max(nums) + 1) if nums else 1
    return f"RQH-{next_num:06d}"


def transition_requisition(
    session: Session,
    requisition_id: str,
    to_status: str,
    actor_id: str,
    changed_at: datetime | None = None,
    reason_text: str | None = None,
) -> RequisitionStatusHistory:
    """Executes one requisition status transition as one atomic
    transaction: validate the edge is legal, hard-enforce the APPROVER
    gate on `PendingApproval->Approved`, enforce the `Open`-readiness
    precondition, insert the `RequisitionStatusHistory` row, and update
    `JobRequisition.status` (plus `opened_at`/`closed_at` when first
    required).

    Raises `RequisitionLifecycleError` (after rolling back) for a missing
    requisition/actor, an illegal edge, a hard-gate rejection, or a failed
    `Open`-readiness precondition — never partially commits.
    """
    try:
        requisition = session.get(JobRequisition, requisition_id)
        if requisition is None:
            raise RequisitionLifecycleError(f"JobRequisition {requisition_id!r} does not exist")

        actor = session.get(SystemActor, actor_id)
        if actor is None:
            raise RequisitionLifecycleError(f"SystemActor {actor_id!r} does not exist")

        from_status = requisition.status
        edge = (from_status, to_status)
        if edge not in REQUISITION_LEGAL_EDGES:
            raise RequisitionLifecycleError(
                f"illegal requisition transition {from_status!r} -> {to_status!r}"
            )

        if edge == HARD_APPROVAL_EDGE and actor.role != "APPROVER":
            raise RequisitionLifecycleError(
                f"PendingApproval->Approved requires actor role APPROVER, got {actor.role!r} "
                f"(hard-enforced, business_rules.md §11)"
            )

        if to_status == "Open":
            current_rule_count = session.execute(
                select(func.count()).select_from(ScreeningRule).where(
                    ScreeningRule.requisition_id == requisition_id,
                    ScreeningRule.is_current.is_(True),
                )
            ).scalar_one()
            skill_count = session.execute(
                select(func.count()).select_from(JobRequisitionSkill).where(
                    JobRequisitionSkill.requisition_id == requisition_id
                )
            ).scalar_one()
            if current_rule_count != 1 or skill_count < 1:
                raise RequisitionLifecycleError(
                    f"requisition {requisition_id!r} is not Open-ready: "
                    f"{current_rule_count} current ScreeningRule row(s), "
                    f"{skill_count} JobRequisitionSkill row(s) (business_rules.md §2)"
                )

        now = changed_at or datetime.now()

        history = RequisitionStatusHistory(
            history_id=_next_history_id(session),
            requisition_id=requisition_id,
            from_status=from_status,
            to_status=to_status,
            changed_at=now,
            actor_id=actor_id,
            reason_text=reason_text,
        )
        session.add(history)
        session.flush()

        requisition.status = to_status
        if to_status == "Open" and requisition.opened_at is None:
            requisition.opened_at = now.date()
        if to_status in ("Closed", "Cancelled") and requisition.closed_at is None:
            requisition.closed_at = now.date()

        session.commit()
        return history
    except Exception:
        session.rollback()
        raise


def approve(
    session: Session,
    requisition_id: str,
    actor_id: str,
    changed_at: datetime | None = None,
    reason_text: str | None = None,
) -> RequisitionStatusHistory:
    """Convenience wrapper for the explicit `PendingApproval->Approved`
    hard-gated transition — matches `validation_strategy.md` §14's test
    naming (`requisition_lifecycle.approve()`), called directly so a
    non-`APPROVER` actor can be proven rejected without going through any
    API/UI layer."""
    return transition_requisition(session, requisition_id, "Approved", actor_id, changed_at, reason_text)
