"""Candidate endpoints — read-only (candidate records are created only
as a side effect of `services/application_submission.py`, Phase 7)."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.api.errors import NotFoundError
from app.db.models import Candidate, CandidateSkill, ResumeArtifact, Skill
from app.schemas.candidate import CandidateOut, CandidateSkillOut, ResumeArtifactOut
from app.schemas.common import Page

router = APIRouter(prefix="/candidates", tags=["candidates"])


@router.get("", response_model=Page[CandidateOut])
def list_candidates(
    search: str | None = Query(None, description="Case-insensitive substring match on full_name or email"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    stmt = select(Candidate)
    count_stmt = select(func.count()).select_from(Candidate)
    if search:
        pattern = f"%{search.lower()}%"
        clause = or_(func.lower(Candidate.full_name).like(pattern), func.lower(Candidate.email).like(pattern))
        stmt = stmt.where(clause)
        count_stmt = count_stmt.where(clause)
    total = db.execute(count_stmt).scalar_one()
    rows = db.execute(stmt.order_by(Candidate.candidate_id).limit(limit).offset(offset)).scalars().all()
    return Page(items=rows, total=total, limit=limit, offset=offset)


@router.get("/{candidate_id}", response_model=CandidateOut)
def get_candidate(candidate_id: str, db: Session = Depends(get_db)):
    candidate = db.get(Candidate, candidate_id)
    if candidate is None:
        raise NotFoundError(f"Candidate {candidate_id!r} does not exist")
    return candidate


@router.get("/{candidate_id}/skills", response_model=list[CandidateSkillOut])
def get_candidate_skills(candidate_id: str, db: Session = Depends(get_db)):
    skills_by_id = {s.skill_id: s.name for s in db.execute(select(Skill)).scalars()}
    rows = db.execute(
        select(CandidateSkill).where(CandidateSkill.candidate_id == candidate_id)
    ).scalars().all()
    return [
        CandidateSkillOut(
            skill_id=row.skill_id,
            skill_name=skills_by_id.get(row.skill_id, row.skill_id),
            proficiency_level=row.proficiency_level,
            years_of_experience=float(row.years_of_experience),
            source=row.source,
        )
        for row in rows
    ]


@router.get("/{candidate_id}/resumes", response_model=list[ResumeArtifactOut])
def get_candidate_resumes(candidate_id: str, db: Session = Depends(get_db)):
    return db.execute(
        select(ResumeArtifact).where(ResumeArtifact.candidate_id == candidate_id)
    ).scalars().all()
