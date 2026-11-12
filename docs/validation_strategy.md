# Validation Strategy

**Revision 2** — updates the screening-recompute check for the new explainability
fields (§5), rewrites duplicate-application detection against
`ApplicationSubmissionAttempt` instead of `Application` (§11), adds a role-
appropriateness check (§14, new), and corrects every expected-hit count to the
incidents-vs-affected-rows numbers in `business_rules.md` §9.

**Audit correction:** this document has always implemented all 13 mandated
categories below (count them: §1–§13) — the intro line previously said "12", an
off-by-one label error also repeated in `PROJECT_SPEC.md`, `architecture.md`,
`workflow.md`, and `implementation_plan.md`, now fixed everywhere. No category was
added, removed, or renumbered by this fix — §14 (role-appropriateness) was already
correctly numbered 14 in the body below; only this intro paragraph's count was wrong.

**Second verification pass:** §5 now checks the new `ScreeningRun` table instead of
a JSON array; §12 reconciliation extended for `ScreeningRun`; §14 severity split into
hard (two approval checks) vs. soft (everything else); new §17 generalizes the
ground-truth non-leakage test to all of `services/` and `validation/rules/`.

**Implementation-detail clarification pass:** §2 and §5 add the
`ScreeningRun.screening_rule_id` FK check and `ScreeningRule` immutability check; §11
pins the duplicate-detection tie-break to `(submitted_at, attempt_id)` and adds the
new partial-unique-index/check-constraint verification; §12 adds the
`uq_screeningrule_current` invariant.

**Withdrawal/resubmission policy pass:** new §18 adds four test cases plus one
structural guarantee test (`reconcile_canonical()` never touches
`Application.stage`), covering Option A (approved).

**Screening/decision logic verification pass:** §5 updated for the three-weight
model and the gate-override guarantee; §17 explicitly names `services/screening.py`
in the leakage-test scope; new §19 adds the full screening test matrix.

**Final approval pass:** §5/§19 marked APPROVED; §19's boundary test case corrected
to the fully concrete `70.00`/`69.25` pair (`business_rules.md` §5a).

**Anomaly generation and validation verification pass:** new §20 closes a real
gap — export consistency was never a named validation category before; new §21
compiles a formal `VAL-nn` rule-ID catalog across all 16 categories with explicit
baseline-vs-post-injection expected outputs; new §22 formally defines
TP/FP/FN/precision/recall/F1; new §23 explicitly assesses indirect ground-truth
leakage channels beyond the direct-reference scan.

**Prompt 5 correction pass:** §12's closed-req detector now explicitly emits one
violation per `(requisition_id, application_id)` pair, not one aggregated
violation per requisition, so its output is comparable to `AnomalyLabel`'s
per-application granularity. §22 rewritten: the "TP=15/FP=0/FN=0" result is now
explicitly labeled an **EXPECTED, design-derived projection**, not a reported test
outcome (no code exists yet to have produced one) — this corrects overclaiming in
the prior version. §22 also adds the affected-entity-level evaluation model, a
per-category matching-key table, and an explicit confirmation that the detector
cannot access `AnomalyLabel`, `ground_truth_label_id`, or this evaluation step's
own output.

**Prompt 5 final clarification pass (this revision):** §12 simplified to key
purely on `application_id` (no more "requisition_id, application_id pair" —
`data_dictionary.md` §16's entity-type flip makes `application_id` alone
sufficient); §13 corrected to scope checksums to the 21 operational content
tables, excluding `GenerationRun` itself, and to require matching
`generator_version` alongside seed/mode; §22's matching-key table loses its
type-5 exception entirely — `entity_id` is now uniform across all five
categories.

Implements the 13 mandated validation categories from the brief (§6), plus one
review-requested addition (§14). The engine lives in `backend/app/validation/`, is
read-only (never mutates data — `architecture.md` §2), and is invoked both as a Pytest
suite and as an on-demand API endpoint (`GET /api/v1/validation/report`).

Each rule below states: **what it checks**, **where it's implemented**, and **how it's
tested**.

## 1. Primary-key uniqueness
- **Check:** every table's PK column has no duplicate values, across all **22** tables
  (corrected count — see `entity_relationships.md` §1). `ScreeningRun` (new, this
  pass) is included.
- **Implementation:** `validation/rules/pk_uniqueness.py`.
- **Test:** `test_validation.py::test_pk_uniqueness_all_tables` — zero violations
  expected. Note: this check is now *structurally guaranteed* for `Application`
  specifically, since its PK is derived from `(requisition_id, candidate_id)` — a
  violation here for `Application` would mean the ID-derivation function itself is
  broken, not that an anomaly slipped through.

## 2. Foreign-key integrity
- **Check:** every FK column resolves to an existing row in its parent table,
  including the six new/changed FKs onto `SystemActor`
  (`JobRequisition.requested_by_actor_id`, `RequisitionStatusHistory.actor_id`,
  `ApplicationStageHistory.actor_id`, `Offer.approved_by_actor_id`,
  `OfferStatusHistory.actor_id`, `GenerationRun.generated_by_actor_id`),
  `ApplicationSubmissionAttempt.canonical_application_id`, and (new, this pass)
  `ScreeningRun.screening_rule_id → ScreeningRule.screening_rule_id`.
- **Implementation:** `validation/rules/fk_integrity.py`, driven off SQLAlchemy's own
  relationship metadata.
- **Test:** zero violations expected on generated data.

## 3. Allowed values and required fields
- **Check:** every enum column's value is in its declared set (including the new
  `SystemActor.role` 5-value enum and `ApplicationSubmissionAttempt.issue_type`
  2-value enum); every conditionally-required field is satisfied.
- **Implementation:** reuses the Pydantic schema's own validators in "report, don't
  raise" mode, so the rule definition lives in exactly one place.
- **Test:** `test_validation.py::test_required_and_allowed_values`.

## 4. Date ordering
- **Check:** every ordering rule in `data_dictionary.md` — unchanged categories, plus
  `ApplicationSubmissionAttempt.submitted_at` ordering within a group (the canonical
  attempt's `submitted_at` must be the minimum in its `(candidate_id, requisition_id)`
  group) and `Application.applied_at == ` the canonical attempt's `submitted_at`.
- **Implementation:** `validation/rules/date_ordering.py`, table-driven.
- **Test:** `test_validation.py::test_date_ordering`.

## 5. Screening score calculations (APPROVED — three-weight model, 50/30/20 default)
- **Check:** recompute `screening_score`, `screening_skill_component`,
  `screening_experience_component`, `screening_education_component` (new, this pass),
  `screening_education_gate_passed`, `screening_decision` from
  `services/screening.py`'s formula (`business_rules.md` §5) and compare to the
  `ScreeningRun` row referenced by `Application.latest_screening_run_id` (float
  tolerance 0.01 on the three component/score fields; exact match on the two
  boolean/enum decisions). Also assert:
  - `skill_weight_pct + experience_weight_pct + education_weight_pct = 100` on the
    referenced `ScreeningRule` row (updated this pass from a two-term sum).
  - **Gate-override guarantee (new, this pass):** for every `ScreeningRun` where
    `screening_education_gate_passed = false`, `screening_decision = "Fail"`
    regardless of `screening_score` — a case where a high score and `Fail` coexist
    is expected and correct (proof case: `business_rules.md` §5a, CAND-000104); a
    case where `screening_decision = "Pass"` despite `screening_education_gate_passed
    = false` is a violation, full stop.
  - At most one `ScreeningRun` row per `application_id` has `is_latest=true` (zero
    before first screening, exactly one after — never two, `business_rules.md` §5);
    `Application`'s nine mirrored columns exactly equal that row; `screening_explanation`
    is reproducible by re-running the deterministic template against the same inputs
    (byte-for-byte string match).
  - `ScreeningRun.screening_rule_id` resolves to a `ScreeningRule` row whose
    scoring-criteria fields have never been updated since that `ScreeningRun` was
    created — checked by comparing the referenced row's fields against the exact
    values the formula recompute used (if they differ, the immutability policy in
    `data_dictionary.md` §9 was violated, which should be structurally impossible).
- **Implementation:** `validation/rules/screening_recompute.py`, importing the same
  `services/screening.py:compute_screening_score` function used at write time. This
  module reads only `Application` and `ScreeningRun` — no JSON parsing path exists
  anymore, since there's no JSON column left to parse.
- **Test:** `test_validation.py::test_screening_score_matches_formula`,
  `test_validation.py::test_screening_run_mirror_invariant` (renamed from
  `test_screening_history_invariant`), plus
  `test_business_rules.py::test_screening_formula_examples` (hand-computed fixtures:
  perfect match, partial skill match, below-education hard gate, zero-experience-weight
  edge case, and one explanation-string golden fixture).

## 6. Scheduling conflicts
- **Check:** for every `Interview`, its `[scheduled_start, scheduled_end)` window is
  fully contained in one of the interviewer's `InterviewerAvailabilitySlot` windows,
  and does not overlap any other `Interview` for the same interviewer.
- **Implementation:** `validation/rules/scheduling_conflicts.py`.
- **Expected positive hits:** exactly 15 (full) / 3 (starter) — anomaly type 1,
  unchanged by Rev 2.
- **Test:** `test_validation.py::test_scheduling_conflicts_matches_seeded_count`.

## 7. Lifecycle transitions
- **Check:** every transition recorded in the three history tables is a legal edge in
  the state graphs in `business_rules.md` §2–3, every entity's current state agrees
  with its latest history row, **and** (new) every history row's `actor_id` resolves to
  an active `SystemActor`.
- **Implementation:** `validation/rules/lifecycle_transitions.py`, state graphs encoded
  once and shared with `services/*_lifecycle.py` (architecture.md §6).
- **Test:** `test_validation.py::test_no_illegal_transitions_in_history`.

## 8. Feedback requirements
- **Check:** `business_rules.md` §6 — no `Application` at stage `Offer`/`Hired` has a
  `Completed` interview without a `Feedback` row.
- **Implementation:** `validation/rules/feedback_requirements.py`.
- **Expected positive hits:** exactly 10 (full) / 2 (starter) — anomaly type 3,
  unchanged by Rev 2.
- **Test:** `test_validation.py::test_missing_feedback_matches_seeded_count`.

## 9. Offer approval rules
- **Check:** every `Offer` with `status ∈ {Approved, Extended, Accepted}` has an
  `approved_at`/`approved_by_actor_id`, that actor exists and is active, and
  `JobRequisition.status` was `Open` at `approved_at` time (via
  `RequisitionStatusHistory`).
- **Implementation:** `validation/rules/offer_approval.py`.
- **Test:** `test_validation.py::test_offer_approval_requires_open_requisition`.

## 10. Salary-band compliance
- **Check:** `business_rules.md` §7 — `Offer.proposed_salary ∈
  [requisition.salary_min, requisition.salary_max]`.
- **Implementation:** `validation/rules/salary_band.py`.
- **Expected positive hits:** exactly 6 (full) / 1 (starter) — anomaly type 4,
  unchanged by Rev 2.
- **Test:** `test_validation.py::test_salary_band_matches_seeded_count`.

## 11. Duplicate applications — rewritten against `ApplicationSubmissionAttempt` (Rev 2)
- **Check (Rev 2):** rather than grouping `Application` by
  `(candidate_id, requisition_id)` (impossible now — the PK makes that structurally
  unique, `entity_relationships.md` §5), this rule runs the detection algorithm in
  `business_rules.md` §10 over `ApplicationSubmissionAttempt`: group by
  `(candidate_id, requisition_id)`, sort by `(submitted_at, attempt_id)` ascending
  (the deterministic tie-break, clarified this pass), flag every non-canonical
  attempt. Also verifies (new, this pass): the partial unique index
  `uq_attempt_canonical` and check constraint on `(is_canonical,
  duplicate_of_attempt_id)` (`data_dictionary.md` §8a) report zero violations. A
  secondary structural check confirms `Application`'s PK uniqueness independently
  guarantees there is never more than one `Application` row per pair (this should
  always pass by construction — a failure here would indicate the ID-derivation
  function is broken, not that duplicates exist).
- **Implementation:** `validation/rules/duplicate_submissions.py` (renamed from
  `duplicate_applications.py`), importing the same grouping logic described in
  `business_rules.md` §10 — this module **must not** import or reference
  `AnomalyLabel`/`ground_truth_label_id` anywhere in its detection path; a dedicated
  test enforces this by import-graph inspection (`test_validation.py` asserts
  `duplicate_submissions.py` has no reference to the `AnomalyLabel` model).
- **Expected positive hits:** exactly 15 (full) / 3 (starter) non-canonical attempts —
  note this is a *count correction* from Rev 1, which (under the old model) expected
  30 affected `Application` rows; Rev 2's figure is the attempt-level count.
- **`rule_category` sub-split (Phase 5/6 boundary clarification, added this pass):**
  this rule's findings are not all the same kind of thing, even though they all share
  `rule_id="VAL-11"`. Three structurally distinct `rule_category` values distinguish
  them — never message-string matching:
  - `duplicate_submission_consistency` — the *stored* fields disagree with a fresh
    recompute; always a genuine defect (the write path is broken), never expected.
  - `duplicate_submission_detected` — the algorithm determines this attempt is a
    duplicate; not a defect, this **is** the "expected positive hits" count above.
    Phase 6's offline evaluator must select only this category (via
    `duplicate_submissions.select_detected_duplicates()`, which filters on
    `rule_category`, not on `message` text) before matching against ground truth —
    the consistency and invariant findings are never part of that comparison.
  - `duplicate_submission_invariant` — more than one canonical attempt for the same
    `Application`; a structural defect, independent of the above (and, like PK
    uniqueness, structurally impossible to construct given `uq_attempt_canonical` —
    verified only on clean data, never by deliberate corruption).
- **Test:** `test_validation.py::test_duplicate_submissions_matches_seeded_count`,
  `test_validation.py::test_duplicate_detector_never_imports_anomaly_label`,
  `test_validation.py::test_val11_consistency_mismatch_has_consistency_category`,
  `test_validation.py::test_val11_detected_duplicate_has_detected_category`,
  `test_validation.py::test_val11_invariant_category_clean_on_baseline`,
  `test_validation.py::test_val11_select_detected_duplicates_filters_by_structured_field`.

## 12. Reconciliation of generated records
- **Check:** row counts match targets (including the corrected
  `ApplicationSubmissionAttempt` 3,015/153 and `AnomalyLabel` 56/11 totals — see
  `business_rules.md` §9/§12), FK orphan count is zero, every `Application` has
  exactly one canonical attempt, every `Application` has exactly one `ScreeningRun`
  with `is_latest=true` and the `ScreeningRun` row count equals the `Application` row
  count (3,000/150), each of the five anomaly-specific checks above reports a count
  equal to its documented injection count, and (new, this pass) every `JobRequisition`
  that has ever had a `ScreeningRule` has exactly one `is_current=true` row, with the
  three partial unique indexes (`uq_attempt_canonical`, `uq_screeningrun_latest`,
  `uq_screeningrule_current`) all reporting zero violations.
- **Closed-req-with-active-applications check** (anomaly type 5):
  `validation/rules/closed_req_active_apps.py` — flags any `JobRequisition` with
  `status ∈ {Closed, Cancelled}` that has active `Application` rows attached.
  **Reporting granularity, keyed on `application_id` (finalized this pass):** emits
  one violation row per affected `Application.application_id` — not one
  aggregated violation per requisition — so a requisition with 2 active
  applications produces 2 violation rows, each independently keyed. This matches
  `AnomalyLabel`'s `entity_id` exactly, now that `entity_type=Application` for
  this type (`data_dictionary.md` §16, `business_rules.md` §9b) — the detector's
  output and the ground truth use the *same* field as their matching key, with
  `requisition_id` carried only as supporting context on each violation, never as
  the key itself. This alignment is what makes TP/FP/FN comparable against ground
  truth at all (§22 below) — if the detector keyed on `requisition_id` while
  ground truth keyed on `application_id`, "one incident" vs. "one label" would
  never line up. Expected hits: 5 incidents / 10 violation rows
  (full), 1 incident / 2 violation rows (starter) — A-12.
- **Implementation:** `validation/reconcile.py`.
- **Test:** `test_validation.py::test_full_reconciliation_report`.

## 13. Deterministic reproducibility using checksums
- **Check:** running `data_generation/generator.py --seed 20261022 --mode full`
  twice, with the same `generator_version`, produces byte-identical CSV/JSON/SQL
  exports across the **21 operational content tables** — every table except
  `GenerationRun` itself. **Corrected scope, this pass:** `GenerationRun`'s own
  exported row is *not* expected to be byte-identical across the two runs
  (`run_id` and `generated_at` are per-invocation execution metadata, not dataset
  content, `data_dictionary.md` §17) — what *is* expected to match, within that
  row, is the `entity_counts_json`/`table_checksums_json`/`overall_checksum`
  field *values*, plus the *results* portion (not the `checked_at` timestamp) of
  both validation-report JSON fields. "Repeated runs produce identical checksums"
  refers to these deterministic-content fields, never to the whole
  `GenerationRun` row or table.
- **Implementation:** `validation/checksums.py`, shared with
  `data_generation/checksums.py`.
- **Test:** `test_generation_reproducibility.py::test_same_seed_same_checksum` and
  `test_same_seed_different_mode_differ`.

## 14. Role-appropriateness (added because the review introduced `SystemActor` roles; split into hard/soft this pass)
- **Check:** for every row in the three history tables, and for `Offer.
  approved_by_actor_id`/`JobRequisition.requested_by_actor_id`/
  `GenerationRun.generated_by_actor_id`, the referenced `SystemActor.role` matches the
  expected role(s) in `business_rules.md` §11.
- **Severity — revised, this pass (A-14):** `"violation"` for the two rows
  `business_rules.md` §11 marks **Hard** (`RequisitionStatusHistory
  PendingApproval→Approved` and `OfferStatusHistory PendingApproval→Approved` /
  `Offer.approved_by_actor_id`) — a hit here means the service-layer gate in
  `services/requisition_lifecycle.py` / `services/offer_lifecycle.py` was bypassed,
  which should never happen in data produced through the service layer. `"warning"`
  for every other row (unchanged — soft, reported-only convention, since there's no
  authentication system to back broader enforcement).
- **Implementation:** `validation/rules/role_appropriateness.py`.
- **Test:** `test_validation.py::test_role_appropriateness_report` — asserts the
  generated baseline dataset has zero role mismatches of either severity (the
  generator always assigns the "correct" role when creating history rows);
  `test_validation.py::test_hard_role_checks_cannot_be_bypassed` — a new test
  (this pass) that attempts to call `requisition_lifecycle.approve()` /
  `offer_lifecycle.approve()` with a non-`APPROVER` actor and asserts the service
  layer rejects it before any row is written.

## 15. Reporting format

```json
{
  "rule_category": "salary_band_compliance",
  "entity_type": "Offer",
  "entity_id": "OFR-00042",
  "message": "proposed_salary 210000 outside requisition band [120000, 180000]",
  "severity": "violation"
}
```
`severity` is `"violation"` for categories 1–13 (binary pass/fail by construction),
and for category 14 (role-appropriateness) it is split per-row (revised, this pass):
`"violation"` for the two hard-enforced approval checks, `"warning"` for every other
role expectation. `"warning"` is otherwise a deliberate, narrow exception to "no
separate severity tier" — it exists only because most of category 14 is explicitly
non-blocking by design (A-14).

## 16. What validation deliberately does NOT do

- It does not read `AnomalyLabel` or `ApplicationSubmissionAttempt.ground_truth_label_id`
  while computing any of categories 1–14 above — generalized and enforced for the
  whole package in §17 below, not just the duplicate-submission check. `AnomalyLabel`/
  `ground_truth_label_id` are consulted only in the separate, clearly-named offline
  evaluation step described in `workflow.md` §7 and `business_rules.md` §13 (step 5).
- It does not auto-fix violations. `validation/` is read-only; fixing is a `services/`
  concern invoked explicitly by a human/API call, never automatically triggered by a
  failed validation run.

## 17. Ground-truth non-leakage guarantee (generalized, this pass)

Confirms and formalizes `business_rules.md` §10a: `ground_truth_label_id` and
`AnomalyLabel` are strictly evaluation/audit artifacts, never a decision input.

- **Scope of the guarantee:** every module under `services/` — explicitly including
  `services/screening.py` (named here per review request) — and every module under
  `validation/rules/` (all 13 mandated categories plus role-appropriateness) — not
  just `validation/rules/duplicate_submissions.py`, which was the only module this
  check covered before an earlier pass. `services/screening.py` has no need to read
  `AnomalyLabel`/`ground_truth_label_id` in the first place (its three inputs are
  skill/experience/education only, `business_rules.md` §5) — the whole-package test
  confirms this by scanning its source, not by trusting that it has no reason to.
- **Concrete test, this pass:** `test_validation.py::test_no_ground_truth_leakage` —
  a single import-graph/AST-level check run once over the whole `services/` and
  `validation/rules/` packages, asserting that **no module in either package**
  contains a reference to the `AnomalyLabel` model or the string
  `ground_truth_label_id`, anywhere in its source (not just its imports — a module
  could in principle `SELECT *` and then dot into the column by name without
  importing the model, so the check scans for the field name itself, not just the
  import statement). One test, whole-package scope, rather than one hand-written
  per-module assertion — this means a *new* rule module added later is covered by
  the same test automatically, with no extra line to remember to write.
- **Explicit exclusions from this guarantee** (the only code allowed to touch ground
  truth, by design): `validation/reconcile.py`'s offline evaluation step
  (`business_rules.md` §13, step 5) and the frontend's dev-only "Ground Truth" view
  (`workflow.md` §7) — both read-only, both outside `services/` and
  `validation/rules/`, both named and scoped exactly so a reviewer can see at a glance
  that nothing else is permitted to touch this data.
- **Confirmed for `ScreeningRun`/screening specifically:** `ScreeningRun` and
  `Application`'s mirrored screening columns have no ground-truth column of any
  kind — there's nothing for the leakage test to even need to check there; screening
  is excluded from the guarantee's *scope* because it has no surface the guarantee
  would apply to, not because it was carved out as an exception.

## 18. Withdrawal-then-resubmission test cases (new, this pass — Option A, approved)

These exercise `business_rules.md` §3a / `workflow.md` §2b against the unmodified
canonical-reconciliation logic (§10/§11 above) and the unmodified lifecycle graph
(`business_rules.md` §3).

**Structural guarantee test, underlying all four cases below:**
`test_business_rules.py::test_reconcile_canonical_never_touches_application_stage`
— asserts, by code inspection of `reconcile_canonical()`'s write set (or by
mutation-testing: run it with `Application.stage` forcibly set to every enum value
and confirm it's unchanged after the call, for every value), that the function
writes only to `ApplicationSubmissionAttempt` rows. This is the one test that makes
every other guarantee below mechanical rather than aspirational.

| Test | Setup | Expected result | Covers |
|---|---|---|---|
| **Test 1** | Candidate applies (Application created) → candidate withdraws (`stage=Withdrawn`) → candidate submits again for the same requisition | Original `Application` remains `Withdrawn`; new attempt classified `DuplicateSubmission`, `duplicate_of_attempt_id` → the original attempt | `test_validation.py::test_withdrawal_then_resubmission_typical_case` |
| **Test 2** | Same as Test 1, but the resubmission's `submitted_at` is *earlier* than the original's (out-of-order arrival) | Canonical selection still follows `(submitted_at, attempt_id)` — the earlier attempt may become `is_canonical=true` and the original may be re-flagged `DuplicateSubmission` pointing at it — but `Application.stage` remains `Withdrawn` either way; no reactivation occurs | `test_validation.py::test_withdrawal_then_out_of_order_resubmission` |
| **Test 3** | Candidate withdraws from requisition A → applies to requisition B | Two independent canonical `Application` rows (`APP-<A>-<cand>`, `APP-<B>-<cand>`); no duplicate classification on either | `test_validation.py::test_withdrawal_then_application_to_different_requisition` |
| **Test 4** | Candidate submits again after withdrawal | `issue_type` is computed with zero access to `ground_truth_label_id` — same whole-package leakage test as §17, re-run against this scenario's rows specifically | `test_validation.py::test_withdrawal_resubmission_detection_ignores_ground_truth` |

All four are additive test cases over existing mechanisms — none required a new
validation rule category, a new table, or a new field.

## 19. Screening/decision logic test cases (new, this pass)

Exercises the three-weight formula (`business_rules.md` §5/§5a) and its
explainability/reproducibility/fairness guarantees.

| Test | Setup | Expected result |
|---|---|---|
| Correct score calculation | CAND-000101 from §5a (Expert Python, Advanced SQL, 6.0y exp, Master's) | `screening_score = 100.00`, `screening_decision = "Pass"` |
| Weight totals | `ScreeningRule` with `skill_weight_pct=50, experience_weight_pct=30, education_weight_pct=20` | Sum = 100; a rule with e.g. `50/30/15` (sum=95) is rejected at the schema/service layer, flagged as a violation if it ever reaches storage |
| Missing skills | CAND-000105 from §5a (no `CandidateSkill` row for either required skill) | `screening_skill_component = 0.00`, not an error, not a null — a well-defined zero |
| Missing experience | Candidate with `years_experience = 0.0` (the field is `NOT NULL`, §5 — "missing" cannot occur structurally; zero is the floor) against `min_years_experience = 4.0` | `screening_experience_component = 0.00` |
| Education gate failure | CAND-000104 from §5a (Associate degree against a Bachelor's minimum, otherwise perfect) | `screening_education_gate_passed = false`, `screening_decision = "Fail"` despite `screening_score = 93.33` |
| Boundary scores at thresholds | Two candidates identical except `years_experience` (4.0 vs 3.9), scoring exactly `70.00` and `69.25` against the default `pass_threshold_score = 70.0` (`business_rules.md` §5a, corrected this pass to a fully concrete pair) | `70.00 → Pass`, `69.25 → Fail` — confirms `≥`, not `>` |
| Identical inputs → identical outputs | Recompute `services/screening.py:compute_screening_score` twice against the same `Application`/`CandidateSkill`/`ScreeningRule` snapshot | Byte-identical `screening_score`, `screening_explanation`, and every component |
| Rule version changes | Redefine a requisition's `ScreeningRule` (new row, `version=2`, `is_current=true`); recompute a *historical* `ScreeningRun` created under `version=1` | The historical run's stored values are unchanged; its `screening_rule_id` still resolves to the `version=1` row, not `version=2` (`business_rules.md` §4) |
| Historical `ScreeningRun` preservation | Insert a second `ScreeningRun` for the same `Application` (simulating re-screening) | The first row's scored fields are byte-identical to before; only `is_latest` flips, on the first row, to `false` |
| Latest-run pointer consistency | After the second `ScreeningRun` insert above | `Application.latest_screening_run_id` and its nine mirrored columns equal the *second* row, not the first |
| Ground-truth leakage | Run `test_validation.py::test_no_ground_truth_leakage` (§17) with `services/screening.py` in scope | Zero references to `AnomalyLabel`/`ground_truth_label_id` found in its source |
| Exclusion of demographic proxies | Inspect `services/screening.py:compute_screening_score`'s parameter list | No `full_name`, `location_city`, `location_country`, `source_channel`, or any other non-skill/experience/education argument is accepted — checked by signature inspection, not just by reading the function body |

Sample test data for the first six rows is the shared `REQ-00010` setup and the five
candidates in `business_rules.md` §5a — reused here rather than restated, so the
numbers in both documents can never silently drift apart.

## 20. Export consistency (new, this pass — previously implied, never a named category)

**Gap closed this pass:** exports were previously described (`architecture.md` §1/§7)
but never had their own validation rule — nothing explicitly checked that an export
*matches* the database it was generated from. Added now as its own category.

- **Check:** for every one of the 22 tables, in every format (CSV, JSON, SQL):
  - Row count in the export exactly equals the row count in the live database table
    at export time.
  - Every FK value appearing in an exported row resolves to a row present in the
    *same* export (an export is never partial/filtered in a way that would orphan a
    reference — all 22 tables are always exported together, from the same snapshot).
  - The SQL export, executed against a fresh empty SQLite database, produces a
    database that is row-for-row identical to the live one it was exported from.
  - Re-running the generator with the same seed and mode produces byte-identical
    export files (not just an identical live database) — this is the export-level
    analogue of `GenerationRun.overall_checksum` (§13), checked on the files
    themselves, not just the DB.
- **Implementation:** `validation/rules/export_consistency.py` — round-trips each
  CSV/JSON back into a scratch table and diffs against the live table; executes the
  SQL export against a throwaway DB and diffs the result; hashes the three export
  directories and compares against `GenerationRun.table_checksums_json`.
- **Applies to:** post-injection only (exports are produced once, from the final
  state of a generation run, after both baseline generation and anomaly injection
  have completed — there is no separate "baseline-only" export in this design).
- **Test:** `test_generation_reproducibility.py::test_export_matches_database`,
  `test_export_reproducible_across_runs`.

## 21. Validation rule catalog (Rule IDs, new this pass)

Formal `VAL-nn` identifiers for every check above, cross-referenced to its detailed
section rather than re-described. `Applies to` distinguishes checks that must report
**zero violations at every stage** (nothing about anomaly injection should ever
affect them) from the five that are **expected to change** between the baseline gate
(zero) and post-injection detection (an exact, documented count).

| Rule ID | Description | Severity | Input tables | Detection logic | Expected output | Applies to |
|---|---|---|---|---|---|---|
| VAL-01 | Primary-key uniqueness | Violation | all 22 | §1 | Zero violations | Both |
| VAL-02 | Foreign-key integrity | Violation | all 22 | §2 | Zero violations | Both |
| VAL-03 | Required fields, nullability, enum/allowed values | Violation | all 22 | §3 | Zero violations | Both |
| VAL-04 | Date/timestamp ordering | Violation | per `data_dictionary.md`'s ordering rules | §4 | Zero violations | Both |
| VAL-05 | Screening score calculation + reproducibility | Violation | `Application`, `ScreeningRun`, `ScreeningRule` | §5 | Zero violations | Both — screening is untouched by any anomaly type |
| VAL-06 | Interview scheduling / interviewer availability | Violation | `Interview`, `InterviewerAvailabilitySlot` | §6 | **Zero at baseline; exactly 15 (full) / 3 (starter) post-injection** | Both, different expected count |
| VAL-07a | Requisition lifecycle | Violation | `JobRequisition`, `RequisitionStatusHistory` | `business_rules.md` §2, this doc §7 | Zero violations | Both |
| VAL-07b | Application lifecycle | Violation | `Application`, `ApplicationStageHistory` | `business_rules.md` §3, this doc §7 | Zero violations | Both |
| VAL-08 | Feedback completeness | Violation | `Interview`, `Feedback`, `Application` | §8 | **Zero at baseline; exactly 10 (full) / 2 (starter) post-injection** | Both, different expected count |
| VAL-09 | Offer approval rules | Violation | `Offer`, `JobRequisition`, `RequisitionStatusHistory`, `SystemActor` | §9 | Zero violations | Both |
| VAL-10 | Salary-band compliance | Violation | `Offer`, `JobRequisition` | §10 | **Zero at baseline; exactly 6 (full) / 1 (starter) post-injection** | Both, different expected count |
| VAL-11 | Duplicate-submission detection | Violation | `ApplicationSubmissionAttempt`, `Application` | §11 | **Zero at baseline; exactly 15 (full) / 3 (starter) non-canonical attempts post-injection** | Both, different expected count |
| VAL-12 | Reconciliation of generated records (incl. closed-req-with-active-applications, anomaly type 5) | Violation | all 22 | §12 | Baseline: all counts match targets, zero `AnomalyLabel` rows. Post-injection: counts match targets + exactly 56 (full) / 11 (starter) `AnomalyLabel` rows, incl. **5 (full) / 1 (starter) closed-req incidents affecting 10/2 Application rows** | Both, different expected count |
| VAL-13 | Deterministic reproducibility (checksums) | Violation | all 22, `GenerationRun` | §13 | Identical checksums across repeated runs with the same seed | Both |
| VAL-14 | Role-appropriateness | Violation (2 hard rows) / Warning (rest) | three history tables, `Offer`, `JobRequisition`, `GenerationRun`, `SystemActor` | §14 | Zero violations (hard rows); zero expected but non-blocking if found (soft rows) | Both |
| VAL-15 | Ground-truth non-leakage (whole-package) | Violation | `services/*`, `validation/rules/*` source code | §17 | Zero references to `AnomalyLabel`/`ground_truth_label_id` found | N/A — static check on code, not data |
| VAL-16 | Export consistency | Violation | all 22, plus the three export formats | §20 | Zero diffs, every table, every format | Post-injection only |

**Why the user-requested list maps to 14 rows, not 16 bullets:** "Enum validation"
(the brief's bullet) is the same Pydantic-driven check as "required fields" —
VAL-03 covers both, since splitting them would duplicate one implementation under
two rule IDs. "Requisition lifecycle" and "Application lifecycle" are split into
VAL-07a/VAL-07b here specifically because the brief asked for them separately, even
though `business_rules.md` documents both lifecycle graphs under one umbrella
concept (state-transition legality) — no duplicated logic, just two rows pointing
at sibling sections of the same document.

## 22. Detection quality and evaluation (revised, this pass — corrected labeling + evaluation model)

**Important correction, this pass:** the prior version of this section described a
"TP=15, FP=0, FN=0" result as an "actual expected result." That wording overstated
what exists: **no application code has been written yet** (Phase 0, documentation
only) — there is no detector implementation to have run and produced a measured
result. Every number below is a **design-derived projection** (what the documented
algorithm, applied to the documented injection mechanism, logically implies), not
an empirically observed test result. This section now labels every number
explicitly as **EXPECTED** (derived from the design, not yet measured) rather than
implying it was tested.

**Evaluation granularity, clarified this pass: affected-entity level, not incident
level.** TP/FP/FN are counted over the same units `AnomalyLabel` is scoped to —
one unit per affected entity (`business_rules.md` §9a) — not one unit per incident.
These coincide for four of the five categories (one affected entity per incident)
but not for type 5, where one incident has two affected `Application` rows and
therefore counts as **two independently matchable units**, not one.

**Matching key per category** (the field that pairs a detector output row with an
`AnomalyLabel` row — now uniform across all five types, this pass, since
`entity_id` always holds the evaluation unit and `related_entity_id` always holds
supporting context, `data_dictionary.md` §16):

| Category | Matching key |
|---|---|
| 1. Interviewer unavailable | `Interview.interview_id` ↔ `AnomalyLabel.entity_id` |
| 2. Duplicate application | `ApplicationSubmissionAttempt.attempt_id` ↔ `AnomalyLabel.entity_id` |
| 3. Missing feedback | `Application.application_id` ↔ `AnomalyLabel.entity_id` |
| 4. Salary out of band | `Offer.offer_id` ↔ `AnomalyLabel.entity_id` |
| 5. Closed req, active apps | `Application.application_id` ↔ `AnomalyLabel.entity_id` — **no longer an exception** (flipped this pass, `business_rules.md` §9b); `JobRequisition.requisition_id` appears only as `related_entity_id` context, never as the key |

**How one closed-requisition incident affecting two applications is evaluated:**
per §12's revised reporting granularity, the detector emits one violation row per
affected `Application.application_id` — so one incident yields exactly 2
detector-output rows, matching the 2 `AnomalyLabel` rows the injector wrote for it.
Each of the 2 is matched and scored independently via `Application.application_id`:
both correctly flagged → 2 TPs for that incident; one missed → 1 TP + 1 FN; neither
→ 2 FNs. The incident itself is never the unit of comparison — only the individual
`Application` rows are (`business_rules.md` §9b).

```
TP (true positive)  = a detector-output unit for anomaly type X that matches an
                       AnomalyLabel of type X on the key above
FP (false positive) = a detector-output unit for type X with no matching
                       AnomalyLabel (a false alarm)
FN (false negative)  = an AnomalyLabel of type X with no matching detector-output
                       unit (a miss)

Precision = TP / (TP + FP)
Recall    = TP / (TP + FN)
F1        = 2 × Precision × Recall / (Precision + Recall)
```

**Detector isolation, confirmed explicitly (this pass):** the detector cannot
access `AnomalyLabel`, `ground_truth_label_id` (VAL-15, §17), any other
generation-time label, **or this evaluation step's own output** — the data flow is
one-directional: detect (step 4) → compare (step 5); step 5 reads step 4's already-
finalized output and `AnomalyLabel`, but nothing step 5 produces is ever read back
into step 4, in the same run or any future one. There is no cycle for ground truth
or evaluation results to leak through.

**Worked example 1 — EXPECTED result (design-derived, not yet tested), duplicate-
application category (type 2):** 3,015 total `ApplicationSubmissionAttempt` rows;
exactly 15 carry a seeded `ground_truth_label_id`. The documented algorithm (§11)
is, by its own logic, deterministically aligned with how the injector builds these
rows (every non-canonical attempt is, by construction, exactly one of the 15 seeded
ones — no pair has more than 2 attempts in this dataset's design) — so the design
*implies* the detector would flag exactly those same 15 rows:
```
EXPECTED: TP = 15, FP = 0, FN = 0
Precision = 15/15 = 1.00, Recall = 15/15 = 1.00, F1 = 1.00
```
This is a design expectation to be confirmed by actual tests once
`services/`/`validation/rules/` are implemented (Phase 4/5) — **not a reported test
result**. The same expectation, computed independently per category, should hold
for all five types once real code exists; this evaluation is specified to run every
generation cycle precisely so that a future regression (e.g., a tie-break bug)
would show up as a measured drop below 1.00 — something that can only be observed
once the detector is actually implemented and run.

**Worked example 2 — illustrative hypothetical, not a projection of this design,
included only to show the formulas computing a non-trivial result:** if a detector
implementation had a bug that missed 2 of 15 duplicate-type incidents and falsely
flagged 1 legitimate pair:
```
HYPOTHETICAL (illustrates the formula, not an expected or observed result):
TP = 13, FP = 1, FN = 2
Precision = 13/14 = 0.929, Recall = 13/15 = 0.867
F1 = 2 × 0.929 × 0.867 / (0.929 + 0.867) = 1.611 / 1.796 ≈ 0.897
```
A real result like this, once code exists, would indicate a genuine defect — it is
shown here purely to demonstrate the arithmetic, not as something this design
predicts or has observed.

## 23. Indirect ground-truth leakage paths (new, this pass — explicitly identified, per review request)

VAL-15 / §17's whole-package scan catches **direct** references to `AnomalyLabel`/
`ground_truth_label_id` in source code. Considered, and assessed below, for
**indirect** channels the scan does not cover:

1. **Generic audit-timestamp correlation.** Anomaly injection runs as a distinct
   pass after baseline generation (`architecture.md` §4), so injected/mutated rows
   could in principle have `updated_at` values systematically later than untouched
   rows' — a detector that naively used `updated_at`/`created_at` deltas as a signal
   could indirectly correlate with anomaly status without ever reading
   `AnomalyLabel`. **Assessed: not currently exploited** — none of the detection
   functions (§6/§8/§10/§11) reference `updated_at`/`created_at` anywhere in their
   logic; each reads only the specific business fields named in its section. This is
   a real boundary of the leakage guarantee, though: VAL-15 checks for named-field
   references, not for this kind of incidental metadata correlation, so a future
   detector that *did* start reading generic timestamps would not be caught by the
   existing test. Documented as a known boundary, not fixed with a new test this
   pass, since no current code exercises it.
2. **Seeded-RNG-state correlation.** Both the baseline generator and the anomaly
   injector derive from the same `base_seed` (`architecture.md` §4). Nothing in the
   system attempts to reverse-engineer which rows were selected for injection from
   RNG state alone, and no detector has access to the seed or RNG state at all (they
   operate on stored row values only) — this channel is not just unexploited but
   structurally inaccessible to any of the detection functions as written.
3. **`GenerationRun` manifest fields.** `entity_counts_json`/`table_checksums_json`
   are reproducibility artifacts, never read by any detection or screening function
   — confirmed by the same VAL-15 scan (these functions aren't in its exclusion
   list, `§17`). Not a leakage path.

No currently-exploited indirect leakage path was found. Path 1 is the one named,
documented limitation of the leakage guarantee's current scope.
