"""Read-only reference-data schemas — Department, SystemActor, Interviewer,
InterviewerAvailabilitySlot. `SystemActor` carries no authentication
(data_dictionary.md §18) — the frontend uses it only to let a user pick
"acting as" an actor when exercising a lifecycle transition, so the hard
role gates have something to demonstrate; this is explicitly documented
as not a real access-control mechanism (`api/v1/actors.py`'s docstring).
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class DepartmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    department_id: str
    name: str
    cost_center_code: str


class SystemActorOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    actor_id: str
    full_name: str
    role: str
    department_id: str | None
    email: str
    is_active: bool


class InterviewerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    interviewer_id: str
    full_name: str
    email: str
    department_id: str
    title: str
    is_active: bool


class AvailabilitySlotOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    slot_id: str
    interviewer_id: str
    start_datetime: datetime
    end_datetime: datetime
    is_booked: bool
