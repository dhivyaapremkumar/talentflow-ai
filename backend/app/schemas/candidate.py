"""Candidate/ResumeArtifact/CandidateSkill schemas — data_dictionary.md
§5/§6/§7. Deliberately excludes demographic fields, same structural
guarantee the model itself enforces (no such column exists to expose)."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class CandidateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    candidate_id: str
    full_name: str
    email: str
    phone: str | None
    location_city: str
    location_country: str
    years_experience: float
    highest_education_level: str
    source_channel: str
    created_at: datetime


class CandidateSkillOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    skill_id: str
    skill_name: str
    proficiency_level: str
    years_of_experience: float
    source: str


class ResumeArtifactOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    resume_artifact_id: str
    file_name: str
    file_format: str
    parsed_years_experience: float
    parsed_education_level: str
    is_latest: bool
    uploaded_at: datetime
