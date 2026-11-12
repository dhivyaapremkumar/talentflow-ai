"""Application, ApplicationSubmissionAttempt, ScreeningRun — generated
together per architecture.md §4 (ScreeningRun needs application_id to
already exist; Application is updated afterward to mirror it).

Every Application gets exactly one ScreeningRun (data_dictionary.md §8b:
"screening runs exactly once per Application... a 1:1 shadow of the
Application count") — `stage` reflects the recruiter-workflow position
(which can still be `Applied` even once an automated score exists; the
score is immediate, the human stage-advancement action is not), while the
screening outcome is always genuinely computed via
`app.screening_formula`, never hand-picked, by deliberately selecting
which candidate is paired with which requisition per the target funnel
bucket (constructing a labeled dataset with controlled funnel statistics
this way is standard practice — the scoring math itself is always real).

Baseline only: every `ApplicationSubmissionAttempt` here is canonical
(`is_canonical=True`, `issue_type="None"`) — the 15/3 seeded duplicate
attempts are a Phase 5 concern (PROJECT_SPEC.md A-5).
"""

from datetime import timedelta

from app.data_generation.seeding import make_rng
from app.screening_formula import EDUCATION_RANKS, compute_screening_result

BUCKET_STAGE = {
    "hired": "Hired",
    "offer_declined": "Rejected",
    "offer_pending": "Offer",
    "still_interviewing": "Interviewing",
    "rejected_after_interview": "Rejected",
    "rejected_at_screening": "Rejected",
    "still_at_screening": "Screening",
    "withdrawn": "Withdrawn",
    "still_applied": "Applied",
}

REJECTED_REASON_BY_BUCKET = {
    "offer_declined": "Candidate declined the extended offer.",
    "rejected_after_interview": "Not selected after interview rounds.",
    "rejected_at_screening": "Did not meet minimum screening requirements.",
}

# Buckets requiring an Open/OnHold requisition (an in-progress application
# cannot sit against a Closed/Cancelled requisition in a clean baseline —
# that mismatch is exactly the ClosedReqActiveApplications anomaly, Phase 5
# only).
ACTIVE_ONLY_BUCKETS = {"still_interviewing", "still_at_screening", "still_applied", "offer_pending"}
# Buckets allowed on a Closed requisition too (Open/OnHold/Closed).
ACTIVE_OR_CLOSED_BUCKETS = {"hired", "offer_declined", "rejected_after_interview"}
# Buckets allowed on any requisition status, including Cancelled.
ANY_STATUS_BUCKETS = {"rejected_at_screening", "withdrawn"}

MAX_PASS_ATTEMPTS = 30


def _education_rank(level: str) -> int:
    return EDUCATION_RANKS[level]


def _build_candidate_skill_index(candidate_skills: list[dict]) -> dict:
    index: dict[str, dict] = {}
    for row in candidate_skills:
        index.setdefault(row["candidate_id"], {})[row["skill_id"]] = {
            "proficiency_level": row["proficiency_level"]
        }
    return index


def generate_applications(
    seed: int,
    requisitions: list[dict],
    requisition_skills: list[dict],
    screening_rules: list[dict],
    candidates: list[dict],
    candidate_skills: list[dict],
    resume_artifacts: list[dict],
    funnel,
):
    rng = make_rng(seed, "application")

    req_by_id = {r["requisition_id"]: r for r in requisitions}
    rule_by_req = {r["requisition_id"]: r for r in screening_rules}
    required_skills_by_req: dict[str, list] = {}
    for row in requisition_skills:
        required_skills_by_req.setdefault(row["requisition_id"], []).append(
            {
                "skill_id": row["skill_id"],
                "weight_pct": row["weight_pct"],
                "min_proficiency_level": row["min_proficiency_level"],
            }
        )

    candidate_by_id = {c["candidate_id"]: c for c in candidates}
    resume_by_candidate = {r["candidate_id"]: r["resume_artifact_id"] for r in resume_artifacts}
    skill_index = _build_candidate_skill_index(candidate_skills)
    all_candidate_ids = [c["candidate_id"] for c in candidates]

    pools = {"Open": [], "OnHold": [], "Closed": [], "Cancelled": []}
    for r in requisitions:
        pools[r["status"]].append(r["requisition_id"])
    active_pool = pools["Open"] + pools["OnHold"]
    active_or_closed_pool = active_pool + pools["Closed"]
    any_status_pool = active_or_closed_pool + pools["Cancelled"]

    # Eligible/ineligible candidate pools keyed by (min_years, min_education_rank) —
    # cheap to precompute since only 5 distinct level profiles exist.
    eligible_cache: dict[tuple, list[str]] = {}
    ineligible_cache: dict[tuple, list[str]] = {}

    def eligible_candidates(min_years: float, min_education: str) -> list[str]:
        key = (min_years, min_education)
        if key not in eligible_cache:
            min_rank = _education_rank(min_education)
            eligible_cache[key] = [
                c["candidate_id"]
                for c in candidates
                if c["years_experience"] >= min_years and _education_rank(c["highest_education_level"]) >= min_rank
            ]
        return eligible_cache[key]

    def ineligible_by_education(min_education: str) -> list[str]:
        key = min_education
        if key not in ineligible_cache:
            min_rank = _education_rank(min_education)
            ineligible_cache[key] = [
                c["candidate_id"]
                for c in candidates
                if _education_rank(c["highest_education_level"]) < min_rank
            ]
        return ineligible_cache[key]

    used_pairs: set[tuple[str, str]] = set()
    applications: list[dict] = []
    attempts: list[dict] = []
    screening_runs: list[dict] = []
    applications_by_bucket: dict[str, list[dict]] = {b: [] for b in BUCKET_STAGE}

    attempt_counter = 0
    run_counter = 0

    bucket_targets = {
        "hired": funnel.hired,
        "offer_declined": funnel.offer_declined,
        "offer_pending": funnel.offer_pending,
        "still_interviewing": funnel.still_interviewing,
        "rejected_after_interview": funnel.rejected_after_interview,
        "rejected_at_screening": funnel.rejected_at_screening,
        "still_at_screening": funnel.still_at_screening,
        "withdrawn": funnel.withdrawn,
        "still_applied": funnel.still_applied,
    }

    for bucket, target_count in bucket_targets.items():
        needs_pass = bucket in (
            "hired",
            "offer_declined",
            "offer_pending",
            "still_interviewing",
            "rejected_after_interview",
        )
        needs_fail_via_gate = bucket == "rejected_at_screening"

        if bucket in ACTIVE_ONLY_BUCKETS:
            req_pool = active_pool
        elif bucket in ACTIVE_OR_CLOSED_BUCKETS:
            req_pool = active_or_closed_pool
        elif bucket in ANY_STATUS_BUCKETS:
            req_pool = any_status_pool
        else:
            req_pool = active_pool

        for _ in range(target_count):
            requisition_id = None
            candidate_id = None
            screening = None

            for _try in range(50):
                candidate_requisition_id = rng.choice(req_pool)
                rule = rule_by_req[candidate_requisition_id]
                min_years = rule["min_years_experience"]
                min_education = rule["min_education_level"]

                if needs_fail_via_gate:
                    pool = ineligible_by_education(min_education) or all_candidate_ids
                    cand_id = rng.choice(pool)
                elif needs_pass:
                    pool = eligible_candidates(min_years, min_education) or all_candidate_ids
                    cand_id = rng.choice(pool)
                else:
                    cand_id = rng.choice(all_candidate_ids)

                pair = (candidate_requisition_id, cand_id)
                if pair in used_pairs:
                    continue

                required_skills = required_skills_by_req.get(candidate_requisition_id, [])
                candidate = candidate_by_id[cand_id]
                result = compute_screening_result(
                    required_skills=required_skills,
                    candidate_skills_by_skill_id=skill_index.get(cand_id, {}),
                    candidate_years_experience=candidate["years_experience"],
                    candidate_education_level=candidate["highest_education_level"],
                    min_years_experience=min_years,
                    min_education_level=min_education,
                    skill_weight_pct=rule["skill_weight_pct"],
                    experience_weight_pct=rule["experience_weight_pct"],
                    education_weight_pct=rule["education_weight_pct"],
                    pass_threshold_score=rule["pass_threshold_score"],
                    rule_version=rule["version"],
                )

                if needs_pass and result.screening_decision != "Pass":
                    if _try < MAX_PASS_ATTEMPTS:
                        continue
                if needs_fail_via_gate and result.screening_decision != "Fail":
                    if _try < MAX_PASS_ATTEMPTS:
                        continue

                requisition_id, candidate_id, screening = candidate_requisition_id, cand_id, result
                break

            if requisition_id is None:
                # Safety valve: extremely unlikely given the candidate pool
                # sizes, but never loop forever.
                continue

            used_pairs.add((requisition_id, candidate_id))
            req = req_by_id[requisition_id]
            candidate = candidate_by_id[candidate_id]
            rule = rule_by_req[requisition_id]

            opened_at_dt = req.get("opened_at")
            earliest = candidate["created_at"]
            if opened_at_dt is not None:
                from datetime import datetime as _dt

                opened_dt = _dt.combine(opened_at_dt, _dt.min.time()) + timedelta(hours=9)
                if opened_dt > earliest:
                    earliest = opened_dt
            applied_at = earliest + timedelta(days=rng.randint(1, 30), hours=rng.randint(0, 10))

            attempt_counter += 1
            run_counter += 1
            application_id = f"APP-{requisition_id}-{candidate_id}"
            screening_computed_at = applied_at + timedelta(hours=rng.randint(2, 48))

            attempts.append(
                {
                    "attempt_id": f"ATT-{attempt_counter:07d}",
                    "canonical_application_id": application_id,
                    "candidate_id": candidate_id,
                    "requisition_id": requisition_id,
                    "submitted_at": applied_at,
                    "is_canonical": True,
                    "duplicate_of_attempt_id": None,
                    "issue_type": "None",
                    "ground_truth_label_id": None,
                }
            )

            screening_run_id = f"SCRUN-{run_counter:07d}"
            screening_runs.append(
                {
                    "screening_run_id": screening_run_id,
                    "application_id": application_id,
                    "screening_rule_id": rule["screening_rule_id"],
                    "is_latest": True,
                    "screening_rule_version": rule["version"],
                    "screening_skill_component": screening.skill_component,
                    "screening_experience_component": screening.experience_component,
                    "screening_education_component": screening.education_component,
                    "screening_education_gate_passed": screening.education_gate_passed,
                    "screening_score": screening.screening_score,
                    "screening_decision": screening.screening_decision,
                    "screening_explanation": screening.screening_explanation,
                    "computed_at": screening_computed_at,
                }
            )

            stage = BUCKET_STAGE[bucket]
            withdrawn_at = None
            updated_at = screening_computed_at
            if bucket == "withdrawn":
                withdrawn_at = screening_computed_at + timedelta(days=rng.randint(1, 10))
                updated_at = withdrawn_at

            app_row = {
                "application_id": application_id,
                "candidate_id": candidate_id,
                "requisition_id": requisition_id,
                "resume_artifact_id": resume_by_candidate[candidate_id],
                "applied_at": applied_at,
                "source_channel": candidate["source_channel"],
                "stage": stage,
                "screening_score": screening.screening_score,
                "screening_skill_component": screening.skill_component,
                "screening_experience_component": screening.experience_component,
                "screening_education_component": screening.education_component,
                "screening_education_gate_passed": screening.education_gate_passed,
                "screening_decision": screening.screening_decision,
                "screening_rule_version": rule["version"],
                "screening_computed_at": screening_computed_at,
                "screening_explanation": screening.screening_explanation,
                "latest_screening_run_id": screening_run_id,
                "rejected_reason": REJECTED_REASON_BY_BUCKET.get(bucket),
                "withdrawn_at": withdrawn_at,
                "created_at": applied_at,
                "updated_at": updated_at,
                "_bucket": bucket,
            }
            applications.append(app_row)
            applications_by_bucket[bucket].append(app_row)

    return applications, attempts, screening_runs, applications_by_bucket
