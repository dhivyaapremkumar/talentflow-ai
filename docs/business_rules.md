# Business Rules

**Revision 2** — adds the duplicate-submission detection algorithm (§10), actor-role
conventions for every lifecycle transition (§11), expanded screening explainability
(§5), and corrects the anomaly-injection and reconciliation math (§9) to distinguish
incidents from affected rows.

**Second verification pass** — replaces the JSON-array screening history with a
dedicated, insert-only `ScreeningRun` table (§5, resolves A-16); confirms and scopes
ground-truth non-leakage explicitly (§10a); splits role-appropriateness into
hard-enforced (requisition/offer approval, §11) and soft (everything else); adds the
confirmed five-step generation-and-verification pipeline (§13); extends reconciliation
for `ScreeningRun` (§12).

**Implementation-detail clarification pass** — `ScreeningRule` is now
versioned/insert-only with an `is_current` flag, and `ScreeningRun.screening_rule_id`
is a direct FK to it, resolving historical reproducibility (§4); the
duplicate-submission tie-break is pinned to `(submitted_at, attempt_id)` (§10); the
`ScreeningRun` zero-before/one-after invariant and its atomic consistency procedure
are made explicit (§5); reconciliation extended for all three new partial unique
indexes (§12).

**Withdrawal/resubmission policy pass** — documents the approved Option A policy
(§3a): withdrawal never releases the `(candidate_id, requisition_id)` pair; no
change to the canonical-reconciliation algorithm or to the lifecycle state graph was
needed, since the two mechanisms were already orthogonal.

**Screening/decision logic verification pass** — resolves a real inconsistency:
education moves from gate-only to gated-and-graded, adopting the proposed 50/30/20
weight split (§5, new §5a worked examples, A-19); adds an explicit fairness-scope
statement — what this design can and cannot establish (§8).

**Final approval pass** — §5 marked APPROVED; default `pass_threshold_score=70.0`
documented explicitly; zero-division safety for both `experience_component` and
`education_component` stated explicitly rather than left as an implicit "else"
clause; §5a's boundary pair replaced with a fully concrete, hand-verified example
(the prior version was an unverified placeholder). All five primary worked examples
re-verified against the approved formula — no numerical corrections were needed.

**Anomaly generation and validation verification pass** — §1 adds an explicit
baseline-vs-final-volume clarification (A-5); §13's abort mechanism made concrete
(exception halts the process before the anomaly-injection module is even
imported); §13 updated to reference the full 16-category `VAL-nn` catalog
(`validation_strategy.md` §21) and the new precision/recall/F1 framework (§22).

**Prompt 5 correction pass** — new §9a resolves the 51-vs-56 arithmetic question
with an explicit granularity table; new §13a gives a complete before/after table
distinguishing modified/added/removed rows across the pipeline.

**Prompt 5 final clarification pass (this revision)** — §9 flips
`ClosedReqActiveApplications`'s `entity_type` from `JobRequisition` to
`Application` so `entity_id` is uniformly the matching key; new §9b states the four
distinct counts for that anomaly type side by side; new §13b clarifies which
`GenerationRun` fields are volatile execution metadata vs. deterministic content,
and adds `generator_version` as a precondition for the reproducibility claim. No
anomaly count, row count, or table changed.

## 1. Funnel targets the generator must hit (full dataset, seed 20261022)

| Stage | Target count | % of previous stage |
|---|---|---|
| JobRequisition | 100 | — |
| Application | 3,000 | 30 per requisition, avg |
| ApplicationSubmissionAttempt | 3,015 | 3,000 canonical + 15 seeded duplicates |
| Applications reaching `Interviewing` or beyond | ~430 | ~14% of 3,000 |
| Interview rows | 600 | ~1.4 rounds per interviewed application |
| Applications reaching `Offer` or beyond | 150 | ~35% of interviewed applications |
| Offer | 150 | 1 per offered application (1:1) |
| Offers reaching `Hired` (Application.stage) | ~110–130 | ~75–85% accept rate |

Starter dataset (A-6, 5% scale): 10 / 150 / 153 / ~22 / 30 / 8 / ~6.

**Baseline volume vs. final/exported volume (clarified, this pass — A-5):** the
table above states **final, post-injection, exported** counts — these are what the
generator must produce by the end of the full pipeline, not a pre-anomaly baseline
that then grows. Per A-5, anomalies are injected *within* these totals (mutating or
adding a row that was always part of the planned count), never on top of them.
`Application` (3,000) and `Interview` (600) are untouched in row count by injection
— their anomalies mutate existing rows' fields, not row counts.
`ApplicationSubmissionAttempt` (3,015) is the one count that is visibly "baseline
3,000 + 15 injected" in its own row, because that type's anomaly *is* an extra row
by nature (§9) — still within the planned final total, not grown afterward. The
database and every export reflect only this one, final state — there is no
separate "pre-injection" snapshot persisted or exported anywhere in this design.

Reference/catalog tables (A-13, fixed, identical both modes): Department 10, Skill 40,
Interviewer 25, SystemActor 20.

## 2. JobRequisition lifecycle

```
Draft ──► PendingApproval ──► Approved ──► Open ◄──► OnHold
                                             │
                                             ▼
                                           Closed

(Cancelled reachable from Draft, PendingApproval, Approved, Open, OnHold)
```
- Terminal states: `Closed`, `Cancelled`. No transitions out of either.
- `Open → OnHold → Open` is allowed any number of times.
- Every transition writes exactly one `RequisitionStatusHistory` row, referencing the
  `SystemActor` who performed it via `actor_id` (never free text, Rev 2) — rows are
  never updated or deleted (brief §3, "do not overwrite historical state changes").
- A requisition may only move to `Open` if it has exactly one `ScreeningRule` with
  `is_current=true` (**changed, this pass** — `ScreeningRule` is now versioned and
  insert-only, §4; "exactly one" now means exactly one *current* row, not exactly one
  row ever) and at least one `JobRequisitionSkill` row.
- Expected actor role per transition (soft-checked, A-14 — see §11 for the full table):
  `Draft→PendingApproval`: `BUSINESS_REQUESTER`. `PendingApproval→Approved`:
  `APPROVER`. `Approved→Open`, `Open↔OnHold`, `Open→Closed`: `PROCESS_OWNER`.
  `*→Cancelled`: `APPROVER` or `PROCESS_OWNER`.

## 3. Application, Interview, and Offer lifecycles

**Application.stage**
```
Applied ──► Screening ──► Interviewing ──► Offer ──► Hired
   │             │              │             │
   └─────────────┴──────────────┴─────────────┴──► Withdrawn (candidate-initiated, any non-terminal stage)
                  │              │
                  └──────────────┴────────────────► Rejected (recruiter-initiated, any non-terminal stage except Applied)
```
- Terminal: `Hired`, `Rejected`, `Withdrawn`.
- `Rejected` is reachable from `Screening`, `Interviewing`, or `Offer` (not directly
  from `Applied` — every application is screened before a reject decision is recorded,
  even if the screening score was 0).
- `Withdrawn` is reachable from any non-terminal stage.
- Forward progression may not skip a stage.
- Every transition writes one `ApplicationStageHistory` row with `actor_id` → expected
  role `PROCESS_OWNER` (§11).

**Interview.status**: `Scheduled → Completed`, `Scheduled → Cancelled`,
`Scheduled → NoShow`. All three right-hand states are terminal.

**Offer.status**
```
Drafted ─► PendingApproval ─► Approved ─► Extended ─┬─► Accepted
                                                      └─► Declined
(Rescinded reachable from Approved or Extended; Expired reachable from Extended only)
```
Terminal: `Accepted`, `Declined`, `Rescinded`, `Expired`. Expected actor role per
transition: §11.

## 3a. Withdrawal and resubmission policy — Option A, approved (new, this pass)

**Decision:** withdrawal does **not** release the `(candidate_id, requisition_id)`
pair. If a candidate withdraws and later submits again for the *same* requisition,
the system does not create a new canonical `Application` or reopen the old one — it
records the new submission as another `ApplicationSubmissionAttempt` against the
**same** canonical `Application`, exactly as any other repeat submission would be.

This requires **no change to the canonical-reconciliation algorithm (§10)** and
**no new lifecycle state**, because the two mechanisms involved were already
orthogonal before this decision was made:

- `Application.stage` transitions (this section, above) are driven exclusively by
  explicit lifecycle actions — screening results, interview/offer outcomes, an
  explicit withdraw action. Nothing in `reconcile_canonical()` (§10) reads or writes
  `Application.stage`; it only ever touches `ApplicationSubmissionAttempt` rows.
- `ApplicationSubmissionAttempt.is_canonical`/`issue_type` are driven exclusively by
  the `(submitted_at, attempt_id)` reconciliation over attempts for the pair. Nothing
  in that reconciliation reads `Application.stage`.

Because neither mechanism inspects the other, "withdrawal doesn't release the pair"
falls out of the existing design rather than requiring new machinery:

1. The original canonical `Application` row is never deleted, replaced, or given a
   second row for the same pair — the derived PK already makes a second row for the
   pair structurally impossible (`data_dictionary.md` §8).
2. A resubmission for the same pair after withdrawal is just another
   `ApplicationSubmissionAttempt` insert, which triggers `reconcile_canonical()`
   exactly as any other new attempt would (§10) — no withdrawal-specific branch
   exists anywhere in that function.
3. In the realistic case (the resubmission's `submitted_at` is later than the
   original's, since you withdraw before you resubmit), the new attempt sorts after
   the original and is classified `DuplicateSubmission` — the expected, typical
   outcome.
4. In the adversarial edge case where the new attempt's `submitted_at` is somehow
   *earlier* than the original's (out-of-order arrival, `business_rules.md` §10's
   own out-of-order handling), the reconciliation still runs unmodified: canonical
   status is re-derived purely from `(submitted_at, attempt_id)`, exactly as it
   would for any other pair. **What stays fixed regardless of that outcome** is
   `Application.stage` — it remains `Withdrawn`, because no part of either mechanism
   ever writes to it. "Reactivation" isn't prevented by a special guard; it's
   prevented by the fact that nothing in this path has a write path to `stage` at
   all.
5. `duplicate_of_attempt_id` always points at whichever attempt
   `reconcile_canonical()` currently holds canonical for the pair — the same rule
   used everywhere else, not a withdrawal-specific rule.
6. The detector's inputs are unchanged: `candidate_id`, `requisition_id`,
   `submitted_at`, `attempt_id` — `Application.stage` is not one of them, and
   `ground_truth_label_id` never is (§10a).

**No new lifecycle state was introduced.** `Withdrawn` was already terminal
(no outgoing transitions, §3 above) before this decision, and remains so — this
policy is a statement about what does *not* happen (no reactivation, no new
Application), not a new state or transition.

## 4. ScreeningRule versioning and historical reproducibility (revised, this pass)

`ScreeningRule` is versioned and insert-only, the same pattern already used for
`ResumeArtifact`/`ScreeningRun`: `version` starts at 1; a redefinition **inserts a
new row** with `version = previous + 1` and `is_current=true`, flipping the previous
row's `is_current` to `false`. No existing row's scoring-criteria fields are ever
updated (`data_dictionary.md` §9's immutability policy). This replaces the Rev 2
description, which described `version` as something that *might* increment via
updating the same row in place — that description was never implemented and is
retired here because it couldn't actually support the reproducibility guarantee
below.

**How a historical `ScreeningRun` stays reproducible once the current `ScreeningRule`
changes:**
1. `ScreeningRun.screening_rule_id` is a direct FK to the *specific* `ScreeningRule`
   row that was `is_current=true` at the moment that run was computed — not a lookup
   of "whichever row is current now."
2. That row is never mutated or deleted after creation (immutability policy, §9) — a
   later redefinition creates a *different* row (`is_current` flips there, not here).
3. Therefore, fetching `ScreeningRun.screening_rule_id` at any point in the future —
   next week, after three more redefinitions — always resolves to the exact
   `min_years_experience`/`min_education_level`/`skill_weight_pct`/
   `experience_weight_pct`/`education_weight_pct`/`pass_threshold_score` values
   (`education_weight_pct` added this pass, §5) that actually produced that run's
   score. Nothing about the run's reproducibility depends on the requisition's
   *current* rule state at all.
4. `screening_rule_version` (kept on both `ScreeningRun` and mirrored onto
   `Application`) is a denormalized copy of that same immutable row's `version` field
   — safe to keep only because the row it's copied from can never change out from
   under it.

In the generated dataset this mechanism exists but isn't exercised: every requisition
gets exactly one `ScreeningRule` row for its lifetime, so `screening_rule_id` always
points at `version=1`. The design supports a live system where redefinition actually
happens, without requiring a different mechanism later.

## 5. Screening score formula and explainability (APPROVED, this pass — three-weight model)

**Status: APPROVED.** The three-weight model, the 50/30/20 split, and the five
education-policy points below are explicitly user-approved — see `PROJECT_SPEC.md`
A-19 for the approval record.

**Resolved contradiction:** the prior formula weighted only skills and experience
(`skill_weight_pct + experience_weight_pct = 100`), treating education as a
pass/fail gate with no graded score — an inconsistent treatment of the three
dimensions (skill and experience were both graded; education alone was binary).
The approved weights (Skills 50% / Experience 30% / Education 20%) require education
to also contribute a graded score, so `ScreeningRule` gained `education_weight_pct`
and education gained a graded `education_component`, **exactly mirroring the
capping philosophy already used for `experience_component`** (credit scales up to
the minimum requirement, capped at 1.0 — no extra reward for far exceeding it). The
hard gate is kept, unchanged in effect: it is a second, independent check that can
still force `Fail` regardless of the weighted score. This is **not** a
reinterpretation of YottaFlex's requirements — it's an approved design choice for
the parts of the system YottaFlex left open.

**Approved education policy (verbatim, for traceability):**
1. Education is both a scored component and a mandatory eligibility gate.
2. Candidates meeting or exceeding the minimum education requirement receive full
   education component credit (1.0).
3. Candidates failing the minimum education requirement fail the eligibility gate,
   regardless of their numerical screening score.
4. Education scoring must not reward qualifications above the minimum requirement
   with anything beyond full credit (the `min(1.0, ...)` cap enforces this).
5. The education gate cannot be overridden by skills or experience scores.

For an `Application` against its `JobRequisition`'s `ScreeningRule` and
`JobRequisitionSkill` set, reused identically by `services/` and `validation/`
(architecture.md §6):

```
skill_match(candidate, skill)  = 1.0  if candidate's proficiency_level ≥ min_proficiency_level
                                = 0.5  if candidate has the skill but below min_proficiency_level
                                = 0.0  if candidate has no CandidateSkill row for it

skill_component        = Σ over required skills (weight_pct/100 × skill_match(candidate, skill))   # screening_skill_component, range 0–1

experience_component   = min(1.0, candidate.years_experience / rule.min_years_experience)
                          if rule.min_years_experience > 0 else 1.0                                  # screening_experience_component, range 0–1
                          # No division by zero is possible: when a role requires zero
                          # years of experience, this dimension is defined to award full
                          # credit (1.0) to every candidate — a deliberate business rule
                          # ("experience isn't a differentiator for this role"), not
                          # merely a coding safeguard. The division is never attempted.

education_rank(level)  = ordinal position, 1-indexed:
                          HighSchool=1, Associate=2, Bachelor=3, Master=4, Doctorate=5
                          # Every enum value has rank ≥ 1 — education_rank(rule.min_education_level)
                          # can never be 0 or undefined, so division by zero is structurally
                          # unreachable here regardless of configuration (unlike experience,
                          # where min_years_experience=0 is a valid, expected configuration).

education_component    = min(1.0, education_rank(candidate.highest_education_level)
                                   / education_rank(rule.min_education_level))                       # screening_education_component, range 0–1

education_gate_passed  = candidate.highest_education_level >= rule.min_education_level
                          (same ordinal comparison)                                   # screening_education_gate_passed

screening_score         = round(100 × (rule.skill_weight_pct/100 × skill_component
                                        + rule.experience_weight_pct/100 × experience_component
                                        + rule.education_weight_pct/100 × education_component), 2)
                          # Approved default configuration: skill_weight_pct=50,
                          # experience_weight_pct=30, education_weight_pct=20 — i.e.
                          # screening_score = round(100 × (0.50×skill_component
                          #   + 0.30×experience_component + 0.20×education_component), 2)
                          # Weights remain configurable per ScreeningRule (requirement 3
                          # below); 50/30/20 is the approved value, not a hardcoded constant.

screening_decision       = "Pass"  if education_gate_passed AND screening_score >= rule.pass_threshold_score
                          = "Fail" otherwise
                          # Default pass_threshold_score, documented explicitly: 70.0
                          # (data_dictionary.md §9) — configurable per ScreeningRule.
```

**Why the gate can't be "silently overridden" by the new education score:**
`education_component` only ever differs from 1.0 when the candidate is *below* the
minimum — at exactly the minimum or above, `education_rank(candidate)/education_rank(min) ≥ 1`
and the component is capped at exactly 1.0. So a candidate who passes the gate always
contributes full education credit (identical to how `experience_component` always
contributes full credit once the minimum is met); a candidate who fails the gate gets
a fractional component (so the recorded score still shows "how close" they were, same
rationale as before) **but `screening_decision` is `"Fail"` regardless of how high
that fractional contribution pushes the overall weighted score** — the `AND
education_gate_passed` clause in `screening_decision` is evaluated independently of,
and prior to, the weighted-score comparison; nothing about the arithmetic can make a
failed gate numerically disappear. This is identical to how the gate already worked
before this pass — only the score side gained a graded term, the gate's authority
over the decision is unchanged.

**No hard gate on skill or experience (confirmed intentional, this pass):** only
education has a brief-implied "eligibility gate" concept (brief: "eligibility gates
are explicitly defined" is an education-specific ask); skill and experience remain
graded-only, differentiated via `pass_threshold_score` on the weighted sum, not a
per-dimension cutoff. This asymmetry is deliberate, not an oversight.

**Explanation generation:** `screening_explanation` is built deterministically from
the same inputs, e.g.:
```
"Skill match 83.3% (2.5/3 weighted); experience 100.0% (6.0y ≥ 4.0y min);
education 100.0% (Master ≥ Bachelor min, gate passed); weighted score 91.7
(50/30/20) vs threshold 70.0 (rule v1) → Pass"
```
The template is fixed (no free-text generation, no LLM — this stays deterministic and
reproducible) and is unit-tested against hand-computed fixtures. It names only
skill/experience/education signals — never name, location, or any other field — so
it cannot leak sensitive information not already excluded from scoring (§8 below).

**History preservation:** every time screening is (re)computed for an `Application`,
a new, immutable `ScreeningRun` row is **inserted** (`data_dictionary.md` §8b)
holding `{screening_rule_id, screening_score, screening_skill_component,
screening_experience_component, screening_education_component` (new, this pass)
`, screening_education_gate_passed, screening_decision, screening_rule_version,
screening_explanation, computed_at}` plus its own `screening_run_id`. An
`Application` has zero `ScreeningRun` rows before its first screening and exactly one
`is_latest=true` row after — never a third state. The prior `is_latest=true` row (if
any) is flipped to `false` in the same atomic transaction that inserts the new row as
`is_latest=true` and updates `Application`'s mirrored columns — this is the only
write `ScreeningRun` ever receives after insert, and it touches a boolean flag, never
the scored fields themselves, so a previous run's recorded result can never be
altered once written. Full transactional sequencing: `data_dictionary.md` §8b.

In the generated dataset, screening runs exactly once per `Application` (there's no
re-screening workflow being simulated), so `ScreeningRun` has exactly one row per
application — the table and its insert-only contract exist so the mechanism is in
place and testable, not because the synthetic data exercises repeated screening.
`validation/rules/screening_recompute.py` asserts that `Application`'s mirrored
columns exactly match the `ScreeningRun` row referenced by `latest_screening_run_id`,
that exactly one `ScreeningRun` row per `application_id` has `is_latest=true`, and
recomputes the formula itself against that row.

This formula consumes only skills, experience, and education — **never** name,
location, or any other field — satisfying the demographic-proxy exclusion (§8 below).

### 5a. Worked examples (new, this pass)

Shared setup: `ScreeningRule` for `REQ-00010` — `min_years_experience=4.0`,
`min_education_level=Bachelor`, `skill_weight_pct=50`, `experience_weight_pct=30`,
`education_weight_pct=20`, `pass_threshold_score=70.0`. Required skills
(`JobRequisitionSkill`): Python (min `Advanced`, weight 60%), SQL (min
`Intermediate`, weight 40%).

| Candidate | Python | SQL | skill_component | years_exp | experience_component | education | education_component | gate | `screening_score` | `screening_decision` |
|---|---|---|---|---|---|---|---|---|---|---|
| CAND-000101 | Expert | Advanced | 1.00 | 6.0 | 1.00 | Master | 1.00 | Pass | **100.00** | **Pass** |
| CAND-000102 | Intermediate | Intermediate | 0.70 | 4.0 | 1.00 | Bachelor | 1.00 | Pass | **85.00** | **Pass** |
| CAND-000103 | none | Beginner | 0.20 | 2.0 | 0.50 | Bachelor | 1.00 | Pass | **45.00** | **Fail** (score) |
| CAND-000104 | Expert | Advanced | 1.00 | 8.0 | 1.00 | Associate | 0.667 | **Fail** | 93.33 | **Fail** (gate overrides a high score) |
| CAND-000105 | none | none | 0.00 | 0.0 | 0.00 | HighSchool | 0.333 | **Fail** | 6.67 | **Fail** (fails everywhere) |

CAND-000104 is the proof case for "education eligibility cannot be silently
overridden by other component scores": a 93.33 weighted score is still `Fail`,
because `education_gate_passed=false`.

**Boundary pair (corrected to a fully concrete, hand-verified pair, this pass —
the prior version was an unverified placeholder):** same `REQ-00010` rule
(threshold = 70.0). One required skill at weight 40% matched at the required
proficiency (contributes 0.40×1.0=0.40 to `skill_component`), the other at weight
60% not held at all (contributes 0) → `skill_component = 0.40`. Education =
Bachelor, gate passed, `education_component = 1.0`.
- `years_experience = 4.0` → `experience_component = 1.00` →
  `screening_score = round(100×(0.50×0.40 + 0.30×1.00 + 0.20×1.00), 2) = round(100×0.70, 2) = 70.00` → **Pass** (`≥` is inclusive).
- `years_experience = 3.9` (0.1 year less, same candidate otherwise) →
  `experience_component = 3.9/4.0 = 0.975` →
  `screening_score = round(100×(0.50×0.40 + 0.30×0.975 + 0.20×1.00), 2) = round(100×0.6925, 2) = 69.25` → **Fail**.

Demonstrates the boundary is evaluated inclusively (`≥`, not `>`) and
deterministically from the real formula, not illustrated with unverified numbers.

## 6. Feedback requirement

Rule: every `Interview` with `status = Completed` must have exactly one `Feedback` row
within a reasonable window (generator target: `submitted_at` within 72 hours of
`scheduled_end` — a data-quality target for the generator, not a hard validation rule).

Rule the validation engine *does* enforce strictly: an `Application` may not reach
stage `Offer` or `Hired` unless **every** `Interview` belonging to it with
`status = Completed` also has a `Feedback` row. Violations of this are exactly the
seeded "missing feedback but stage advanced" anomaly (§9) plus, in a live system, any
real data-entry gap.

## 7. Offer approval and salary-band rules

- An `Offer` may not move to `status = Approved` unless its `application_id`'s
  `requisition_id` has `JobRequisition.status = Open` at the time of approval (checked
  against `RequisitionStatusHistory`, not just the current status, so a requisition
  closed *after* a legitimate approval doesn't retroactively flag the offer).
- `Offer.approved_by_actor_id` must reference a `SystemActor`; expected role
  `APPROVER` (§11).
- Salary-band compliance: `offer.proposed_salary` must fall within
  `[requisition.salary_min, requisition.salary_max]`. Checked by the validation engine,
  not a DB constraint — this never touched structural integrity to begin with (PK/FK
  are untouched either way), it's purely a business-threshold check on an otherwise
  perfectly valid row, consistent with the restated A-10.
- **Limitation (A-8 consequence, unchanged from Rev 1):** because the band lives on the
  current `JobRequisition` row rather than a versioned snapshot, mutating a
  requisition's band after an offer against it was approved could retroactively flag a
  historically-valid offer. The generator never does this. A production system would
  need a band-snapshot field on `Offer` to fully close the gap — documented, not
  solved.

## 8. Demographic-proxy exclusion (brief §8)

No field anywhere in the schema encodes gender, age/date-of-birth, ethnicity, marital
status, religion, caste, nationality (distinct from work-location
`location_country`, kept only for interview-logistics display), photograph, name
(see note below), or address. The screening formula (§5) consumes exactly three
signals: skill proficiency match, years of experience, and education level, combined
via the requisition's declared weights/threshold. `location_city`/`location_country`
and `source_channel` are stored for operational/logistics display only and are
explicitly excluded from `services/screening.py` — enforced by a unit test asserting
the screening function's signature takes no location/channel argument, and (new,
this pass) no `full_name` argument either, even though `Candidate.full_name` exists
on the row the function is called with — the function's parameter list, not just its
body, excludes it, so it is structurally unable to read it.

**What this design can and cannot establish (new, this pass — explicitly, per
review request):**
- **Can establish:** no explicitly-named protected characteristic or common
  demographic proxy (name, gender, age, religion, caste, photograph, address) is
  collected anywhere in the schema, let alone passed to the scoring function; the
  scoring function's signature is structurally limited to skill/experience/education
  inputs, verifiable by inspection, not just by policy; every decision is
  deterministic, reproducible, and accompanied by a template-generated explanation
  that only ever names the three scored dimensions.
- **Cannot establish:** that the design is free of bias overall, or that it would
  satisfy any specific jurisdiction's legal or regulatory fairness requirements —
  **no such claim is made**. Education level, in particular, can correlate with
  protected characteristics through real-world structural inequality even though the
  field itself isn't a protected characteristic; this design does not attempt to
  detect or correct for that, and excluding explicit proxy fields does not guarantee
  the *absence* of indirect/statistical bias through the fields that remain. No
  disparate-impact or fairness statistical testing has been performed, and none is
  claimed. This is a structural safeguard against the specific, named proxies the
  brief identified (brief §8) — not a certification of fairness, legal compliance,
  or absence of bias in any broader sense.

## 9. Anomaly injection specification — incidents vs. affected rows (corrected in Rev 2)

All five anomaly types are produced by `data_generation/anomalies/`, run **after** the
full valid baseline (including all canonical `ApplicationSubmissionAttempt` rows)
exists. Per the restated A-10, no injector ever produces a structurally invalid row
(no duplicate PK, no dangling FK) — every injected anomaly is a legitimate row that
only a business-rule check can flag.

| # | Anomaly type | Mechanism | Incidents (full/starter) | Affected rows (full/starter) | Affected table |
|---|---|---|---|---|---|
| 1 | Interview scheduled for unavailable interviewer | Pick a `Scheduled`/`Completed` Interview; rewrite its `scheduled_start/end` to fall outside all of that interviewer's `InterviewerAvailabilitySlot` windows, or to overlap another booked Interview for the same interviewer | 15 / 3 | 15 / 3 | `Interview` |
| 2 | Duplicate candidate application | For an existing `Application`, insert one extra `ApplicationSubmissionAttempt` for the same `(candidate_id, requisition_id)` with a later `submitted_at`, `is_canonical=false`, `duplicate_of_attempt_id` → the original attempt, `issue_type` left for the detector to (re)compute, `ground_truth_label_id` → the new `AnomalyLabel` row | 15 / 3 | 15 / 3 (the extra attempt only — no `Application` row is added or mutated) | `ApplicationSubmissionAttempt` |
| 3 | Missing feedback but stage advanced | Pick an `Application` at stage `Offer`/`Hired`; delete the `Feedback` row for one of its `Completed` interviews | 10 / 2 | 10 / 2 | `Application` (via its `Interview`) |
| 4 | Offer salary outside approved band | Pick an `Offer`; rewrite `proposed_salary` to fall outside `[salary_min, salary_max]` by a random 5–20% margin | 6 / 1 | 6 / 1 | `Offer` |
| 5 | Closed requisition with active applications | Pick a `JobRequisition`; force `status = Closed` while exactly 2 (A-12) of its `Application` rows remain in a non-terminal stage | 5 / 1 | 10 / 2 (2 applications per incident) | `JobRequisition` + `Application` |

**Total `AnomalyLabel` rows:** full = 15+15+10+6+10 = **56**. Starter = 3+3+2+1+2 =
**11**. (Rev 1 reported 81/full under a model where duplicate applications produced
two flagged `Application` rows per incident; that model is retired — see
`entity_relationships.md` §5.)

Every injected row gets exactly one `AnomalyLabel` row, except type 5, which gets one
`AnomalyLabel` row *per affected Application* (so a 5-incident, 2-application-each
anomaly produces 10 label rows, each with `entity_type=Application`, `entity_id` =
the specific still-active application (distinct per label), `related_entity_id` =
the closed requisition (the same value, repeated across both of one incident's
labels — context, not the matching key) — **flipped this pass**, `data_dictionary.md`
§16, so `entity_id` is uniformly the evaluation/matching key across all five anomaly
types; see §9b below for the four-number distinction this enables). The injector
never touches the same source row for two different anomaly types, so the five
counts are independent and auditable.

### 9b. Closed-requisition anomaly: four distinct numbers (new, this pass)

Four different things have been, at various points, loosely called "the count" for
this anomaly type. Stated precisely and simultaneously, so none are conflated:

| What is being counted | Full | Starter |
|---|---|---|
| **Incidents** — one `JobRequisition` deliberately forced `Closed` while active applications remain | 5 | 1 |
| **Affected `JobRequisition` records** — one per incident (A-12 doesn't allow more than one requisition per incident) | 5 | 1 |
| **Affected `Application` records** — exactly 2 per incident (A-12) | 10 | 2 |
| **Evaluation units / `AnomalyLabel` rows** — one per affected `Application`, via `entity_id` | 10 | 2 |

**The `JobRequisition` is the incident's context, not a separately-labelled
evaluation target.** It appears exactly once per incident as `related_entity_id` on
each of that incident's labels (repeated, not counted again), and it is never the
value of `entity_id` for this anomaly type (confirmed by the flip above). The
detector (`validation_strategy.md` §12) and the matching-key table
(`validation_strategy.md` §22) both key exclusively on `Application.application_id`
for this type — there is no code path, detection rule, or evaluation step that
matches on `JobRequisition.requisition_id` for `ClosedReqActiveApplications`.

### 9a. `AnomalyLabel` granularity table (new, this pass — resolves the 51-vs-56 arithmetic question)

Naively summing the five **incident** counts gives 15+15+10+6+5=**51** (full) /
3+3+2+1+1=**10** (starter) — this is correct as an incident count, but it is not
the same number as the `AnomalyLabel` row count, because **granularity is
per-affected-entity, not per-incident**, and those coincide 1:1 for four of the five
types but not the fifth:

| Anomaly category | Incident count (full/starter) | Affected-entity count (full/starter) | `AnomalyLabel` row count (full/starter) | Labelled entity type(s) | Label ID reference |
|---|---|---|---|---|---|
| 1. Interviewer unavailable | 15/3 | 15/3 `Interview` rows | 15/3 | `Interview` | Illustrative only — no data has been generated; IDs would be assigned sequentially in generation order (e.g. a contiguous `ANOM-00xx` range), not these specific numbers |
| 2. Duplicate application | 15/3 | 15/3 `ApplicationSubmissionAttempt` rows | 15/3 | `ApplicationSubmissionAttempt` | Illustrative only, same caveat |
| 3. Missing feedback | 10/2 | 10/2 `Application` rows | 10/2 | `Application` (primary); `related_entity_id` = the specific `Interview` lacking `Feedback` | Illustrative only, same caveat |
| 4. Salary out of band | 6/1 | 6/1 `Offer` rows | 6/1 | `Offer` | Illustrative only, same caveat |
| 5. Closed req, active apps | 5/1 | **10/2** `Application` rows (2 per incident, A-12) | **10/2** | `Application` (`entity_id`, distinct per label — **flipped this pass**, §9b) + `JobRequisition` (`related_entity_id`, repeated across the incident's labels — context only) | Illustrative only, same caveat |
| **Total** | **51/10** | — | **56/11** | — | — |

**The extra 5 (full) / 1 (starter) arise entirely from type 5:** 5 incidents × 2
affected `Application` rows each = 10 labels, not 5; 10 − 5 = **5** extra (full).
Starter: 1 incident × 2 = 2 labels, not 1; 2 − 1 = **1** extra (starter). No other
category contributes any discrepancy — their incident count and label count are
identical by construction (one affected entity per incident).

**One incident legitimately producing multiple labels:** confirmed, and type 5 is
the only case where it happens. This is not an inconsistency to fix — it is the
documented, intentional granularity rule (A-12): `AnomalyLabel` is scoped to
*affected entities*, and a closed-requisition incident is defined (A-12) to leave
exactly 2 `Application` rows active, so it has 2 affected entities by design.
**Counts were not adjusted to make arithmetic agree** — 56/11 was already the
correct number under this granularity rule before this pass; this section makes
the rule explicit rather than leaving it as something a reader had to infer from
one sentence above.

**Scope of the "no overlap" guarantee (clarified, this pass):** this is a row-level
guarantee — the same specific row (a given `Interview`, `ApplicationSubmissionAttempt`,
`Application`, `Offer`, or `JobRequisition`) is never the target of two different
injectors. It is *not* a broader entity-group guarantee: nothing prevents, say, a
`JobRequisition` chosen for the type-5 closed-requisition anomaly from also
(independently, by chance) having one of its `Application` rows be the subject of a
type-3 missing-feedback anomaly. This is benign — the two mutations target different
rows and don't corrupt or interact with each other — but it is a real, narrower scope
than "these five categories never touch related data," so it's stated precisely here
rather than left to be assumed.

## 10. Duplicate-submission detection algorithm (new in Rev 2)

This is the concrete logic behind `ApplicationSubmissionAttempt.issue_type`, and it is
written and tested with **zero access** to `ground_truth_label_id`:

```
for each (candidate_id, requisition_id) group in ApplicationSubmissionAttempt:
    sort the group's attempts by (submitted_at, attempt_id) ascending   # deterministic
    first_attempt.is_canonical = True                                   # tie-break,
    first_attempt.issue_type = "None"                                   # clarified
    first_attempt.duplicate_of_attempt_id = None                        # this pass
    for every later attempt in the group:
        attempt.is_canonical = False
        attempt.issue_type = "DuplicateSubmission"
        attempt.duplicate_of_attempt_id = first_attempt.attempt_id
```

**Tie-break rule (clarified, this pass):** the sort key is the pair `(submitted_at,
attempt_id)`, not `submitted_at` alone — `attempt_id` is unique and assigned
sequentially in generation order, so two attempts can never tie on the full key, and
"which attempt is canonical" is never ambiguous or dependent on an unstable sort.

**This algorithm is not detection-only — it is the write path too (corrected, this
pass):** `services/application_submission.py` calls this exact function, inside one
transaction, every time a new attempt is inserted for a pair, re-deriving
`is_canonical`/`duplicate_of_attempt_id`/`issue_type` for *every* attempt on file for
that pair, not just the new one. This is what correctly handles an attempt that
arrives later in processing order but carries an earlier `submitted_at` than the
attempt currently flagged canonical — the earlier one wins, regardless of arrival
order, because the algorithm never trusts "whichever was inserted first," only the
stored `submitted_at`/`attempt_id` values. Full enforcement detail (partial unique
index, check constraint, concurrency note): `data_dictionary.md` §8a.

This is pure structural analysis — it only needs `attempt_id`, `candidate_id`,
`requisition_id`, and `submitted_at`. The function's parameter type (a narrow DTO or a
`SELECT` that never includes `ground_truth_label_id`) makes it impossible to
accidentally read the seeded label while computing `issue_type` — this is the "detect
independently of ground truth" requirement enforced structurally, not just by
convention, mirroring how `AnomalyLabel` isolation is enforced elsewhere
(architecture.md §5).

**Evaluation (offline, separate step, unchanged in spirit from Rev 1):** a distinct
script compares every attempt's computed `issue_type` against whether it has a
non-null `ground_truth_label_id`, reporting precision/recall. In this synthetic
dataset the two should always agree (the generator's injected duplicates are exactly
the "later attempt in a group" case the algorithm above is designed to catch); a
mismatch during development indicates a generator or detector bug, not an expected
outcome, and is asserted against in `test_business_rules.py`.

### 10a. Ground-truth non-leakage — confirmed scope (this pass)

`ground_truth_label_id` (on `ApplicationSubmissionAttempt` only — no other table has
an equivalent field) is confirmed to be **exclusively** an evaluation/audit pointer.
Concretely, none of the following ever read it, read `AnomalyLabel`, or are passed it
as an argument: the screening formula (§5), the scheduling-conflict check, the
feedback-requirement check, the offer-approval/salary-band checks, any lifecycle
transition in `services/`, and — specifically, since it sits on the same table —
the duplicate-submission detector itself (§10 above). `ScreeningRun` and
`Application` carry no ground-truth pointer of any kind; screening is structurally
unrelated to anomaly ground truth, not merely uninterested in it. The concrete,
generalized test that enforces this for every module (not just the duplicate
detector) is specified in `validation_strategy.md` §17. Indirect (non-direct-
reference) leakage channels are explicitly assessed in `validation_strategy.md`
§23 — none currently exploited; one named boundary of the guarantee's scope.

## 11. SystemActor role-per-transition convention (revised, this pass — hard/soft split)

Per A-14 (revised): the two transitions the brief explicitly names "approvals" are
now **hard-enforced** at the service layer (the action is rejected if the actor's role
doesn't match); every other row below remains a **soft**, reported-only convention —
the validator flags a mismatch as a finding, but the service layer permits the
transition regardless.

| Transition table | Transition | Expected role(s) | Enforcement |
|---|---|---|---|
| RequisitionStatusHistory | Draft→PendingApproval | BUSINESS_REQUESTER | Soft |
| RequisitionStatusHistory | **PendingApproval→Approved** | **APPROVER** | **Hard** |
| RequisitionStatusHistory | Approved→Open, Open↔OnHold, Open→Closed | PROCESS_OWNER | Soft |
| RequisitionStatusHistory | *→Cancelled | APPROVER or PROCESS_OWNER | Soft |
| ApplicationStageHistory | any stage transition | PROCESS_OWNER | Soft |
| OfferStatusHistory | Drafted→PendingApproval, Approved→Extended, Extended→Accepted/Declined | PROCESS_OWNER | Soft |
| OfferStatusHistory | **PendingApproval→Approved** | **APPROVER** | **Hard** |
| OfferStatusHistory | Approved/Extended→Rescinded | APPROVER | Soft |
| OfferStatusHistory | Extended→Expired | SYSTEM_ADMINISTRATOR (automatic, no human approval) | Soft |
| Offer.approved_by_actor_id | (field, not a transition) | **APPROVER** | **Hard** (same gate as the OfferStatusHistory row above — one check, two places it's visible) |
| JobRequisition.requested_by_actor_id | (field, not a transition) | BUSINESS_REQUESTER | Soft |
| GenerationRun.generated_by_actor_id | (field, not a transition) | SYSTEM_ADMINISTRATOR | Soft |

Why only these two: "approvals" is a named mandated capability (brief capabilities 1
and 9 — "job requisitions **and approvals**", "offer creation **and approvals**"), so
a role mismatch there is a correctness/compliance issue. Every other row is routine
workflow sequencing where no requirement asked for access control, and hard-blocking
it would add rigidity the brief never requested in a system that has no
authentication to back such a check with real identity verification. A **hard**
check means `services/requisition_lifecycle.py`/`services/offer_lifecycle.py` reject
the call (service-layer error, no row written) if the actor's role doesn't match;
`validation/rules/role_appropriateness.py` still re-checks both defensively at
`severity: "violation"` (not `"warning"`) as belt-and-suspenders — a hit there in the
generated dataset would mean the service-layer gate was bypassed, which should never
happen, not an expected finding. Every **soft** row keeps `severity: "warning"`,
unchanged from before. Full severity rationale: `validation_strategy.md` §14.

`OPERATIONS_ANALYST` intentionally has no row in this table — see
`data_dictionary.md` §18 and `workflow.md` §6 for its role as the exception-detection
persona, not a lifecycle participant.

**Feedback submission is not in this table.** It is gated by a structural,
already-hard FK-equality check — `Feedback.interviewer_id` must equal
`Interview.interviewer_id` (`data_dictionary.md` §13) — not by a `SystemActor` role,
because interview feedback is authored by an `Interviewer`, a deliberately separate
entity from `SystemActor` (`entity_relationships.md` §4). There is nothing to add
here; this note exists only to make the omission explicit rather than silent.

## 12. Reconciliation rules (brief §6, "reconciliation of generated records") — corrected in Rev 2, extended this pass

After generation, a reconciliation pass asserts:
- Row count per table exactly matches the targets in §1/PROJECT_SPEC §5 (or the starter
  equivalents), including the corrected `ApplicationSubmissionAttempt` (3,015/153) and
  `AnomalyLabel` (56/11) totals.
- Every FK column resolves to an existing row (no orphans) — checked independently by
  the FK-integrity validator; disagreement between that and reconciliation is a
  generator defect, not an acceptable anomaly.
- Every `Application` has exactly one `ApplicationSubmissionAttempt` with
  `is_canonical=true`, and the count of canonical attempts exactly equals the
  `Application` row count (3,000/150).
- Every `Application` has exactly one `ScreeningRun` with `is_latest=true`, the
  `ScreeningRun` row count equals the `Application` row count (3,000/150, since
  screening runs exactly once per application in this dataset — `business_rules.md`
  §5), and `Application.latest_screening_run_id` plus its eight mirrored columns match
  that `is_latest=true` row exactly.
- **New, this pass:** every `ScreeningRun.screening_rule_id` resolves to an existing
  `ScreeningRule` row (FK integrity, already covered generically by that check, called
  out here because it's new this pass); every `JobRequisition` that has ever had a
  `ScreeningRule` has exactly one `is_current=true` row (`ScreeningRule` row count is
  ~100/10 — unchanged, since the dataset never exercises redefinition); and the two
  new partial unique indexes (`uq_attempt_canonical`, `uq_screeningrun_latest`,
  `data_dictionary.md` §8a/§8b) plus `uq_screeningrule_current` (§9) report zero
  violations.
- `AnomalyLabel` row count matches the §9 table exactly: 56 at full scale (11 at
  starter scale) — not 81, correcting Rev 1.
- Re-running the generator with the same seed and mode produces byte-identical exports
  (verified by comparing `GenerationRun.overall_checksum` across two runs), now across
  **22** tables.

## 13. Confirmed generation-and-verification pipeline (new, this pass)

The exact sequence, as confirmed in this review round:

```
1. Generate valid baseline data
   (architecture.md §4's full generation order, through Offer/ScreeningRun —
   no anomalies yet)
        │
        ▼
2. Validate baseline structural integrity
   (run all 16 rule categories — VAL-01 through VAL-16, validation_strategy.md §21
   — against the just-generated baseline — EVERY category must report ZERO
   violations here)
        │
        ▼
   [GATE — concrete abort mechanism, clarified this pass]
   generator.py's entrypoint calls this validation suite synchronously and
   inspects its return value. A non-empty violation list raises an exception
   caught only at the top level, which halts the process before the
   anomaly-injection module is even imported — not a flag that could be bypassed,
   a code path that is never reached. A violation at this step means the
   generator itself is broken (not an acceptable outcome under any
   configuration), and no anomalies are ever injected on top of a broken
   baseline.
        │
        ▼ (only reached if step 2 passed with zero violations)
3. Inject labelled anomalies
   (business_rules.md §9 — each injector writes its AnomalyLabel row(s)
   inline, in the same step it mutates/adds the anomalous row, so any FK to
   AnomalyLabel — i.e. ApplicationSubmissionAttempt.ground_truth_label_id —
   resolves immediately; architecture.md §4). Structural integrity (VAL-01,
   VAL-02, and every partial unique index) is re-asserted to still hold —
   no injector is permitted to violate it; only the five business-rule
   categories (VAL-06/08/10/11/12) are expected to change.
        │
        ▼
4. Run business-rule anomaly detection, independently of ground truth
   (the same 16 validation/detection modules from step 2, run again — this
   time VAL-06/08/10/11/12 are EXPECTED to report exactly their documented
   counts: 15/10/6/15/56 per business_rules.md §9 and validation_strategy.md
   §21; every other category still reports zero. None of these modules read
   AnomalyLabel or ground_truth_label_id while doing this — §10a above,
   validation_strategy.md §23 for the indirect-leakage assessment)
        │
        ▼
5. Compare detected anomalies against ground-truth labels
   (a separate, offline evaluation script — precision/recall/F1 of step 4's
   output against AnomalyLabel, formally defined in validation_strategy.md §22
   — this is the ONLY step where detection output and ground truth are brought
   together, and it is read-only/diagnostic; its result never feeds back into
   step 4's logic)
```

Steps 1–3 run once, at generation time (`data_generation/generator.py`). Step 4's
rule modules are the *same code* invoked twice in different contexts: once here at
generation time (to prove the generator worked), and again, repeatedly, whenever
`OPERATIONS_ANALYST` triggers the live validation engine against a running database
(`workflow.md` §7) — there is exactly one implementation of each rule, per
`architecture.md` §6, not a generation-time copy and a separate live copy. Step 5 is
generation-time-only; the live-trigger flow in `workflow.md` §7 describes the
equivalent "offline evaluation" comparison in that ongoing context.

### 13a. Baseline vs. post-injection table state (new, this pass)

No separate full database snapshot is taken between steps 2 and 3 — but baseline
validation *evidence* (the step-2 result) is retained, not just inferred from "the
process didn't crash." `GenerationRun` gains two fields, this pass
(`data_dictionary.md` §17): `baseline_validation_report_json` (the full VAL-01..
VAL-16 result from step 2, timestamped before step 3 runs — must show zero
violations everywhere, by construction, since step 3 is unreachable otherwise) and
`post_injection_validation_report_json` (the same 16-category result from step 4,
timestamped after step 3). **This is exactly how a reviewer distinguishes baseline
validation from post-injection detection**: two distinct, timestamped, persisted
report objects on the same `GenerationRun` row — not two different code paths, not
a inferred distinction, two actual retained artifacts.

Exact table-count effect of step 3 (full-dataset numbers; starter scales the same
way), covering every table step 3 can touch plus the three it cannot:

| Table | Immediately after baseline (step 2) | Immediately after injection (step 3) | What changed |
|---|---|---|---|
| `JobRequisition` | 100 | 100 | **Modified**: 5 rows' `status` forced to `Closed` (type 5) — no row added/removed |
| `Candidate` | 2,000 | 2,000 | Unchanged — no anomaly type touches `Candidate` |
| `Application` | 3,000 | 3,000 | **Modified**: 10 rows' `stage` left non-terminal under a now-`Closed` requisition (type 5, the 2-per-incident rows) — no row added/removed. (Type 3's effect is on `Feedback`, not `Application`, below) |
| `ApplicationSubmissionAttempt` | 3,000 (one canonical attempt per `Application`) | **3,015** | **Added**: 15 new rows (type 2) — the only anomaly type that adds rows anywhere |
| `Interview` | 600 | 600 | **Modified**: 15 rows' `scheduled_start`/`scheduled_end` rewritten (type 1) — no row added/removed |
| `Feedback` | One row for every `Completed` interview (baseline is fully consistent — zero violations means zero missing feedback at this point); exact count not independently fixed by the brief, since it's a derived subset of the 600 `Interview` rows' outcomes, not a mandated volume | 10 fewer than the baseline count | **Removed**: 10 rows deleted (type 3) — the only anomaly type that removes rows |
| `Offer` | 150 | 150 | **Modified**: 6 rows' `proposed_salary` rewritten (type 4) — no row added/removed |
| `AnomalyLabel` | **0 — this table does not exist before step 3** (`architecture.md` §4: each injector writes its own label rows inline, during step 3, not before) | 56 | **Added**: 56 new rows, written inline by the five injectors during step 3 itself |

Only `ApplicationSubmissionAttempt` (+15) and `AnomalyLabel` (+56, from zero) change
row **count**; `Feedback` is the one table where rows are **removed**; every other
affected table keeps its row count and has specific rows **mutated** in place.

### 13b. Reproducibility across repeated runs, with real timestamps retained (new, this pass)

`GenerationRun` (`data_dictionary.md` §17) deliberately mixes two kinds of field on
one row: **volatile execution metadata** (`run_id`, `generated_at`, and the nested
`checked_at`-style timestamps inside both validation-report JSON fields) and
**deterministic dataset content** (`seed`, `mode`, `generator_version`,
`entity_counts_json`, `table_checksums_json`, `overall_checksum`, and the *results*
portion of both report JSON fields). This is not a contradiction of "repeated runs
produce identical checksums" — it is what makes that claim precisely true rather
than trivially false:

- `table_checksums_json`/`overall_checksum` are computed over the **21 operational
  content tables** — every table except `GenerationRun` itself.
  `GenerationRun`'s own row is excluded, because it is, by definition, the record
  of one specific execution (a new `run_id`, the real `generated_at`) — checksumming
  it would make "identical checksums across repeated runs" false for reasons that
  have nothing to do with the dataset actually differing.
- Two runs with the same `seed`, `mode`, and `generator_version` are expected to
  produce: different `run_id`/`generated_at` (always, by design — these are
  per-invocation identifiers, not dataset content); identical `entity_counts_json`,
  `table_checksums_json`, `overall_checksum`; and identical *results* within both
  validation-report JSON fields (zero violations at baseline; the documented
  non-zero counts post-injection) even though those fields' `checked_at` timestamps
  will differ.
- If `generator_version` differs between two runs (the code itself changed), the
  content checksums are *allowed* to differ too — that's a legitimate, expected
  outcome of a code change, not a reproducibility failure. `generator_version`
  existing as its own field is what lets a reviewer tell "the code changed" apart
  from "the same code produced a different result," which would be a real defect.

This is a documentation clarification only — no table was added (`generator_version`
is a new *field* on the already-approved `GenerationRun` table), and no anomaly
count or checksum *algorithm* changed.
