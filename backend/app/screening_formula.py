"""The screening score formula — business_rules.md §5 (APPROVED, three-weight
model). Defined exactly once, as plain functions over plain values (no ORM,
no DB session), so it can be imported from anywhere without pulling in
unrelated coupling — `architecture.md` §6's "one implementation, never
duplicated or allowed to drift" principle.

**Why this lives here and not in `services/` (flagged deviation, not a
silent one):** `architecture.md` §6's module-boundary diagram states
`data_generation/ → db/models/ (never into api/ or services/)`, but also
says the formula should be "defined once in services/ and imported by both
services/ and validation/." `data_generation/` (Phase 3) needs the exact
same formula to produce a baseline whose `ScreeningRun` rows are genuinely
correct, not just plausible-looking. Since `services/` doesn't exist yet
(Phase 7) and `data_generation/` is architecturally forbidden from
importing it, this module sits at `app/` top level — owned by neither
`services/` nor `data_generation/` — so both can import it with no
import-direction violation. `services/screening.py` (Phase 7) and
`validation/rules/screening_recompute.py` (Phase 4/6) must import from
here rather than redefining this logic.
"""

from dataclasses import dataclass

EDUCATION_RANKS = {
    "HighSchool": 1,
    "Associate": 2,
    "Bachelor": 3,
    "Master": 4,
    "Doctorate": 5,
}


def education_rank(level: str) -> int:
    return EDUCATION_RANKS[level]


def skill_match(candidate_proficiency: str | None, min_proficiency: str) -> float:
    """1.0 if candidate meets/exceeds the minimum, 0.5 if below it but present,
    0.0 if the candidate has no CandidateSkill row for this skill at all."""
    if candidate_proficiency is None:
        return 0.0
    proficiency_ranks = {"Beginner": 1, "Intermediate": 2, "Advanced": 3, "Expert": 4}
    if proficiency_ranks[candidate_proficiency] >= proficiency_ranks[min_proficiency]:
        return 1.0
    return 0.5


@dataclass(frozen=True)
class ScreeningResult:
    skill_component: float
    experience_component: float
    education_component: float
    education_gate_passed: bool
    screening_score: float
    screening_decision: str
    screening_explanation: str


def compute_screening_result(
    *,
    required_skills: list[dict],
    candidate_skills_by_skill_id: dict[str, dict],
    candidate_years_experience: float,
    candidate_education_level: str,
    min_years_experience: float,
    min_education_level: str,
    skill_weight_pct: int,
    experience_weight_pct: int,
    education_weight_pct: int,
    pass_threshold_score: float,
    rule_version: int,
) -> ScreeningResult:
    """`required_skills`: list of {"skill_id", "skill_name", "weight_pct",
    "min_proficiency_level"}. `candidate_skills_by_skill_id`: skill_id ->
    {"proficiency_level"}."""

    skill_component = 0.0
    skill_detail_parts = []
    matched_weight = 0.0
    for req in required_skills:
        candidate_skill = candidate_skills_by_skill_id.get(req["skill_id"])
        proficiency = candidate_skill["proficiency_level"] if candidate_skill else None
        match = skill_match(proficiency, req["min_proficiency_level"])
        skill_component += (req["weight_pct"] / 100) * match
        matched_weight += req["weight_pct"] * match
    skill_detail_parts.append(
        f"{round(matched_weight / 100, 1)}/{round(sum(r['weight_pct'] for r in required_skills) / 100, 1)} weighted"
    )

    if min_years_experience > 0:
        experience_component = min(1.0, candidate_years_experience / min_years_experience)
    else:
        experience_component = 1.0

    education_component = min(
        1.0, education_rank(candidate_education_level) / education_rank(min_education_level)
    )
    education_gate_passed = education_rank(candidate_education_level) >= education_rank(
        min_education_level
    )

    screening_score = round(
        100
        * (
            (skill_weight_pct / 100) * skill_component
            + (experience_weight_pct / 100) * experience_component
            + (education_weight_pct / 100) * education_component
        ),
        2,
    )
    screening_decision = (
        "Pass" if education_gate_passed and screening_score >= pass_threshold_score else "Fail"
    )

    gate_text = "gate passed" if education_gate_passed else "gate failed"
    explanation = (
        f"Skill match {round(skill_component * 100, 1)}% ({skill_detail_parts[0]}); "
        f"experience {round(experience_component * 100, 1)}% "
        f"({candidate_years_experience}y vs {min_years_experience}y min); "
        f"education {round(education_component * 100, 1)}% "
        f"({candidate_education_level} vs {min_education_level} min, {gate_text}); "
        f"weighted score {screening_score} "
        f"({skill_weight_pct}/{experience_weight_pct}/{education_weight_pct}) "
        f"vs threshold {pass_threshold_score} (rule v{rule_version}) → {screening_decision}"
    )
    if len(explanation) > 500:
        explanation = explanation[:497] + "..."

    return ScreeningResult(
        skill_component=round(skill_component, 4),
        experience_component=round(experience_component, 4),
        education_component=round(education_component, 4),
        education_gate_passed=education_gate_passed,
        screening_score=screening_score,
        screening_decision=screening_decision,
        screening_explanation=explanation,
    )
