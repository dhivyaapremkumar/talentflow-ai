"""Import every model module here so Base.metadata is fully populated
whenever `app.db.models` is imported — required for create_all() and for
ForeignKey target resolution across modules.

Phase 2, Unit 1: Department, Skill, SystemActor, Interviewer,
InterviewerAvailabilitySlot.
Phase 2, Unit 2 (this commit): JobRequisition, JobRequisitionSkill,
ScreeningRule.
Remaining tables are added unit by unit.
"""

from app.db.models.actor import SystemActor
from app.db.models.department import Department
from app.db.models.interview import Interviewer, InterviewerAvailabilitySlot
from app.db.models.requisition import JobRequisition, JobRequisitionSkill
from app.db.models.screening import ScreeningRule
from app.db.models.skill import Skill

__all__ = [
    "Department",
    "Skill",
    "SystemActor",
    "Interviewer",
    "InterviewerAvailabilitySlot",
    "JobRequisition",
    "JobRequisitionSkill",
    "ScreeningRule",
]
