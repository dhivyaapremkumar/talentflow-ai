"""Candidate, ResumeArtifact, CandidateSkill.

No demographic fields (PROJECT_SPEC.md A-9). Each candidate gets exactly
one ResumeArtifact (is_latest=True) whose parsed fields mirror the
candidate's own fields at generation time (data_dictionary.md §6), and a
broad-ish skill set (8-16 of the 40-skill catalog) so natural overlap with
any requisition's required skills is plausible.
"""

from datetime import timedelta

from app.data_generation.entities.reference_data import EPOCH
from app.data_generation.seeding import make_faker, make_rng

EDUCATION_LEVELS = ("HighSchool", "Associate", "Bachelor", "Master", "Doctorate")
EDUCATION_WEIGHTS = (10, 15, 45, 25, 5)
SOURCE_CHANNELS = ("Referral", "Website", "LinkedIn", "Agency", "JobBoard")
PROFICIENCY_LEVELS = ("Beginner", "Intermediate", "Advanced", "Expert")
RESUME_FILE_FORMATS = ("PDF", "DOCX")


def generate_candidates(seed: int, count: int) -> list[dict]:
    fake = make_faker(seed, "candidate")
    rng = make_rng(seed, "candidate")
    rows = []
    for i in range(1, count + 1):
        candidate_id = f"CAND-{i:06d}"
        years_experience = round(min(50.0, max(0.0, rng.gammavariate(2.2, 2.3))), 1)
        created_at = EPOCH + timedelta(days=rng.randint(0, 280), hours=rng.randint(0, 23))
        rows.append(
            {
                "candidate_id": candidate_id,
                "full_name": fake.name(),
                "email": f"candidate{i:06d}@example.com",
                "phone": fake.phone_number() if rng.random() < 0.85 else None,
                "location_city": fake.city(),
                "location_country": fake.country(),
                "years_experience": years_experience,
                "highest_education_level": rng.choices(EDUCATION_LEVELS, weights=EDUCATION_WEIGHTS)[0],
                "source_channel": rng.choice(SOURCE_CHANNELS),
                "created_at": created_at,
            }
        )
    return rows


def generate_resume_artifacts(seed: int, candidates: list[dict]) -> list[dict]:
    rng = make_rng(seed, "resume_artifact")
    rows = []
    for i, cand in enumerate(candidates, start=1):
        rows.append(
            {
                "resume_artifact_id": f"RES-{i:06d}",
                "candidate_id": cand["candidate_id"],
                "file_name": f"{cand['candidate_id'].lower()}_resume.{rng.choice(['pdf', 'docx'])}",
                "file_format": rng.choice(RESUME_FILE_FORMATS),
                "parsed_years_experience": cand["years_experience"],
                "parsed_education_level": cand["highest_education_level"],
                "is_latest": True,
                "uploaded_at": cand["created_at"] + timedelta(hours=rng.randint(1, 48)),
            }
        )
    return rows


def generate_candidate_skills(seed: int, candidates: list[dict], skill_ids: list[str]) -> list[dict]:
    rng = make_rng(seed, "candidate_skill")
    rows = []
    for cand in candidates:
        n_skills = rng.randint(8, 16)
        chosen = rng.sample(skill_ids, min(n_skills, len(skill_ids)))
        # More experienced candidates skew toward higher proficiency.
        exp = cand["years_experience"]
        if exp < 2:
            weights = (50, 35, 13, 2)
        elif exp < 5:
            weights = (20, 40, 30, 10)
        elif exp < 10:
            weights = (5, 25, 45, 25)
        else:
            weights = (2, 13, 40, 45)
        for skill_id in chosen:
            proficiency = rng.choices(PROFICIENCY_LEVELS, weights=weights)[0]
            years_of_experience = round(min(exp, max(0.3, rng.uniform(0.5, exp if exp > 0 else 0.5))), 1)
            rows.append(
                {
                    "candidate_id": cand["candidate_id"],
                    "skill_id": skill_id,
                    "proficiency_level": proficiency,
                    "years_of_experience": years_of_experience,
                    "source": rng.choice(["ResumeParsed", "SelfReported"]),
                    "updated_at": cand["created_at"] + timedelta(hours=rng.randint(1, 72)),
                }
            )
    return rows
