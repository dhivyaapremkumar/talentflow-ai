"""The live application-submission service — Phase 7,
implementation_plan.md's Phase 7 row: "gains the transactional wrapper
around Phase 4's pure `reconcile_canonical`... ensure Application exists
idempotently, insert the new attempt, rerun reconciliation over every
attempt for the pair — business_rules.md §10, including the
out-of-order-arrival case."

Reuses `validation.rules.duplicate_submissions.recompute_canonical_
assignment` verbatim — the same pure function the Phase 4 validator and
the Phase 5 injector already use (architecture.md §6: "one
implementation, never duplicated or allowed to drift"). This module
never redefines the grouping/sort/tie-break algorithm.

**Option A (approved), enforced by construction, not by a special-case
branch:** if an `Application` already exists for `(candidate_id,
requisition_id)` — in *any* stage, including `Withdrawn` — this service
never modifies it. `Application.stage` has no write path anywhere in
this module. A resubmission after withdrawal is handled by the exact
same code path as any other repeat submission (business_rules.md §3a,
workflow.md §2b) — there is no withdrawal-specific branch to get wrong.

**Scope boundary, flagged (not silent):** this module does not perform
any `SystemActor` role check. `ApplicationSubmissionAttempt` and
`Application` have no `actor_id` column in the schema at all
(data_dictionary.md §8/§8a) — submission is a candidate-triggered
action, not an actor-attributed one, so there is nothing for an
authorization gate to check here. Role-gated lifecycle transitions
(requisition/offer approval) are a different, separate concern —
`services/requisition_lifecycle.py` / `services/offer_lifecycle.py`,
explicitly Phase 8 work.
"""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Application, ApplicationSubmissionAttempt, Candidate, ResumeArtifact
from app.validation.rules.duplicate_submissions import AttemptInput, recompute_canonical_assignment


class ApplicationSubmissionError(Exception):
    """Raised when a submission cannot proceed — the service rolls back
    the session before raising, so the caller is never left mid-transaction."""


def _next_attempt_id(session: Session) -> str:
    existing = session.execute(select(ApplicationSubmissionAttempt.attempt_id)).scalars().all()
    nums = [int(v.split("-")[1]) for v in existing]
    next_num = (max(nums) + 1) if nums else 1
    return f"ATT-{next_num:07d}"


def submit_application(
    session: Session,
    candidate_id: str,
    requisition_id: str,
    submitted_at: datetime,
    resume_artifact_id: str | None = None,
) -> ApplicationSubmissionAttempt:
    """Records one submission event for `(candidate_id, requisition_id)`,
    as one atomic transaction:

    1. Idempotently ensure the canonical `Application` exists — created
       only if this is genuinely the first submission ever for this
       pair; never modified if it already exists, regardless of stage.
    2. Insert the new `ApplicationSubmissionAttempt` row.
    3. Re-run `recompute_canonical_assignment()` over *every* attempt now
       on file for the pair and write the (possibly changed, for every
       row, not just the new one) `is_canonical`/`duplicate_of_attempt_id`
       /`issue_type` back — the same out-of-order-safe behavior the
       validator and injector already rely on.

    Raises `ApplicationSubmissionError` (after rolling back) if the
    candidate/requisition/resume artifact cannot be resolved for a
    first-time submission — never partially commits.
    """
    try:
        application_id = f"APP-{requisition_id}-{candidate_id}"
        application = session.get(Application, application_id)

        if application is None:
            candidate = session.get(Candidate, candidate_id)
            if candidate is None:
                raise ApplicationSubmissionError(f"Candidate {candidate_id!r} does not exist")

            resolved_resume_id = resume_artifact_id
            if resolved_resume_id is None:
                latest_resume = session.execute(
                    select(ResumeArtifact).where(
                        ResumeArtifact.candidate_id == candidate_id, ResumeArtifact.is_latest.is_(True)
                    )
                ).scalars().first()
                if latest_resume is None:
                    raise ApplicationSubmissionError(
                        f"Candidate {candidate_id!r} has no resume artifact to reference"
                    )
                resolved_resume_id = latest_resume.resume_artifact_id

            application = Application(
                application_id=application_id,
                candidate_id=candidate_id,
                requisition_id=requisition_id,
                resume_artifact_id=resolved_resume_id,
                applied_at=submitted_at,
                source_channel=candidate.source_channel,
                stage="Applied",
                created_at=submitted_at,
                updated_at=submitted_at,
            )
            session.add(application)
            session.flush()

        # Placeholder flags for the INSERT must themselves satisfy
        # ck_attempt_canonical_duplicate_consistency immediately - SQLite
        # checks it per-statement, not deferred to commit (a real bug,
        # caught before this was considered done: (is_canonical=False,
        # duplicate_of_attempt_id=None) violates that CHECK on its own,
        # regardless of what the recompute below would later derive). A
        # brand-new pair's first attempt is unambiguously canonical with
        # no pointer; a repeat submission's new attempt is given the
        # existing canonical attempt as a (possibly provisional, always
        # FK-valid) pointer - either placeholder already satisfies the
        # CHECK, and the recompute below corrects it if the real answer
        # differs (e.g. an out-of-order arrival).
        existing_canonical = None
        if application is not None:
            existing_canonical = session.execute(
                select(ApplicationSubmissionAttempt).where(
                    ApplicationSubmissionAttempt.canonical_application_id == application_id,
                    ApplicationSubmissionAttempt.is_canonical.is_(True),
                )
            ).scalars().first()

        if existing_canonical is None:
            new_attempt = ApplicationSubmissionAttempt(
                attempt_id=_next_attempt_id(session),
                canonical_application_id=application_id,
                candidate_id=candidate_id,
                requisition_id=requisition_id,
                submitted_at=submitted_at,
                is_canonical=True,
                duplicate_of_attempt_id=None,
                issue_type="None",
            )
        else:
            new_attempt = ApplicationSubmissionAttempt(
                attempt_id=_next_attempt_id(session),
                canonical_application_id=application_id,
                candidate_id=candidate_id,
                requisition_id=requisition_id,
                submitted_at=submitted_at,
                is_canonical=False,
                duplicate_of_attempt_id=existing_canonical.attempt_id,
                issue_type="DuplicateSubmission",
            )
        session.add(new_attempt)
        session.flush()

        group_attempts = session.execute(
            select(ApplicationSubmissionAttempt).where(
                ApplicationSubmissionAttempt.candidate_id == candidate_id,
                ApplicationSubmissionAttempt.requisition_id == requisition_id,
            )
        ).scalars().all()
        inputs = [
            AttemptInput(
                attempt_id=a.attempt_id,
                candidate_id=a.candidate_id,
                requisition_id=a.requisition_id,
                submitted_at=a.submitted_at,
                is_canonical=a.is_canonical,
                duplicate_of_attempt_id=a.duplicate_of_attempt_id,
                issue_type=a.issue_type,
            )
            for a in group_attempts
        ]
        recomputed = recompute_canonical_assignment(inputs)
        by_id = {a.attempt_id: a for a in group_attempts}

        # Apply in two passes - every row being set to False first, then
        # every row being set to True - so the uq_attempt_canonical
        # partial unique index (at most one is_canonical=true per
        # canonical_application_id) is never violated mid-sequence, even
        # when a reassignment swaps which row is canonical. At most one
        # row is ever "True" at any instant this way, by construction.
        for attempt_id, fields in recomputed.items():
            if not fields["is_canonical"]:
                row = by_id[attempt_id]
                row.is_canonical = False
                row.duplicate_of_attempt_id = fields["duplicate_of_attempt_id"]
                row.issue_type = fields["issue_type"]
        session.flush()
        for attempt_id, fields in recomputed.items():
            if fields["is_canonical"]:
                row = by_id[attempt_id]
                row.is_canonical = True
                row.duplicate_of_attempt_id = fields["duplicate_of_attempt_id"]
                row.issue_type = fields["issue_type"]
        session.flush()

        session.commit()
        session.refresh(new_attempt)
        return new_attempt
    except Exception:
        session.rollback()
        raise
