"""VAL-05 — Screening score calculation + reproducibility,
validation_strategy.md §5.

Recomputes every `ScreeningRun` from the exact `ScreeningRule` row it
references (not "whichever rule is current now" — `business_rules.md`
§4's reproducibility guarantee) via `app.screening_formula`, the same
module `data_generation/entities/applications.py` used to produce the
baseline — one implementation, never duplicated (architecture.md §6).
Float tolerance 0.01 on the three components/score; exact match on the
two boolean/enum decisions and the explanation string (the template is
deterministic, so a mismatch there is a real defect, not noise).
"""

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
from app.validation.report import Finding

RULE_ID = "VAL-05"
RULE_CATEGORY = "screening_recompute"

FLOAT_TOLERANCE = 0.01


def _close(a: float, b: float) -> bool:
    return abs(float(a) - float(b)) <= FLOAT_TOLERANCE


def check(session: Session) -> list[Finding]:
    findings: list[Finding] = []

    candidates = {c.candidate_id: c for c in session.execute(select(Candidate)).scalars()}
    rules = {r.screening_rule_id: r for r in session.execute(select(ScreeningRule)).scalars()}
    applications = {a.application_id: a for a in session.execute(select(Application)).scalars()}
    runs = list(session.execute(select(ScreeningRun)).scalars())

    required_skills_by_req: dict[str, list] = {}
    for jrs in session.execute(select(JobRequisitionSkill)).scalars():
        required_skills_by_req.setdefault(jrs.requisition_id, []).append(
            {
                "skill_id": jrs.skill_id,
                "weight_pct": jrs.weight_pct,
                "min_proficiency_level": jrs.min_proficiency_level,
            }
        )

    skill_index: dict[str, dict] = {}
    for cs in session.execute(select(CandidateSkill)).scalars():
        skill_index.setdefault(cs.candidate_id, {})[cs.skill_id] = {
            "proficiency_level": cs.proficiency_level
        }

    # Rule weight-sum check.
    for rule in rules.values():
        total = rule.skill_weight_pct + rule.experience_weight_pct + rule.education_weight_pct
        if total != 100:
            findings.append(
                Finding(
                    RULE_ID, RULE_CATEGORY, "screening_rule", rule.screening_rule_id,
                    f"skill_weight_pct+experience_weight_pct+education_weight_pct = {total}, not 100",
                    "violation",
                )
            )

    # Per-application-id is_latest cardinality: at most one true.
    latest_count_by_app: dict[str, int] = {}
    for run in runs:
        if run.is_latest:
            latest_count_by_app[run.application_id] = latest_count_by_app.get(run.application_id, 0) + 1
    for app_id, count in latest_count_by_app.items():
        if count > 1:
            findings.append(
                Finding(
                    RULE_ID, RULE_CATEGORY, "application", app_id,
                    f"{count} ScreeningRun rows with is_latest=true (expected at most 1)",
                    "violation",
                )
            )

    for run in runs:
        app = applications.get(run.application_id)
        candidate = candidates.get(app.candidate_id) if app else None
        rule = rules.get(run.screening_rule_id)
        if app is None or candidate is None or rule is None:
            continue  # already reported by VAL-02 (fk_integrity)

        required_skills = required_skills_by_req.get(app.requisition_id, [])
        recomputed = compute_screening_result(
            required_skills=required_skills,
            candidate_skills_by_skill_id=skill_index.get(candidate.candidate_id, {}),
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

        stored_fields = {
            "screening_skill_component": (run.screening_skill_component, recomputed.skill_component),
            "screening_experience_component": (
                run.screening_experience_component,
                recomputed.experience_component,
            ),
            "screening_education_component": (
                run.screening_education_component,
                recomputed.education_component,
            ),
            "screening_score": (run.screening_score, recomputed.screening_score),
        }
        for field_name, (stored, expected) in stored_fields.items():
            if not _close(stored, expected):
                findings.append(
                    Finding(
                        RULE_ID, RULE_CATEGORY, "screening_run", run.screening_run_id,
                        f"{field_name}={stored} does not match recomputed value {expected} "
                        f"(tolerance {FLOAT_TOLERANCE})",
                        "violation",
                    )
                )

        if run.screening_education_gate_passed != recomputed.education_gate_passed:
            findings.append(
                Finding(
                    RULE_ID, RULE_CATEGORY, "screening_run", run.screening_run_id,
                    f"screening_education_gate_passed={run.screening_education_gate_passed} does not "
                    f"match recomputed {recomputed.education_gate_passed}",
                    "violation",
                )
            )
        if run.screening_decision != recomputed.screening_decision:
            findings.append(
                Finding(
                    RULE_ID, RULE_CATEGORY, "screening_run", run.screening_run_id,
                    f"screening_decision={run.screening_decision!r} does not match recomputed "
                    f"{recomputed.screening_decision!r}",
                    "violation",
                )
            )
        if run.screening_explanation != recomputed.screening_explanation:
            findings.append(
                Finding(
                    RULE_ID, RULE_CATEGORY, "screening_run", run.screening_run_id,
                    "screening_explanation does not byte-for-byte match the deterministic template "
                    "recompute",
                    "violation",
                )
            )

        # Gate-override guarantee: gate failed => decision must be Fail,
        # regardless of score (business_rules.md Sec5, CAND-000104 proof case).
        if not run.screening_education_gate_passed and run.screening_decision != "Fail":
            findings.append(
                Finding(
                    RULE_ID, RULE_CATEGORY, "screening_run", run.screening_run_id,
                    f"screening_education_gate_passed=False but screening_decision="
                    f"{run.screening_decision!r} (must be 'Fail' regardless of score)",
                    "violation",
                )
            )

        # Application's nine mirrored columns must exactly equal the
        # is_latest=true run referenced by latest_screening_run_id.
        if run.is_latest and app.latest_screening_run_id == run.screening_run_id:
            mirrored = {
                "screening_score": (app.screening_score, run.screening_score),
                "screening_skill_component": (app.screening_skill_component, run.screening_skill_component),
                "screening_experience_component": (
                    app.screening_experience_component,
                    run.screening_experience_component,
                ),
                "screening_education_component": (
                    app.screening_education_component,
                    run.screening_education_component,
                ),
                "screening_education_gate_passed": (
                    app.screening_education_gate_passed,
                    run.screening_education_gate_passed,
                ),
                "screening_decision": (app.screening_decision, run.screening_decision),
                "screening_rule_version": (app.screening_rule_version, run.screening_rule_version),
                "screening_computed_at": (app.screening_computed_at, run.computed_at),
                "screening_explanation": (app.screening_explanation, run.screening_explanation),
            }
            for field_name, (app_value, run_value) in mirrored.items():
                mismatch = (
                    not _close(app_value, run_value)
                    if isinstance(app_value, (int, float)) and not isinstance(app_value, bool)
                    else app_value != run_value
                )
                if mismatch:
                    findings.append(
                        Finding(
                            RULE_ID, RULE_CATEGORY, "application", app.application_id,
                            f"mirrored field {field_name}={app_value!r} does not match the "
                            f"is_latest ScreeningRun's {run_value!r}",
                            "violation",
                        )
                    )

    return findings
