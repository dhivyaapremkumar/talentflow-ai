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
Ground-truth comparison happens exclusively in the offline evaluation
layer (`validation/reconcile.py`'s evaluation step, validation_strategy.md
§17/§22 — Phase 6), which consumes this module's output but is never
imported by it.

**`rule_category` distinguishes three structurally different kinds of
`VAL-11` finding** (all share `rule_id="VAL-11"` — this is a sub-category
within one rule, not a new rule), via the `CATEGORY_*` constants below,
never via message-string matching:
- `CATEGORY_CONSISTENCY`: the *stored* fields disagree with a fresh
  recompute — always a genuine defect (the write path is broken), never
  an expected outcome.
- `CATEGORY_DETECTED`: the algorithm determines this attempt is a
  duplicate — not a defect; this is the actual detection output
  validation_strategy.md §11/§21 means by "zero at baseline; 15/3
  non-canonical attempts post-injection." Phase 6's evaluator must
  select only these findings (via `rule_category ==
  duplicate_submissions.CATEGORY_DETECTED`) before comparing against
  the ground-truth label table — never the consistency or invariant
  findings.
- `CATEGORY_INVARIANT`: more than one canonical attempt exists for the
  same `Application` — a structural defect, independent of the above.
"""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import ApplicationSubmissionAttempt
from app.validation.report import Finding

RULE_ID = "VAL-11"

CATEGORY_CONSISTENCY = "duplicate_submission_consistency"
CATEGORY_DETECTED = "duplicate_submission_detected"
CATEGORY_INVARIANT = "duplicate_submission_invariant"


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
                    RULE_ID, CATEGORY_CONSISTENCY, "application_submission_attempt", attempt_id,
                    f"is_canonical={stored.is_canonical} but recomputed detection expects "
                    f"{exp['is_canonical']}",
                    "violation",
                )
            )
        if stored.duplicate_of_attempt_id != exp["duplicate_of_attempt_id"]:
            findings.append(
                Finding(
                    RULE_ID, CATEGORY_CONSISTENCY, "application_submission_attempt", attempt_id,
                    f"duplicate_of_attempt_id={stored.duplicate_of_attempt_id!r} but recomputed "
                    f"detection expects {exp['duplicate_of_attempt_id']!r}",
                    "violation",
                )
            )
        if stored.issue_type != exp["issue_type"]:
            findings.append(
                Finding(
                    RULE_ID, CATEGORY_CONSISTENCY, "application_submission_attempt", attempt_id,
                    f"issue_type={stored.issue_type!r} but recomputed detection expects "
                    f"{exp['issue_type']!r}",
                    "violation",
                )
            )

    # Detection output, distinct from the consistency checks above: one
    # finding per attempt the algorithm determines is a duplicate — this
    # is what validation_strategy.md Sec11/Sec21 means by "expected output:
    # zero at baseline; exactly 15 (full) / 3 (starter) non-canonical
    # attempts post-injection." A finding here does not mean something is
    # broken (unlike the consistency-mismatch findings above) — it means a
    # duplicate submission was correctly detected, which is the intended,
    # expected outcome once Phase 5 has injected any. rule_category=
    # CATEGORY_DETECTED is how Phase 6's evaluator selects exactly these
    # findings for comparison against the ground-truth label table —
    # never by matching on this message text.
    for attempt_id, exp in expected.items():
        if exp["issue_type"] == "DuplicateSubmission":
            findings.append(
                Finding(
                    RULE_ID, CATEGORY_DETECTED, "application_submission_attempt", attempt_id,
                    f"detected duplicate submission (duplicate_of_attempt_id="
                    f"{exp['duplicate_of_attempt_id']!r})",
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
                    RULE_ID, CATEGORY_INVARIANT, "application", app_id,
                    f"{count} canonical ApplicationSubmissionAttempt rows (expected exactly 1)",
                    "violation",
                )
            )

    return findings


def select_detected_duplicates(findings: list[Finding]) -> list[Finding]:
    """Returns only the `CATEGORY_DETECTED` findings from a VAL-11 finding
    list — the subset Phase 6's offline evaluator must compare against
    the ground-truth label table (matching key: `entity_id` ==
    `attempt_id`, validation_strategy.md §22). Never selects
    `CATEGORY_CONSISTENCY` or `CATEGORY_INVARIANT` findings, which
    represent defects, not detections.
    Exists so Phase 6 selects by structured field, never by matching on
    `message` text."""
    return [f for f in findings if f.rule_id == RULE_ID and f.rule_category == CATEGORY_DETECTED]
