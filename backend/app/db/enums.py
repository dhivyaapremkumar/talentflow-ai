"""Enum value tuples shared by more than one model module — defined once so
`CandidateSkill`/`JobRequisitionSkill` (proficiency) and `Candidate`/
`ScreeningRule` (education) can never drift apart on allowed values.
"""

PROFICIENCY_LEVELS = ("Beginner", "Intermediate", "Advanced", "Expert")
EDUCATION_LEVELS = ("HighSchool", "Associate", "Bachelor", "Master", "Doctorate")
