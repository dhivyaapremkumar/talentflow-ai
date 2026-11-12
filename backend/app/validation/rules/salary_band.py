"""VAL-10 — Salary-band compliance, validation_strategy.md §10,
business_rules.md §7.

Check: `Offer.proposed_salary` in `[requisition.salary_min,
requisition.salary_max]`, via `Offer.application_id -> Application.
requisition_id -> JobRequisition.salary_min/max` (the band is never
duplicated onto `Offer` itself — data_dictionary.md §14). Expected zero
at baseline; exactly 6 (full) / 1 (starter) post-injection
(SalaryOutsideBand, Phase 5 — not yet exercised).
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Application, JobRequisition, Offer
from app.validation.report import Finding

RULE_ID = "VAL-10"
RULE_CATEGORY = "salary_band"


def check(session: Session) -> list[Finding]:
    findings: list[Finding] = []

    applications = {a.application_id: a for a in session.execute(select(Application)).scalars()}
    requisitions = {r.requisition_id: r for r in session.execute(select(JobRequisition)).scalars()}

    for offer in session.execute(select(Offer)).scalars():
        app = applications.get(offer.application_id)
        if app is None:
            continue
        req = requisitions.get(app.requisition_id)
        if req is None:
            continue
        if not (req.salary_min <= offer.proposed_salary <= req.salary_max):
            findings.append(
                Finding(
                    RULE_ID, RULE_CATEGORY, "offer", offer.offer_id,
                    f"proposed_salary {offer.proposed_salary} outside requisition band "
                    f"[{req.salary_min}, {req.salary_max}]",
                    "violation",
                )
            )

    return findings
