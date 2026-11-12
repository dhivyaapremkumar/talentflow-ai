"""VAL-06 — Interview scheduling / interviewer availability,
validation_strategy.md §6.

Expected zero at baseline; exactly 15 (full) / 3 (starter) post-injection
(UnavailableInterviewer, Phase 5 — not yet exercised, since Phase 5
doesn't exist in this codebase yet).
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Interview, InterviewerAvailabilitySlot
from app.validation.report import Finding

RULE_ID = "VAL-06"
RULE_CATEGORY = "scheduling_conflicts"


def check(session: Session) -> list[Finding]:
    findings: list[Finding] = []

    slots_by_interviewer: dict[str, list] = {}
    for slot in session.execute(select(InterviewerAvailabilitySlot)).scalars():
        slots_by_interviewer.setdefault(slot.interviewer_id, []).append(slot)

    interviews = list(session.execute(select(Interview)).scalars())
    interviews_by_interviewer: dict[str, list] = {}
    for iv in interviews:
        interviews_by_interviewer.setdefault(iv.interviewer_id, []).append(iv)

    for iv in interviews:
        slots = slots_by_interviewer.get(iv.interviewer_id, [])
        contained = any(
            slot.start_datetime <= iv.scheduled_start and iv.scheduled_end <= slot.end_datetime
            for slot in slots
        )
        if not contained:
            findings.append(
                Finding(
                    RULE_ID, RULE_CATEGORY, "interview", iv.interview_id,
                    f"[{iv.scheduled_start}, {iv.scheduled_end}) is not fully contained in any "
                    f"availability slot for interviewer {iv.interviewer_id}",
                    "violation",
                )
            )

    for interviewer_id, ivs in interviews_by_interviewer.items():
        ordered = sorted(ivs, key=lambda i: i.scheduled_start)
        for prev, curr in zip(ordered, ordered[1:]):
            if curr.scheduled_start < prev.scheduled_end:
                findings.append(
                    Finding(
                        RULE_ID, RULE_CATEGORY, "interview", curr.interview_id,
                        f"overlaps interview {prev.interview_id} for the same interviewer "
                        f"({interviewer_id}): [{curr.scheduled_start}, {curr.scheduled_end}) vs "
                        f"[{prev.scheduled_start}, {prev.scheduled_end})",
                        "violation",
                    )
                )

    return findings
