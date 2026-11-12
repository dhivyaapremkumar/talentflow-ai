"""Interview, Feedback.

Round-count distribution (how many applications get 1 vs 2 interview
rounds) comes from `volumes.FunnelBuckets.{one,two}_round_count`, computed
to hit the mandated total Interview row count exactly. Scheduling checks
real (interviewer_id, date, hour) availability against the generated
`InterviewerAvailabilitySlot` rows and a per-interviewer booked-hours
tracker, so the baseline never double-books an interviewer — that
conflict is exactly the UnavailableInterviewer anomaly, Phase 5 only.
"""

from datetime import datetime, timedelta

from app.data_generation.seeding import make_rng

ROUND_TYPES_BY_NUMBER = {1: "Phone", 2: "Technical"}
POSITIVE_RECOMMENDATIONS = ("StrongYes", "Yes")
NEGATIVE_RECOMMENDATIONS = ("No", "StrongNo")
HOUR_CANDIDATES = (9, 10, 11, 13, 14, 15, 16)

BUCKETS_GETTING_INTERVIEWS = (
    "hired",
    "offer_declined",
    "offer_pending",
    "still_interviewing",
    "rejected_after_interview",
)
POSITIVE_FEEDBACK_BUCKETS = {"hired", "offer_declined", "offer_pending", "still_interviewing"}


def _assign_round_counts(applications_by_bucket: dict, funnel) -> dict[str, int]:
    """Returns application_id -> round count (1 or 2), preferring to give 2
    rounds to offer-tier apps first, per volumes.py's derivation."""
    priority_order = ["hired", "offer_declined", "offer_pending", "still_interviewing", "rejected_after_interview"]
    remaining_two = funnel.two_round_count
    rounds_by_app: dict[str, int] = {}
    for bucket in priority_order:
        for app in applications_by_bucket[bucket]:
            if remaining_two > 0:
                rounds_by_app[app["application_id"]] = 2
                remaining_two -= 1
            else:
                rounds_by_app[app["application_id"]] = 1
    return rounds_by_app


def _find_slot(
    rng, interviewer_ids: list[str], booked_hours: dict, earliest: datetime, duration_minutes: int = 60
):
    for _attempt in range(40):
        interviewer_id = rng.choice(interviewer_ids)
        day_offset = rng.randint(2, 12)
        candidate_date = (earliest + timedelta(days=day_offset)).date()
        while candidate_date.weekday() >= 5:
            candidate_date += timedelta(days=1)
        key = (interviewer_id, candidate_date)
        used_hours = booked_hours.setdefault(key, set())
        free_hours = [h for h in HOUR_CANDIDATES if h not in used_hours]
        if not free_hours:
            continue
        hour = rng.choice(free_hours)
        used_hours.add(hour)
        start = datetime.combine(candidate_date, datetime.min.time()).replace(hour=hour)
        end = start + timedelta(minutes=duration_minutes)
        return interviewer_id, start, end
    raise RuntimeError("Could not find an available interview slot after 40 attempts")


def generate_interviews_and_feedback(
    seed: int, applications_by_bucket: dict, funnel, interviewer_ids: list[str], availability_slots: list[dict]
):
    rng = make_rng(seed, "interview")
    rounds_by_app = _assign_round_counts(applications_by_bucket, funnel)
    booked_hours: dict[tuple, set] = {}

    interviews: list[dict] = []
    feedback_rows: list[dict] = []
    interview_counter = 0
    feedback_counter = 0

    for bucket in BUCKETS_GETTING_INTERVIEWS:
        is_positive_bucket = bucket in POSITIVE_FEEDBACK_BUCKETS
        for app in applications_by_bucket[bucket]:
            n_rounds = rounds_by_app[app["application_id"]]
            earliest = app["screening_computed_at"]
            last_end = None
            for round_number in range(1, n_rounds + 1):
                interviewer_id, start, end = _find_slot(rng, interviewer_ids, booked_hours, earliest)
                earliest = start
                last_end = end
                if round_number == 1:
                    app["_first_interview_start"] = start
                interview_counter += 1
                interview_id = f"IVW-{interview_counter:06d}"

                is_last_round = round_number == n_rounds
                if bucket == "still_interviewing" and is_last_round:
                    status = "Scheduled"
                else:
                    status = "Completed"

                interviews.append(
                    {
                        "interview_id": interview_id,
                        "application_id": app["application_id"],
                        "interviewer_id": interviewer_id,
                        "round_number": round_number,
                        "round_type": ROUND_TYPES_BY_NUMBER.get(round_number, "Panel"),
                        "scheduled_start": start,
                        "scheduled_end": end,
                        "status": status,
                        "location_mode": rng.choice(["Remote", "Onsite"]),
                        "created_at": app["screening_computed_at"],
                        "updated_at": end,
                    }
                )
                app["updated_at"] = max(app["updated_at"], end)

                if status == "Completed":
                    feedback_counter += 1
                    recommendation = rng.choice(
                        POSITIVE_RECOMMENDATIONS if is_positive_bucket else NEGATIVE_RECOMMENDATIONS
                    )
                    overall_score = (
                        rng.choice([4, 5]) if is_positive_bucket else rng.choice([1, 2])
                    )
                    submitted_at = end + timedelta(minutes=rng.randint(30, 180))
                    feedback_rows.append(
                        {
                            "feedback_id": f"FBK-{feedback_counter:06d}",
                            "interview_id": interview_id,
                            "interviewer_id": interviewer_id,
                            "recommendation": recommendation,
                            "overall_score": overall_score,
                            "strengths_text": "Strong technical fundamentals and clear communication."
                            if is_positive_bucket
                            else "Some relevant background.",
                            "concerns_text": None
                            if is_positive_bucket
                            else "Gaps relative to role requirements surfaced during the interview.",
                            "submitted_at": submitted_at,
                        }
                    )
                    app["updated_at"] = max(app["updated_at"], submitted_at)

            app["_last_interview_end"] = last_end

    # Mark the availability slot used by each booked (interviewer, date) as booked.
    booked_keys = set(booked_hours.keys())
    for slot in availability_slots:
        key = (slot["interviewer_id"], slot["start_datetime"].date())
        if key in booked_keys:
            slot["is_booked"] = True

    return interviews, feedback_rows
