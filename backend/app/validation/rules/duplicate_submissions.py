"""VAL-11 — Duplicate-submission detection, validation_strategy.md §11,
business_rules.md §10.

`recompute_canonical_assignment()` is the one, shared implementation of
the detection algorithm (architecture.md §6: "one implementation, two
call sites") — groups attempts by (candidate_id, requisition_id), sorts
by (submitted_at, attempt_id) ascending (the deterministic tie-break),
flags every non-first attempt as a duplicate. Phase 5's injector and
Phase 8's live write path must both call this same function rather than
redefining the grouping logic.

**This module must never reference ground truth.** Per
validation_strategy.md §17/§15's whole-package leakage guarantee, this
file contains no reference to the ground-truth label model or field by
name anywhere in its source — the detection function's input type below
carries only `attempt_id`, `candidate_id`, `requisition_id`,
`submitted_at`, `is_canonical`, `duplicate_of_attempt_id`, `issue_type`.
"""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import ApplicationSubmissionAttempt
from app.validation.report import Finding

RULE_ID = "VAL-11"
RULE_CATEGORY = "duplicate_submissions"


@dataclass(frozen=True)
class AttemptInput:
    attempt_id: str
    candidate_id: str
    requisition_id: str
    submitted_at: object
    is_canonical: bool
    duplicate_of_attempt_id: str | None
    issue_type: str


def recompute_canonical_assignment(attempts: list[AttemptInput]) -> dict[str, dict]:
    """Returns attempt_id -> {"is_canonical", "duplicate_of_attempt_id", "issue_type"}."""
    groups: dict[tuple, list[AttemptInput]] = {}
    for a in attempts:
        groups.setdefault((a.candidate_id, a.requisition_id), []).append(a)

    result: dict[str, dict] = {}
    for group in groups.values():
        ordered = sorted(group, key=lambda a: (a.submitted_at, a.attempt_id))
        canonical = ordered[0]
        result[canonical.attempt_id] = {
            "is_canonical": True,
            "duplicate_of_attempt_id": None,
            "issue_type": "None",
        }
        for dup in ordered[1:]:
            result[dup.attempt_id] = {
                "is_canonical": False,
                "duplicate_of_attempt_id": canonical.attempt_id,
                "issue_type": "DuplicateSubmission",
            }
    return result


def check(session: Session) -> list[Finding]:
    findings: list[Finding] = []

    rows = session.execute(select(ApplicationSubmissionAttempt)).scalars().all()
    attempts = [
        AttemptInput(
            attempt_id=r.attempt_id,
            candidate_id=r.candidate_id,
            requisition_id=r.requisition_id,
            submitted_at=r.submitted_at,
            is_canonical=r.is_canonical,
            duplicate_of_attempt_id=r.duplicate_of_attempt_id,
            issue_type=r.issue_type,
        )
        for r in rows
    ]
    expected = recompute_canonical_assignment(attempts)
    stored_by_id = {r.attempt_id: r for r in rows}

    for attempt_id, exp in expected.items():
        stored = stored_by_id[attempt_id]
        if stored.is_canonical != exp["is_canonical"]:
            findings.append(
                Finding(
                    RULE_ID, RULE_CATEGORY, "application_submission_attempt", attempt_id,
                    f"is_canonical={stored.is_canonical} but recomputed detection expects "
                    f"{exp['is_canonical']}",
                    "violation",
                )
            )
        if stored.duplicate_of_attempt_id != exp["duplicate_of_attempt_id"]:
            findings.append(
                Finding(
                    RULE_ID, RULE_CATEGORY, "application_submission_attempt", attempt_id,
                    f"duplicate_of_attempt_id={stored.duplicate_of_attempt_id!r} but recomputed "
                    f"detection expects {exp['duplicate_of_attempt_id']!r}",
                    "violation",
                )
            )
        if stored.issue_type != exp["issue_type"]:
            findings.append(
                Finding(
                    RULE_ID, RULE_CATEGORY, "application_submission_attempt", attempt_id,
                    f"issue_type={stored.issue_type!r} but recomputed detection expects "
                    f"{exp['issue_type']!r}",
                    "violation",
                )
            )

    # Independent re-derivation of the partial-unique-index invariant: at
    # most one is_canonical=true per canonical_application_id.
    canonical_count_by_app: dict[str, int] = {}
    for r in rows:
        if r.is_canonical:
            canonical_count_by_app[r.canonical_application_id] = (
                canonical_count_by_app.get(r.canonical_application_id, 0) + 1
            )
    for app_id, count in canonical_count_by_app.items():
        if count > 1:
            findings.append(
                Finding(
                    RULE_ID, RULE_CATEGORY, "application", app_id,
                    f"{count} canonical ApplicationSubmissionAttempt rows (expected exactly 1)",
                    "violation",
                )
            )

    return findings
