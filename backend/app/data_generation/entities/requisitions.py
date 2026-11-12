"""JobRequisition, JobRequisitionSkill, ScreeningRule.

Every requisition gets exactly one `ScreeningRule` (version=1,
is_current=True) and 3-5 required skills with weight_pct summing to
exactly 100 — business_rules.md §9's documented baseline behavior (the
versioning/redefinition mechanism exists structurally but isn't exercised
by this synthetic dataset).
"""

from datetime import timedelta

from app.data_generation.entities.reference_data import EPOCH
from app.data_generation.seeding import make_faker, make_rng

LEVELS = ("Junior", "Mid", "Senior", "Lead", "Principal")
EMPLOYMENT_TYPES = ("FullTime", "Contract", "Intern")
EDUCATION_LEVELS = ("HighSchool", "Associate", "Bachelor", "Master", "Doctorate")
PROFICIENCY_LEVELS = ("Beginner", "Intermediate", "Advanced", "Expert")

# (min_years_experience, min_education_level, salary_min, salary_max) by level.
LEVEL_PROFILE = {
    "Junior": (0.0, "Bachelor", 60000, 85000),
    "Mid": (2.0, "Bachelor", 85000, 115000),
    "Senior": (5.0, "Bachelor", 115000, 155000),
    "Lead": (8.0, "Master", 145000, 190000),
    "Principal": (10.0, "Master", 175000, 230000),
}

TITLE_PREFIX_BY_DEPARTMENT = {
    "Engineering": "Software Engineer",
    "Product": "Product Manager",
    "Data Science": "Data Scientist",
    "Design": "Product Designer",
    "Sales": "Account Executive",
    "Marketing": "Marketing Manager",
    "Customer Success": "Customer Success Manager",
    "Human Resources": "HR Business Partner",
    "Finance": "Financial Analyst",
    "Operations": "Operations Manager",
}

# Status plan: fraction of requisitions landing in each final status.
# Closed/Cancelled requisitions only ever receive applications in terminal
# stages (enforced in entities/applications.py) — the clean baseline has no
# ClosedReqActiveApplications incidents (that anomaly is Phase 5 only).
STATUS_PLAN = [
    ("Open", 0.75),
    ("Closed", 0.15),
    ("OnHold", 0.07),
    ("Cancelled", 0.03),
]


def _pick_status(rng, n: int) -> list[str]:
    counts = []
    remaining = n
    for i, (_, frac) in enumerate(STATUS_PLAN):
        if i == len(STATUS_PLAN) - 1:
            counts.append(remaining)
        else:
            c = round(n * frac)
            counts.append(c)
            remaining -= c
    statuses = []
    for (status, _), count in zip(STATUS_PLAN, counts):
        statuses.extend([status] * max(0, count))
    rng.shuffle(statuses)
    return statuses[:n]


def generate_requisitions(
    seed: int, count: int, department_ids: list[str], department_names_by_id: dict, actor_ids_by_role: dict
) -> list[dict]:
    fake = make_faker(seed, "job_requisition")
    rng = make_rng(seed, "job_requisition")
    statuses = _pick_status(rng, count)

    rows = []
    for i in range(1, count + 1):
        requisition_id = f"REQ-{i:05d}"
        department_id = rng.choice(department_ids)
        dept_name = department_names_by_id[department_id]
        level = rng.choice(LEVELS)
        _, _, salary_min, salary_max = LEVEL_PROFILE[level]
        salary_min = salary_min + rng.randint(-3000, 3000)
        salary_max = max(salary_min + 10000, salary_max + rng.randint(-3000, 3000))
        status = statuses[i - 1]

        created_at = EPOCH + timedelta(days=rng.randint(0, 120))
        opened_at = (created_at + timedelta(days=6)).date()
        closed_at = None
        target_close_date = (created_at + timedelta(days=90)).date()
        if status in ("Closed", "Cancelled"):
            closed_at = (created_at + timedelta(days=rng.randint(45, 150))).date()

        title_base = TITLE_PREFIX_BY_DEPARTMENT.get(dept_name, "Specialist")
        title = f"{level} {title_base}" if level != "Mid" else title_base

        rows.append(
            {
                "requisition_id": requisition_id,
                "department_id": department_id,
                "title": title,
                "level": level,
                "employment_type": rng.choices(EMPLOYMENT_TYPES, weights=[80, 15, 5])[0],
                "status": status,
                "salary_min": salary_min,
                "salary_max": salary_max,
                "headcount": rng.choices([1, 2, 3], weights=[70, 20, 10])[0],
                "requested_by_actor_id": rng.choice(actor_ids_by_role["BUSINESS_REQUESTER"]),
                "opened_at": opened_at,
                "target_close_date": target_close_date,
                "closed_at": closed_at,
                "created_at": created_at,
            }
        )
    return rows


def generate_requisition_skills(seed: int, requisitions: list[dict], skill_ids: list[str]) -> list[dict]:
    rng = make_rng(seed, "job_requisition_skill")
    rows = []
    for req in requisitions:
        n_skills = rng.randint(3, 5)
        chosen = rng.sample(skill_ids, n_skills)
        cuts = sorted(rng.sample(range(1, 100), n_skills - 1))
        weights = [cuts[0]] + [cuts[i] - cuts[i - 1] for i in range(1, len(cuts))] + [100 - cuts[-1]]
        for skill_id, weight in zip(chosen, weights):
            rows.append(
                {
                    "requisition_id": req["requisition_id"],
                    "skill_id": skill_id,
                    "min_proficiency_level": rng.choice(PROFICIENCY_LEVELS[1:]),
                    "is_mandatory": rng.random() < 0.6,
                    "weight_pct": weight,
                }
            )
    return rows


def generate_screening_rules(seed: int, requisitions: list[dict]) -> list[dict]:
    rng = make_rng(seed, "screening_rule")
    rows = []
    for i, req in enumerate(requisitions, start=1):
        min_years, min_education, _, _ = LEVEL_PROFILE[req["level"]]
        rows.append(
            {
                "screening_rule_id": f"SCR-{i:04d}",
                "requisition_id": req["requisition_id"],
                "is_current": True,
                "version": 1,
                "min_years_experience": min_years,
                "min_education_level": min_education,
                "skill_weight_pct": 50,
                "experience_weight_pct": 30,
                "education_weight_pct": 20,
                "pass_threshold_score": 70.0,
                "created_at": req["created_at"] + timedelta(days=1),
            }
        )
    return rows
