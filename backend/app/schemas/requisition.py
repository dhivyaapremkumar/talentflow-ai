"""JobRequisition request/response schemas — mirrors data_dictionary.md
§2's field list for the fields the dashboard actually displays."""

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class RequisitionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    requisition_id: str
    department_id: str
    title: str
    level: str
    employment_type: str
    status: str
    salary_min: int
    salary_max: int
    headcount: int
    requested_by_actor_id: str
    opened_at: date | None
    target_close_date: date | None
    closed_at: date | None
    created_at: datetime


class RequisitionTransitionIn(BaseModel):
    to_status: str = Field(..., description="Target JobRequisition.status value")
    actor_id: str = Field(..., description="SystemActor performing the transition")
    reason_text: str | None = None
