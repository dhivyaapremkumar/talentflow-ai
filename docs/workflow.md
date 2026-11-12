# Workflow

**Revision 2** — adds the submission-attempt flow (§2a), threads `SystemActor` through
every approval step, and updates the exception-detection flow to reflect the
isolated-but-pointed ground-truth design (§6).

**Second verification pass** — §3 now reflects the `ScreeningRun` table instead of
a JSON append; §1 and §6 note that the `APPROVER` role is now hard-enforced for
requisition and offer approval, not just an expected convention.

**Implementation-detail clarification pass** — §3 notes `screening_rule_id` being
set to a permanent, reproducible reference at screening time.

**Withdrawal/resubmission policy pass** — new §2b shows the withdrawal-then-
resubmission flow, confirming `Application.stage` is never touched by attempt
reconciliation.

**Screening/decision logic verification pass** — §3 updated for the three-weight
formula (education now scored, not just gated).

**Final approval pass (this revision)** — §3 notes the formula and default
threshold are now APPROVED, not proposed.

End-to-end process flows this system models. Each flow references the lifecycle states
defined in `business_rules.md` §2–3.

## 1. Requisition creation and approval

```
BUSINESS_REQUESTER drafts req (Draft) — JobRequisition.requested_by_actor_id set
        │
        ▼
Submitted for approval (PendingApproval)  ──writes RequisitionStatusHistory (actor: BUSINESS_REQUESTER)──
        │
        ▼
APPROVER approves (Approved) — salary band + headcount locked in; role is
hard-enforced (business_rules.md §11) — the service layer rejects this step if the
actor's role isn't APPROVER
        ──writes RequisitionStatusHistory (actor: APPROVER)──
        │
        ▼
PROCESS_OWNER opens for applications (Open)  ──requires: 1 ScreeningRule + ≥1 JobRequisitionSkill──
        │
        ├──► OnHold ──► Open  (repeatable, actor: PROCESS_OWNER)
        │
        ▼
Closed (filled or cancelled-by-business)  ──writes RequisitionStatusHistory──
```
Validation gate before `Open`: `business_rules.md` §2. Expected actor role per step:
`business_rules.md` §11. Exception surfaced if a requisition is force-closed with
active applications still attached — anomaly type 5 when injected, or a genuine audit
finding when it occurs for real.

## 2. Candidate application submission

```
Candidate submits Application for (candidate_id, requisition_id)
        │
        ▼
canonical_application_id computed = APP-<requisition_id>-<candidate_id>
        │
        ├─ No Application exists yet for this canonical_application_id
        │        │
        │        ▼
        │  Application row created (stage=Applied), referencing the candidate's
        │  latest ResumeArtifact
        │        │
        │        ▼
        │  ApplicationSubmissionAttempt created: is_canonical=true, issue_type=None
        │
        └─ An Application already exists for this canonical_application_id
                 │
                 ▼
           ApplicationSubmissionAttempt created: is_canonical=false,
           duplicate_of_attempt_id → the earlier attempt,
           issue_type=DuplicateSubmission (computed by the detector, §2a)
           — the existing Application is NOT modified, and NO second
           Application row is created
```

## 2a. Why submission attempts are logged separately from Applications (new in Rev 2)

Every submission — first or repeat — is written to `ApplicationSubmissionAttempt`
first. The attempt layer is where "did this already happen" gets decided, *before*
anything touches the canonical `Application` record:

```
New submission arrives: (candidate_id, requisition_id, submitted_at)
        │
        ▼
Ensure Application exists (idempotent insert — safe under a race, PK is derived)
        │
        ▼
Insert this attempt (placeholder flags)
        │
        ▼
Re-run the deterministic (submitted_at, attempt_id) sort over EVERY attempt now on
file for this (candidate_id, requisition_id) pair (business_rules.md §10) — update
is_canonical/duplicate_of_attempt_id/issue_type for all of them to match, not just
the new row (revised, this pass — handles an attempt that arrives later in
processing order but has an earlier submitted_at than the current canonical)
```
This is exactly the flow that makes "duplicate candidate application" (anomaly type 2)
representable without ever creating a second `Application` PK or discarding the repeat
submission — see `business_rules.md` §10 for the detection algorithm (now shared
verbatim between this write path and the independent validation/detection path) and
`entity_relationships.md` §5 for why this removes the need for a soft uniqueness rule
on `Application` entirely. In the generated dataset, attempts are always created in
true chronological order, so the recompute is a no-op confirmation every time — the
mechanism exists for a live system where processing order and submission-time order
can diverge, same pattern as `ScreeningRule`'s unexercised-but-structurally-correct
versioning (`business_rules.md` §4).

## 2b. Withdrawal followed by resubmission (new, this pass — Option A, approved)

```
Application exists for (candidate_id, requisition_id), stage=Withdrawn
(reached via an earlier explicit withdraw action — business_rules.md §3; terminal,
no outgoing transitions)
        │
        ▼
Candidate submits again for the SAME (candidate_id, requisition_id)
        │
        ▼
canonical_application_id computed = APP-<requisition_id>-<candidate_id>
— identical to the existing Application's ID; no new Application is created
        │
        ▼
New ApplicationSubmissionAttempt inserted (§2a's flow, unmodified) →
reconcile_canonical() re-runs over every attempt for the pair
        │
        ├─ Typical case: new attempt's submitted_at is later than the original's
        │  (realistic — you withdraw before you resubmit) ──► new attempt sorts
        │  after the original ──► is_canonical=false, issue_type=DuplicateSubmission,
        │  duplicate_of_attempt_id → the original (still-canonical) attempt
        │
        └─ Out-of-order edge case: new attempt's submitted_at is somehow earlier
           than the original's ──► reconcile_canonical() re-derives canonical
           status purely from (submitted_at, attempt_id), same as it would for any
           pair (business_rules.md §10) — which attempt ends up is_canonical may
           change, but:
        │
        ▼
Application.stage is NOT touched by either branch — it stays Withdrawn. No code
path in this flow writes to Application.stage; reconcile_canonical() only ever
writes ApplicationSubmissionAttempt rows (business_rules.md §3a).
```
This is the same attempt-recording flow as §2/§2a, run against a pair whose
`Application` happens to already be in a terminal state — nothing about that
changes how the flow executes. See `business_rules.md` §3a for the full policy
statement and why no new lifecycle state or algorithm branch was required.

## 3. Screening

```
Application created (stage=Applied, latest_screening_run_id=NULL)
        │
        ▼
PROCESS_OWNER (or an automated job acting on their behalf) triggers screening
(stage=Screening): services/screening.py computes skill_component,
experience_component, education_component, education_gate_passed, screening_score
(APPROVED three-weight sum, default 50/30/20 — business_rules.md §5),
screening_decision (against the default pass_threshold_score=70.0 unless
configured otherwise), screening_explanation, against ScreeningRule.version —
deterministic, no human judgment call needed
        │
        ▼
A new, immutable ScreeningRun row is inserted (is_latest=true, screening_rule_id set
to the requisition's current ScreeningRule — a permanent reference, reproducible even
if that rule is later redefined, business_rules.md §4); any prior ScreeningRun for
this application is flipped to is_latest=false; Application's mirrored screening_*
columns and latest_screening_run_id are updated to match — all three steps one atomic
transaction (business_rules.md §5)
        │
        ├─ screening_decision=Fail ──► stage=Rejected (rejected_reason recorded)
        │
        ▼ screening_decision=Pass
stage=Interviewing (candidate becomes eligible for Interview scheduling)
```

## 4. Interview scheduling and execution

```
For each Interviewing-stage application:
  PROCESS_OWNER picks an Interviewer + a round_type
        │
        ▼
  Scheduling check: does the chosen scheduled_start/end fall inside one of the
  Interviewer's open InterviewerAvailabilitySlot windows, with no overlap against
  another booked Interview for that interviewer?
        │
        ├─ No ──► rejected at the service layer (real-time) / flagged by validation
        │          (synthetic anomaly type 1, business_rules.md §9)
        ▼ Yes
  Interview created (status=Scheduled)
        │
        ▼
  Interview occurs ──► status=Completed (or Cancelled / NoShow)
        │
        ▼ (status=Completed only)
  Interviewer submits Feedback (recommendation + score + notes)
```
An application can have multiple interview rounds, each its own `Interview` +
`Feedback` pair. "Advance to next round" vs. "advance to Offer" is a `PROCESS_OWNER`
decision informed by aggregated `Feedback.recommendation` across completed rounds —
this aggregation is a read-time analytics query (`analytics/funnel.py`), not a stored
field.

## 5. Stage advancement to Offer / Hired

```
All scheduled Interview rounds for the application are Completed, each with Feedback
        │
        ▼
PROCESS_OWNER decision: advance stage=Offer, OR stage=Rejected
──writes ApplicationStageHistory (actor: PROCESS_OWNER)──
```
Gate enforced by validation: stage cannot become `Offer` or `Hired` while any
`Completed` interview for the application lacks `Feedback` — violating this is exactly
anomaly type 3.

## 6. Offer creation, approval, and resolution

```
PROCESS_OWNER drafts Offer (status=Drafted) against the application's requisition's
salary band
        │
        ▼
PendingApproval ──► APPROVER approves (status=Approved; Offer.approved_by_actor_id set)
        │           (requires requisition.status=Open at approval time; role is
        │            hard-enforced, business_rules.md §11 — rejected if not APPROVER)
        │            ──writes OfferStatusHistory (actor: APPROVER)──
        ▼
PROCESS_OWNER extends offer to candidate (status=Extended)
        │
        ├─ Accepted ──► Application.stage becomes Hired
        ├─ Declined
        ├─ Rescinded  (APPROVER withdraws before candidate decides)
        └─ Expired    (SYSTEM_ADMINISTRATOR-attributed automatic expiry if candidate
                        never responds by expiry_date)
```
Salary-band compliance (business_rules.md §7) is checked at approval time in the live
system; the synthetic dataset seeds a few offers that violate this as anomaly type 4,
specifically so the validation engine's band check has real positive examples to catch.

## 7. Exception detection and audit flow (brief §10)

```
OPERATIONS_ANALYST triggers (nightly/on-demand): validation/ engine runs all 13
mandated rule categories plus the role-appropriateness check (business_rules.md +
validation_strategy.md) against the live database —
this includes the duplicate-submission detector (business_rules.md §10), which never
reads ground_truth_label_id
        │
        ▼
Each violation is written to a validation report (not into AnomalyLabel — AnomalyLabel
is ground truth from generation time only, never written to by live validation)
        │
        ▼
Report is compared against AnomalyLabel ONLY in a separate offline evaluation step
(precision/recall of "does validation catch what generation seeded") — this comparison
never feeds back into the validation engine's logic. For ApplicationSubmissionAttempt
specifically, this comparison is: does computed issue_type agree with whether
ground_truth_label_id is set? (business_rules.md §10). This live-trigger flow runs
the same rule modules as steps 4–5 of the confirmed generation-time pipeline
(`business_rules.md` §13) — one implementation, two contexts, never two copies.
        │
        ▼
OPERATIONS_ANALYST reviews the frontend "Anomalies" page: the validation report
(current findings) and, separately, a "Ground Truth" dev-only view (for demoing
detection accuracy)
```
`OPERATIONS_ANALYST` is the one `SystemActor` role with no FK on any mutated data row
— it is purely the persona who runs this flow and reviews its output, matching brief
capability 10 ("exception detection and audit history") without forcing an audit-review
action to itself be logged as a lifecycle transition.

## 8. Analytics flow (read-only, no business-rule side effects)

```
Pandas jobs in analytics/ query the SQLite DB directly (read-only session) and compute:
  - Requisition funnel (Applied→Screening→Interviewing→Offer→Hired per requisition/dept)
  - Time-in-stage (days between ApplicationStageHistory rows)
  - Interviewer load (interviews per interviewer per week vs. availability)
  - Offer acceptance rate by department/level
  - Duplicate-submission rate (ApplicationSubmissionAttempt rows per canonical
    Application, by department/requisition)
  - Anomaly summary (counts by type, from the validation report, not AnomalyLabel)
        │
        ▼
Exposed via api/v1/analytics.py ──► React pages render with Recharts
```
