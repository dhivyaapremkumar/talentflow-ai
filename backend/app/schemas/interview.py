"""Interview/Feedback schemas — data_dictionary.md §12/§13."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class InterviewOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    interview_id: str
    application_id: str
    interviewer_id: str
    round_number: int
    round_type: str
    scheduled_start: datetime
    scheduled_end: datetime
    status: str
    location_mode: str
    created_at: datetime
    updated_at: datetime


class FeedbackOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    feedback_id: str
    interview_id: str
    interviewer_id: str
    recommendation: str
    overall_score: int
    strengths_text: str | None
    concerns_text: str | None
    submitted_at: datetime


class InterviewScheduleIn(BaseModel):
    application_id: str
    interviewer_id: str
    round_type: str
    scheduled_start: datetime
    scheduled_end: datetime
    location_mode: str = "Remote"


class InterviewStatusTransitionIn(BaseModel):
    to_status: str


class FeedbackSubmitIn(BaseModel):
    interviewer_id: str
    recommendation: str
    overall_score: int
    submitted_at: datetime
    strengths_text: str | None = None
    concerns_text: str | None = None
