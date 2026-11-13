"""The live offer-lifecycle service — Phase 8, implementation_plan.md's
Phase 8 row: `services/offer_lifecycle.py` hard-rejects a
`PendingApproval->Approved` transition (and setting
`approved_by_actor_id`) when the actor's role isn't `APPROVER`
(business_rules.md §11) — the same hard/soft split as
`requisition_lifecycle.py`, the only other hard-gated service in this
project.

Reuses `validation.rules.lifecycle_transitions.OFFER_LEGAL_EDGES`
verbatim (architecture.md §6) — never redefines the transition graph.

**Salary-band rule — interpretive decision, flagged explicitly (not a
silent assumption):** `business_rules.md` §7 states band compliance is
"checked by the validation engine, not a DB constraint," specifically so
the *dataset* can represent the seeded `SalaryOutsideBand` anomalies. That
sentence is about why it is not a structural `CHECK` (SQLite cannot
express the cross-table lookup anyway) — it does not say the live service
must accept an out-of-band request. The seeded anomalies are written
directly by the data generator (`data_generation/`), never through this
service, so hard-rejecting an out-of-band proposed_salary here does not
conflict with the dataset's ability to contain them: `create_offer()`
below rejects a request whose `proposed_salary` falls outside the
requisition's current `[salary_min, salary_max]` band at draft time
(workflow.md §6: "PROCESS_OWNER drafts Offer ... against ... salary
band"). `validation/rules/salary_band.py` continues to audit the full
dataset defensively, exactly as `role_appropriateness.py` continues to
re-check the two hard role gates defensively — a hit there would mean
this gate was bypassed (e.g. by the generator), not an expected outcome
for data written through this service.

**`Offer may not move to Approved unless requisition.status == "Open"`**
(business_rules.md §7) is a second, independent hard precondition on the
`PendingApproval->Approved` edge — distinct from, and checked in addition
to, the APPROVER role gate. `validation/rules/offer_approval.py`
reconstructs this from `RequisitionStatusHistory` as of `approved_at`
because it audits historical data after the fact, where the requisition
may have since moved on; this live call's `approved_at` *is* "now", so
checking `JobRequisition.status` directly is the same check, not a
weaker one.

**Composition, not duplication:** on `Extended->Accepted`, this module
calls `application_lifecycle._transition_application_stage_core()`
directly (no nested commit/rollback) inside its own transaction, so
"`Accepted` -> `Application.stage` becomes `Hired`" (workflow.md §6) is
one atomic operation spanning both tables, without reimplementing the
stage-transition algorithm.
"""

from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Application, JobRequisition, Offer, SystemActor
from app.db.models.history import OfferStatusHistory
from app.services.application_lifecycle import (
    ApplicationLifecycleError,
    _transition_application_stage_core,
)
from app.validation.rules.lifecycle_transitions import OFFER_LEGAL_EDGES

HARD_APPROVAL_EDGE = ("PendingApproval", "Approved")


class OfferLifecycleError(Exception):
    """Raised when an offer operation cannot proceed — the service rolls
    back the session before raising, so the caller is never left
    mid-transaction."""


def _next_offer_id(session: Session) -> str:
    existing = session.execute(select(Offer.offer_id)).scalars().all()
    nums = [int(v.split("-")[1]) for v in existing]
    next_num = (max(nums) + 1) if nums else 1
    return f"OFR-{next_num:05d}"


def _next_history_id(session: Session) -> str:
    existing = session.execute(select(OfferStatusHistory.history_id)).scalars().all()
    nums = [int(v.split("-")[1]) for v in existing]
    next_num = (max(nums) + 1) if nums else 1
    return f"OFH-{next_num:06d}"


def create_offer(
    session: Session,
    application_id: str,
    proposed_salary: int,
    currency: str = "USD",
    equity_amount: int | None = None,
    created_at: datetime | None = None,
) -> Offer:
    """Drafts one `Offer` (status=Drafted) as one atomic transaction.

    Raises `OfferLifecycleError` (after rolling back) if the application
    does not exist, is not at stage `Offer`, already has an `Offer` row
    (1:1, data_dictionary.md §14), or `proposed_salary` falls outside the
    requisition's current salary band (see module docstring) — never
    partially commits.
    """
    try:
        application = session.get(Application, application_id)
        if application is None:
            raise OfferLifecycleError(f"Application {application_id!r} does not exist")
        if application.stage != "Offer":
            raise OfferLifecycleError(
                f"Application {application_id!r} is at stage {application.stage!r}, not 'Offer'"
            )

        existing = session.execute(
            select(Offer).where(Offer.application_id == application_id)
        ).scalars().first()
        if existing is not None:
            raise OfferLifecycleError(f"Application {application_id!r} already has an Offer")

        requisition = session.get(JobRequisition, application.requisition_id)
        if requisition is None:
            raise OfferLifecycleError(f"JobRequisition {application.requisition_id!r} does not exist")
        if not (requisition.salary_min <= proposed_salary <= requisition.salary_max):
            raise OfferLifecycleError(
                f"proposed_salary {proposed_salary} outside requisition band "
                f"[{requisition.salary_min}, {requisition.salary_max}] (business_rules.md §7)"
            )

        now = created_at or datetime.now()
        offer = Offer(
            offer_id=_next_offer_id(session),
            application_id=application_id,
            proposed_salary=proposed_salary,
            currency=currency,
            equity_amount=equity_amount,
            status="Drafted",
            created_at=now,
        )
        session.add(offer)

        session.commit()
        return offer
    except Exception:
        session.rollback()
        raise


def transition_offer(
    session: Session,
    offer_id: str,
    to_status: str,
    actor_id: str,
    changed_at: datetime | None = None,
    reason_text: str | None = None,
    expiry_date: date | None = None,
) -> OfferStatusHistory:
    """Executes one offer status transition as one atomic transaction:
    validate the edge is legal, hard-enforce the APPROVER gate and the
    requisition-Open precondition on `PendingApproval->Approved`, populate
    the required fields for the target status, insert the
    `OfferStatusHistory` row, update `Offer.status`, and (only on
    `Extended->Accepted`) advance `Application.stage` to `Hired` in the
    same transaction.

    Raises `OfferLifecycleError` (after rolling back) for a missing
    offer/actor, an illegal edge, a hard-gate rejection, or a failed
    `Hired` advancement — never partially commits.
    """
    try:
        offer = session.get(Offer, offer_id)
        if offer is None:
            raise OfferLifecycleError(f"Offer {offer_id!r} does not exist")

        actor = session.get(SystemActor, actor_id)
        if actor is None:
            raise OfferLifecycleError(f"SystemActor {actor_id!r} does not exist")

        from_status = offer.status
        edge = (from_status, to_status)
        if edge not in OFFER_LEGAL_EDGES:
            raise OfferLifecycleError(f"illegal offer transition {from_status!r} -> {to_status!r}")

        if edge == HARD_APPROVAL_EDGE:
            if actor.role != "APPROVER":
                raise OfferLifecycleError(
                    f"PendingApproval->Approved requires actor role APPROVER, got {actor.role!r} "
                    "(hard-enforced, business_rules.md §11)"
                )
            application = session.get(Application, offer.application_id)
            requisition = session.get(JobRequisition, application.requisition_id) if application else None
            requisition_status = requisition.status if requisition is not None else None
            if requisition_status != "Open":
                raise OfferLifecycleError(
                    f"requisition status is {requisition_status!r}, not 'Open', at approval time "
                    "(business_rules.md §7)"
                )

        now = changed_at or datetime.now()

        if to_status == "Approved":
            offer.approved_by_actor_id = actor_id
            offer.approved_at = now
        if to_status == "Extended":
            offer.extended_at = now
            if expiry_date is not None:
                offer.expiry_date = expiry_date
        if to_status in ("Accepted", "Declined"):
            offer.decision_at = now

        history = OfferStatusHistory(
            history_id=_next_history_id(session),
            offer_id=offer_id,
            from_status=from_status,
            to_status=to_status,
            changed_at=now,
            actor_id=actor_id,
            reason_text=reason_text,
        )
        session.add(history)
        session.flush()

        offer.status = to_status

        if to_status == "Accepted":
            try:
                _transition_application_stage_core(
                    session, offer.application_id, "Hired", actor_id, now,
                    "Offer accepted", None,
                )
            except ApplicationLifecycleError as exc:
                raise OfferLifecycleError(f"could not advance application to Hired: {exc}") from exc

        session.commit()
        return history
    except Exception:
        session.rollback()
        raise


def approve(
    session: Session,
    offer_id: str,
    actor_id: str,
    changed_at: datetime | None = None,
    reason_text: str | None = None,
) -> OfferStatusHistory:
    """Convenience wrapper for the explicit `PendingApproval->Approved`
    hard-gated transition — matches `validation_strategy.md` §14's test
    naming (`offer_lifecycle.approve()`), called directly so a
    non-`APPROVER` actor can be proven rejected without going through any
    API/UI layer."""
    return transition_offer(session, offer_id, "Approved", actor_id, changed_at, reason_text)
