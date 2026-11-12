"""Import every model module here so Base.metadata is fully populated
whenever `app.db.models` is imported — required for create_all() and for
ForeignKey target resolution across modules.

Phase 2, Unit 1 (this commit): Department, Skill, SystemActor, Interviewer,
InterviewerAvailabilitySlot. Remaining tables are added unit by unit.
"""

from app.db.models.actor import SystemActor
from app.db.models.department import Department
from app.db.models.interview import Interviewer, InterviewerAvailabilitySlot
from app.db.models.skill import Skill

__all__ = [
    "Department",
    "Skill",
    "SystemActor",
    "Interviewer",
    "InterviewerAvailabilitySlot",
]
