"""Department, SystemActor, Skill, Interviewer, InterviewerAvailabilitySlot
— the four fixed-size catalog tables (PROJECT_SPEC.md A-13: 10/20/40/25,
identical in both modes) plus InterviewerAvailabilitySlot, which scales
with the number of Interview rows (computed later) but is generated here,
right after Interviewer, per architecture.md §4's order.
"""

from datetime import datetime, timedelta

from app.data_generation.seeding import make_faker, make_rng

DEPARTMENT_NAMES = [
    "Engineering",
    "Product",
    "Data Science",
    "Design",
    "Sales",
    "Marketing",
    "Customer Success",
    "Human Resources",
    "Finance",
    "Operations",
]

SKILL_CATALOG = [
    ("Python", "Technical"),
    ("Java", "Technical"),
    ("JavaScript", "Technical"),
    ("TypeScript", "Technical"),
    ("Go", "Technical"),
    ("C++", "Technical"),
    ("SQL", "Technical"),
    ("React", "Technical"),
    ("Node.js", "Technical"),
    ("Django", "Technical"),
    ("Spring Boot", "Technical"),
    ("Machine Learning", "Technical"),
    ("Data Engineering", "Technical"),
    ("REST API Design", "Technical"),
    ("Microservices", "Technical"),
    ("System Design", "Technical"),
    ("Unit Testing", "Technical"),
    ("CI/CD", "Technical"),
    ("Mobile Development", "Technical"),
    ("Cloud Architecture", "Technical"),
    ("AWS", "Tool"),
    ("Azure", "Tool"),
    ("Docker", "Tool"),
    ("Kubernetes", "Tool"),
    ("Git", "Tool"),
    ("Jira", "Tool"),
    ("Tableau", "Tool"),
    ("Salesforce", "Tool"),
    ("Figma", "Tool"),
    ("Excel", "Tool"),
    ("Fintech Domain Knowledge", "Domain"),
    ("Healthcare Domain Knowledge", "Domain"),
    ("E-commerce Domain Knowledge", "Domain"),
    ("Recruiting Domain Knowledge", "Domain"),
    ("Supply Chain Domain Knowledge", "Domain"),
    ("Communication", "Soft"),
    ("Leadership", "Soft"),
    ("Problem Solving", "Soft"),
    ("Teamwork", "Soft"),
    ("Negotiation", "Soft"),
]

ACTOR_ROLE_PLAN = [
    ("BUSINESS_REQUESTER", 6),
    ("APPROVER", 4),
    ("PROCESS_OWNER", 6),
    ("OPERATIONS_ANALYST", 2),
    ("SYSTEM_ADMINISTRATOR", 2),
]

INTERVIEWER_TITLES = [
    "Senior Software Engineer",
    "Engineering Manager",
    "Staff Engineer",
    "Product Manager",
    "Principal Engineer",
    "Data Science Lead",
    "Design Lead",
    "Director of Engineering",
]

EPOCH = datetime(2025, 1, 6)


def generate_departments(seed: int) -> list[dict]:
    rows = []
    for i, name in enumerate(DEPARTMENT_NAMES, start=1):
        rows.append(
            {
                "department_id": f"DEPT-{i:04d}",
                "name": name,
                "cost_center_code": f"CC-{i:04d}",
                "created_at": EPOCH,
            }
        )
    return rows


def generate_skills(seed: int) -> list[dict]:
    rows = []
    for i, (name, category) in enumerate(SKILL_CATALOG, start=1):
        rows.append(
            {
                "skill_id": f"SKL-{i:04d}",
                "name": name,
                "category": category,
                "is_active": True,
            }
        )
    return rows


def generate_system_actors(seed: int, department_ids: list[str]) -> list[dict]:
    fake = make_faker(seed, "system_actor")
    rng = make_rng(seed, "system_actor")
    rows = []
    actor_num = 1
    for role, count in ACTOR_ROLE_PLAN:
        for _ in range(count):
            needs_department = role in ("BUSINESS_REQUESTER", "PROCESS_OWNER")
            rows.append(
                {
                    "actor_id": f"ACT-{actor_num:04d}",
                    "full_name": fake.name(),
                    "role": role,
                    "department_id": rng.choice(department_ids) if needs_department else None,
                    "email": f"actor{actor_num:04d}@talentflow.example",
                    "is_active": True,
                    "created_at": EPOCH + timedelta(days=rng.randint(0, 30)),
                }
            )
            actor_num += 1
    return rows


def generate_interviewers(seed: int, department_ids: list[str]) -> list[dict]:
    fake = make_faker(seed, "interviewer")
    rng = make_rng(seed, "interviewer")
    rows = []
    for i in range(1, 26):
        rows.append(
            {
                "interviewer_id": f"IVR-{i:04d}",
                "full_name": fake.name(),
                "email": f"interviewer{i:04d}@talentflow.example",
                "department_id": rng.choice(department_ids),
                "title": rng.choice(INTERVIEWER_TITLES),
                "is_active": True,
            }
        )
    return rows


def generate_availability_slots(seed: int, interviewer_ids: list[str], window_days: int = 280) -> list[dict]:
    """One 09:00-17:00 Mon-Fri slot per interviewer per weekday across the
    whole generation window, so every Interview scheduled later always has
    a real availability window to fall inside — the baseline has no
    unavailable-interviewer anomalies (that's Phase 5)."""
    rows = []
    slot_num = 1
    start_day = EPOCH
    weekdays = [start_day + timedelta(days=d) for d in range(window_days) if (start_day + timedelta(days=d)).weekday() < 5]
    for interviewer_id in interviewer_ids:
        for day in weekdays:
            rows.append(
                {
                    "slot_id": f"AVAIL-{slot_num:06d}",
                    "interviewer_id": interviewer_id,
                    "start_datetime": day.replace(hour=9, minute=0),
                    "end_datetime": day.replace(hour=17, minute=0),
                    "is_booked": False,
                }
            )
            slot_num += 1
    return rows
