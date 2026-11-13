"""Application/ApplicationSubmissionAttempt/ScreeningRun schemas —
data_dictionary.md §8/§8a/§8b. `ApplicationOut` carries the mirrored
screening_* columns directly (the atomic-transaction invariant Phase 7's
`services/screening.py` maintains), so the frontend never needs to join
to `ScreeningRun` just to render the current result; `ScreeningRunOut`
is exposed separately for the full history view."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ApplicationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    application_id: str
    candidate_id: str
    requisition_id: str
    resume_artifact_id: str
    applied_at: datetime
    source_channel: str
    stage: str
    screening_score: float | None
    screening_skill_component: float | None
    screening_experience_component: float | None
    screening_education_component: float | None
    screening_education_gate_passed: bool | None
    screening_decision: str | None
    screening_rule_version: int | None
    screening_computed_at: datetime | None
    screening_explanation: str | None
    latest_screening_run_id: str | None
    rejected_reason: str | None
    withdrawn_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ApplicationOutWithNames(ApplicationOut):
    candidate_name: str | None = None
    requisition_title: str | None = None


class ScreeningRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    screening_run_id: str
    application_id: str
    screening_rule_id: str
    is_latest: bool
    screening_rule_version: int
    screening_skill_component: float
    screening_experience_component: float
    screening_education_component: float
    screening_education_gate_passed: bool
    screening_score: float
    screening_decision: str
    screening_explanation: str
    computed_at: datetime


class SubmissionAttemptOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    attempt_id: str
    canonical_application_id: str
    candidate_id: str
    requisition_id: str
    submitted_at: datetime
    is_canonical: bool
    duplicate_of_attempt_id: str | None
    issue_type: str


class ApplicationSubmitIn(BaseModel):
    candidate_id: str
    requisition_id: str
    resume_artifact_id: str | None = None


class ApplicationStageTransitionIn(BaseModel):
    to_stage: str
    actor_id: str
    reason_text: str | None = None
    rejected_reason: str | None = Field(None, description="Required when to_stage='Rejected'")
