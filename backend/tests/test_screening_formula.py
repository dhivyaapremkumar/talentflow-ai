"""Validates app.screening_formula against the hand-verified worked examples
in business_rules.md Sec5a (CAND-000101..105, plus the 70.00/69.25 boundary
pair). This formula is introduced in Phase 3 (the data generator needs it to
produce a genuinely correct baseline) and is reused as-is by Phase 4's
validation engine and Phase 7's screening service — never redefined.
"""

from app.screening_formula import compute_screening_result

RULE = {
    "min_years_experience": 4.0,
    "min_education_level": "Bachelor",
    "skill_weight_pct": 50,
    "experience_weight_pct": 30,
    "education_weight_pct": 20,
    "pass_threshold_score": 70.0,
    "rule_version": 1,
}

REQUIRED_SKILLS = [
    {"skill_id": "SKL-PY", "skill_name": "Python", "weight_pct": 60, "min_proficiency_level": "Advanced"},
    {"skill_id": "SKL-SQL", "skill_name": "SQL", "weight_pct": 40, "min_proficiency_level": "Intermediate"},
]


def _run(candidate_skills: dict, years_exp: float, education: str):
    return compute_screening_result(
        required_skills=REQUIRED_SKILLS,
        candidate_skills_by_skill_id=candidate_skills,
        candidate_years_experience=years_exp,
        candidate_education_level=education,
        **RULE,
    )


def test_cand_000101_expert_advanced_master():
    result = _run(
        {"SKL-PY": {"proficiency_level": "Expert"}, "SKL-SQL": {"proficiency_level": "Advanced"}},
        years_exp=6.0,
        education="Master",
    )
    assert result.skill_component == 1.00
    assert result.experience_component == 1.00
    assert result.education_component == 1.00
    assert result.education_gate_passed is True
    assert result.screening_score == 100.00
    assert result.screening_decision == "Pass"


def test_cand_000102_intermediate_intermediate_bachelor():
    result = _run(
        {"SKL-PY": {"proficiency_level": "Intermediate"}, "SKL-SQL": {"proficiency_level": "Intermediate"}},
        years_exp=4.0,
        education="Bachelor",
    )
    assert result.skill_component == 0.70
    assert result.experience_component == 1.00
    assert result.education_component == 1.00
    assert result.screening_score == 85.00
    assert result.screening_decision == "Pass"


def test_cand_000103_none_beginner_bachelor():
    result = _run(
        {"SKL-SQL": {"proficiency_level": "Beginner"}},
        years_exp=2.0,
        education="Bachelor",
    )
    assert result.skill_component == 0.20
    assert result.experience_component == 0.50
    assert result.education_component == 1.00
    assert result.education_gate_passed is True
    assert result.screening_score == 45.00
    assert result.screening_decision == "Fail"


def test_cand_000104_gate_overrides_high_score():
    result = _run(
        {"SKL-PY": {"proficiency_level": "Expert"}, "SKL-SQL": {"proficiency_level": "Advanced"}},
        years_exp=8.0,
        education="Associate",
    )
    assert result.skill_component == 1.00
    assert result.experience_component == 1.00
    assert round(result.education_component, 3) == 0.667
    assert result.education_gate_passed is False
    assert result.screening_score == 93.33
    assert result.screening_decision == "Fail"


def test_cand_000105_fails_everywhere():
    result = _run({}, years_exp=0.0, education="HighSchool")
    assert result.skill_component == 0.00
    assert result.experience_component == 0.00
    assert round(result.education_component, 3) == 0.333
    assert result.education_gate_passed is False
    assert result.screening_score == 6.67
    assert result.screening_decision == "Fail"


def test_boundary_pair_70_00_pass_inclusive():
    required_skills = [
        {"skill_id": "SKL-A", "skill_name": "A", "weight_pct": 40, "min_proficiency_level": "Advanced"},
        {"skill_id": "SKL-B", "skill_name": "B", "weight_pct": 60, "min_proficiency_level": "Advanced"},
    ]
    result = compute_screening_result(
        required_skills=required_skills,
        candidate_skills_by_skill_id={"SKL-A": {"proficiency_level": "Advanced"}},
        candidate_years_experience=4.0,
        candidate_education_level="Bachelor",
        **RULE,
    )
    assert result.skill_component == 0.40
    assert result.experience_component == 1.00
    assert result.screening_score == 70.00
    assert result.screening_decision == "Pass"


def test_boundary_pair_69_25_fail():
    required_skills = [
        {"skill_id": "SKL-A", "skill_name": "A", "weight_pct": 40, "min_proficiency_level": "Advanced"},
        {"skill_id": "SKL-B", "skill_name": "B", "weight_pct": 60, "min_proficiency_level": "Advanced"},
    ]
    result = compute_screening_result(
        required_skills=required_skills,
        candidate_skills_by_skill_id={"SKL-A": {"proficiency_level": "Advanced"}},
        candidate_years_experience=3.9,
        candidate_education_level="Bachelor",
        **RULE,
    )
    assert result.skill_component == 0.40
    assert result.experience_component == 0.975
    assert result.screening_score == 69.25
    assert result.screening_decision == "Fail"
