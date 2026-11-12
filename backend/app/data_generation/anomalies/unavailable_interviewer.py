"""Anomaly type 1 — Interview scheduled for an unavailable interviewer.
business_rules.md §9: "Pick a Scheduled/Completed Interview; rewrite its
scheduled_start/end to fall outside all of that interviewer's
InterviewerAvailabilitySlot windows, or to overlap another booked
Interview for the same interviewer." 15 incidents (full) / 3 (starter),
one `AnomalyLabel` row per incident, `entity_type=Interview`.

Mechanism chosen: shift the interview forward to the next Saturday after
its current date, same hour/duration. `InterviewerAvailabilitySlot` rows
are only ever generated for weekdays (`reference_data.py`), so a
Saturday slot is *structurally* guaranteed to fall outside every one of
that interviewer's availability windows — deterministic and exact,
never a near-miss.

**Restricted to `status="Scheduled"` only — a real bug, caught before
this was ever considered done, not a silent scope narrowing.** The spec
text allows picking a `Completed` interview too, but a `Completed`
interview already has a `Feedback` row (the baseline's own invariant),
and `Feedback.submitted_at >= Interview.scheduled_end` is a real
cross-table ordering rule (VAL-04). Shifting a Completed interview's
time forward without also touching its Feedback row — which the
documented "Affected table: Interview" (business_rules.md §9) says is
the *only* table this anomaly may touch — would retroactively violate
that ordering rule, a structural category VAL-04 that must stay zero
post-injection. Restricting to `Scheduled` interviews (which never have
Feedback yet) avoids the conflict entirely rather than reaching into a
second table to patch around it.
"""

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.data_generation.seeding import make_rng
from app.db.models import Interview

ANOMALY_TYPE = "UnavailableInterviewer"
ENTITY_TYPE = "Interview"


def _next_saturday(dt):
    days_ahead = (5 - dt.weekday()) % 7
    days_ahead = days_ahead if days_ahead > 0 else 7
    return dt + timedelta(days=days_ahead)


def inject(session: Session, seed: int, count: int) -> list[dict]:
    rng = make_rng(seed, "anomaly_unavailable_interviewer")

    eligible = (
        session.execute(select(Interview).where(Interview.status == "Scheduled"))
        .scalars()
        .all()
    )
    eligible.sort(key=lambda iv: iv.interview_id)
    if len(eligible) < count:
        raise ValueError(
            f"Only {len(eligible)} eligible Interview rows, need {count} for "
            "the unavailable-interviewer anomaly"
        )
    chosen = rng.sample(eligible, count)
    chosen.sort(key=lambda iv: iv.interview_id)

    label_rows: list[dict] = []
    for iv in chosen:
        duration = iv.scheduled_end - iv.scheduled_start
        new_start = _next_saturday(iv.scheduled_start)
        new_end = new_start + duration

        iv.scheduled_start = new_start
        iv.scheduled_end = new_end
        iv.updated_at = new_end

        label_rows.append(
            {
                "entity_type": ENTITY_TYPE,
                "entity_id": iv.interview_id,
                "anomaly_type": ANOMALY_TYPE,
                "related_entity_id": None,
                "description": (
                    f"Interview {iv.interview_id} rescheduled to {new_start.isoformat()}, "
                    f"outside interviewer {iv.interviewer_id}'s availability windows."
                ),
            }
        )

    session.flush()
    return label_rows
