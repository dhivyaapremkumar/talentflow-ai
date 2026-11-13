"""The live screening service — Phase 7, implementation_plan.md's Phase 7
row: "gains the transactional wrapper around Phase 4's pure
`compute_screening_score`... one atomic transaction, business_rules.md
§5." This module never redefines the formula — it imports
`app.screening_formula.compute_screening_result` verbatim (the same
function `data_generation/entities/applications.py` and
`validation/rules/screening_recompute.py` already use), so scoring logic
exists in exactly one place (architecture.md §6). **No LLM is used
anywhere in this module or the formula it calls** — the score, gate, and
decision are a deterministic closed-form computation over
skill/experience/education inputs only.

**Scope boundary, flagged (not silent):** this module does **not**
advance `Application.stage` (Applied→Screening→Interviewing/Rejected).
`data_dictionary.md` §8b's atomic procedure and `business_rules.md` §5
both describe exactly three steps — flip the prior `is_latest` row,
insert the new `ScreeningRun`, update `Application`'s *mirrored
screening columns* — never a stage transition. Stage advancement based
on `screening_decision` is lifecycle logic
(`services/application_lifecycle.py`), explicitly Phase 8 work per
`implementation_plan.md`'s own Phase 7/8 split. Calling this function
leaves `Application.stage` untouched; a caller (Phase 8) is expected to
read the mirrored `screening_decision` afterward and apply the stage
transition itself.
"""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    Application,
    Candidate,
    CandidateSkill,
    JobRequisitionSkill,
    ScreeningRule,
    ScreeningRun,
)
from app.screening_formula import compute_screening_result


class ScreeningError(Exception):
    """Raised when screening cannot proceed — the service rolls back the
    session before raising, so the caller is never left mid-transaction."""


def _next_screening_run_id(session: Session) -> str:
    existing = session.execute(select(ScreeningRun.screening_run_id)).scalars().all()
    nums = [int(v.split("-")[1]) for v in existing]
    next_num = (max(nums) + 1) if nums else 1
    return f"SCRUN-{next_num:07d}"


def run_screening(session: Session, application_id: str, computed_at: datetime | None = None) -> ScreeningRun:
    """Computes and persists one screening result for `application_id`,
    as one atomic transaction:

    1. Flip any prior `is_latest=true` ScreeningRun for this application
       to `false` (a no-op on first screening).
    2. Insert the new `ScreeningRun` row (`is_latest=true`), referencing
       the requisition's *current* `ScreeningRule` row directly — a
       permanent, reproducible reference even if that rule is later
       redefined (business_rules.md §4).
    3. Update `Application`'s nine mirrored screening columns and
       `latest_screening_run_id` to match the row just inserted.

    Raises `ScreeningError` (after rolling back) if the application,
    its requisition's current screening rule, or its required skills
    cannot be resolved — never partially commits.
    """
    try:
        application = session.get(Application, application_id)
        if application is None:
            raise ScreeningError(f"Application {application_id!r} does not exist")

        candidate = session.get(Candidate, application.candidate_id)
        if candidate is None:
            raise ScreeningError(f"Candidate {application.candidate_id!r} does not exist")

        rule = session.execute(
            select(ScreeningRule).where(
                ScreeningRule.requisition_id == application.requisition_id,
                ScreeningRule.is_current.is_(True),
            )
        ).scalars().first()
        if rule is None:
            raise ScreeningError(
                f"Requisition {application.requisition_id!r} has no current ScreeningRule"
            )

        required_skills = [
            {
                "skill_id": jrs.skill_id,
                "weight_pct": jrs.weight_pct,
                "min_proficiency_level": jrs.min_proficiency_level,
            }
            for jrs in session.execute(
                select(JobRequisitionSkill).where(
                    JobRequisitionSkill.requisition_id == application.requisition_id
                )
            ).scalars()
        ]

        candidate_skills_by_skill_id = {
            cs.skill_id: {"proficiency_level": cs.proficiency_level}
            for cs in session.execute(
                select(CandidateSkill).where(CandidateSkill.candidate_id == candidate.candidate_id)
            ).scalars()
        }

        result = compute_screening_result(
            required_skills=required_skills,
            candidate_skills_by_skill_id=candidate_skills_by_skill_id,
            candidate_years_experience=float(candidate.years_experience),
            candidate_education_level=candidate.highest_education_level,
            min_years_experience=float(rule.min_years_experience),
            min_education_level=rule.min_education_level,
            skill_weight_pct=rule.skill_weight_pct,
            experience_weight_pct=rule.experience_weight_pct,
            education_weight_pct=rule.education_weight_pct,
            pass_threshold_score=float(rule.pass_threshold_score),
            rule_version=rule.version,
        )

        now = computed_at or datetime.now()

        # Step 1: flip any prior is_latest row to false.
        prior_latest = session.execute(
            select(ScreeningRun).where(
                ScreeningRun.application_id == application_id, ScreeningRun.is_latest.is_(True)
            )
        ).scalars().first()
        if prior_latest is not None:
            prior_latest.is_latest = False
            session.flush()

        # Step 2: insert the new ScreeningRun.
        run_id = _next_screening_run_id(session)
        new_run = ScreeningRun(
            screening_run_id=run_id,
            application_id=application_id,
            screening_rule_id=rule.screening_rule_id,
            is_latest=True,
            screening_rule_version=rule.version,
            screening_skill_component=result.skill_component,
            screening_experience_component=result.experience_component,
            screening_education_component=result.education_component,
            screening_education_gate_passed=result.education_gate_passed,
            screening_score=result.screening_score,
            screening_decision=result.screening_decision,
            screening_explanation=result.screening_explanation,
            computed_at=now,
        )
        session.add(new_run)
        session.flush()

        # Step 3: update Application's mirrored columns + pointer. Stage
        # is deliberately not touched here - see module docstring.
        application.screening_score = result.screening_score
        application.screening_skill_component = result.skill_component
        application.screening_experience_component = result.experience_component
        application.screening_education_component = result.education_component
        application.screening_education_gate_passed = result.education_gate_passed
        application.screening_decision = result.screening_decision
        application.screening_rule_version = rule.version
        application.screening_computed_at = now
        application.screening_explanation = result.screening_explanation
        application.latest_screening_run_id = run_id
        application.updated_at = now

        session.commit()
        return new_run
    except Exception:
        session.rollback()
        raise
