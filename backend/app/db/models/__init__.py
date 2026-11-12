"""Import every model module here so Base.metadata is fully populated
whenever `app.db.models` is imported — required for create_all() and for
ForeignKey target resolution across modules.

Phase 2, Unit 1: Department, Skill, SystemActor, Interviewer,
InterviewerAvailabilitySlot.
Phase 2, Unit 2: JobRequisition, JobRequisitionSkill, ScreeningRule.
Phase 2, Unit 3: Candidate, ResumeArtifact, CandidateSkill.
Phase 2, Unit 4: Application, ApplicationSubmissionAttempt, ScreeningRun.
Phase 2, Unit 5: Interview, Feedback.
Phase 2, Unit 6: Offer.
Phase 2, Unit 7: RequisitionStatusHistory, ApplicationStageHistory,
OfferStatusHistory.
Phase 2, Unit 8 (this commit, FINAL unit): AnomalyLabel, GenerationRun.
All 22 tables are now built.
"""

from app.db.models.actor import SystemActor
from app.db.models.anomaly import AnomalyLabel
from app.db.models.application import Application, ApplicationSubmissionAttempt
from app.db.models.candidate import Candidate, ResumeArtifact
from app.db.models.department import Department
from app.db.models.generation_run import GenerationRun
from app.db.models.history import (
    ApplicationStageHistory,
    OfferStatusHistory,
    RequisitionStatusHistory,
)
from app.db.models.interview import Feedback, Interview, Interviewer, InterviewerAvailabilitySlot
from app.db.models.offer import Offer
from app.db.models.requisition import JobRequisition, JobRequisitionSkill
from app.db.models.screening import ScreeningRule, ScreeningRun
from app.db.models.skill import CandidateSkill, Skill

__all__ = [
    "Department",
    "Skill",
    "SystemActor",
    "Interviewer",
    "InterviewerAvailabilitySlot",
    "JobRequisition",
    "JobRequisitionSkill",
    "ScreeningRule",
    "Candidate",
    "ResumeArtifact",
    "CandidateSkill",
    "Application",
    "ApplicationSubmissionAttempt",
    "ScreeningRun",
    "Interview",
    "Feedback",
    "Offer",
    "RequisitionStatusHistory",
    "ApplicationStageHistory",
    "OfferStatusHistory",
    "AnomalyLabel",
    "GenerationRun",
]
