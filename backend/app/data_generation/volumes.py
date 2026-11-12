"""Volume targets per mode (business_rules.md §1, PROJECT_SPEC.md A-6/A-13)
and the funnel-bucket derivation that splits `Application` counts into
internally consistent stage buckets hitting the mandated headline numbers
exactly (Application, Interview, Offer) while the sub-bucket breakdown
(how many are Hired vs Rejected-after-interview vs still mid-pipeline,
etc.) is derived proportionally — business_rules.md §1 marks those with
"~", this generator does not need to hit them bit-for-bit, only the
unprefixed headline numbers.

**Baseline vs. final volumes (PROJECT_SPEC.md A-5):** the funnel table's
`ApplicationSubmissionAttempt` count (3,015 full / 153 starter) is the
*final*, post-injection total — 3,000/150 canonical attempts plus 15/3
seeded duplicates added only in Phase 5. Phase 3 generates only the
canonical attempts (one per `Application`, 1:1), so `BASELINE_VOLUMES`
below deliberately does not add the +15/+3 here.
"""

from dataclasses import dataclass

FIXED_CATALOG_VOLUMES = {
    "department": 10,
    "skill": 40,
    "interviewer": 25,
    "system_actor": 20,
}

# Anomaly incident counts per mode — business_rules.md Sec9's table,
# PROJECT_SPEC.md Sec6. "Affected rows" equals "incidents" for every type
# except closed_requisition (2 affected Application rows per incident,
# A-12), handled separately by that injector, not reflected in these
# incident counts.
ANOMALY_COUNTS = {
    "full": {
        "unavailable_interviewer": 15,
        "duplicate_application": 15,
        "missing_feedback": 10,
        "salary_band": 6,
        "closed_requisition": 5,
    },
    "starter": {
        "unavailable_interviewer": 3,
        "duplicate_application": 3,
        "missing_feedback": 2,
        "salary_band": 1,
        "closed_requisition": 1,
    },
}

MODE_VOLUMES = {
    "full": {
        "job_requisition": 100,
        "candidate": 2000,
        "application": 3000,
        "interview": 600,
        "offer": 150,
        "hired": 120,
        "interviewing_or_beyond": 430,
    },
    "starter": {
        "job_requisition": 10,
        "candidate": 100,
        "application": 150,
        "interview": 30,
        "offer": 8,
        "hired": 6,
        "interviewing_or_beyond": 22,
    },
}


@dataclass(frozen=True)
class FunnelBuckets:
    hired: int
    offer_declined: int
    offer_pending: int
    still_interviewing: int
    rejected_after_interview: int
    rejected_at_screening: int
    still_at_screening: int
    withdrawn: int
    still_applied: int
    two_round_count: int
    one_round_count: int

    @property
    def offer_or_beyond(self) -> int:
        return self.hired + self.offer_declined + self.offer_pending

    @property
    def interviewing_or_beyond_actual(self) -> int:
        return self.offer_or_beyond + self.still_interviewing + self.rejected_after_interview

    @property
    def total_applications(self) -> int:
        return (
            self.interviewing_or_beyond_actual
            + self.rejected_at_screening
            + self.still_at_screening
            + self.withdrawn
            + self.still_applied
        )


def derive_funnel_buckets(
    *, n_applications: int, n_interviews: int, n_offers: int, n_hired: int, n_interviewing_or_beyond: int
) -> FunnelBuckets:
    hired = n_hired
    remaining_offer = max(0, n_offers - hired)
    offer_declined = round(remaining_offer * 0.6)
    offer_pending = remaining_offer - offer_declined

    interviewing_not_offered = max(0, n_interviewing_or_beyond - n_offers)
    still_interviewing = round(interviewing_not_offered * 0.22)
    rejected_after_interview = interviewing_not_offered - still_interviewing

    total_interview_apps = n_offers + interviewing_not_offered

    # Solve x (1-round apps) + y (2-round apps) = total_interview_apps,
    # x + 2y = n_interviews  =>  y = n_interviews - total_interview_apps.
    two_round_count = max(0, min(total_interview_apps, n_interviews - total_interview_apps))
    one_round_count = total_interview_apps - two_round_count

    remaining_apps = max(0, n_applications - total_interview_apps)
    rejected_at_screening = round(remaining_apps * 0.78)
    still_at_screening = round(remaining_apps * 0.16)
    withdrawn = round(remaining_apps * 0.04)
    still_applied = remaining_apps - rejected_at_screening - still_at_screening - withdrawn

    return FunnelBuckets(
        hired=hired,
        offer_declined=offer_declined,
        offer_pending=offer_pending,
        still_interviewing=still_interviewing,
        rejected_after_interview=rejected_after_interview,
        rejected_at_screening=rejected_at_screening,
        still_at_screening=still_at_screening,
        withdrawn=withdrawn,
        still_applied=still_applied,
        two_round_count=two_round_count,
        one_round_count=one_round_count,
    )


def volumes_for_mode(mode: str) -> dict:
    if mode not in MODE_VOLUMES:
        raise ValueError(f"Unknown mode: {mode!r} (expected 'starter' or 'full')")
    volumes = {**FIXED_CATALOG_VOLUMES, **MODE_VOLUMES[mode]}
    volumes["funnel"] = derive_funnel_buckets(
        n_applications=volumes["application"],
        n_interviews=volumes["interview"],
        n_offers=volumes["offer"],
        n_hired=volumes["hired"],
        n_interviewing_or_beyond=volumes["interviewing_or_beyond"],
    )
    volumes["anomaly_counts"] = ANOMALY_COUNTS[mode]
    return volumes
