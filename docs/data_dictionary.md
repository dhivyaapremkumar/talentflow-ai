# Data Dictionary

**Revision 2, second verification pass** — incorporates: `SystemActor` (replacing
free-text actor fields), the derived `Application` PK with
`ApplicationSubmissionAttempt`, explainable screening fields on `Application` backed
by a dedicated `ScreeningRun` table (§8b, resolves A-16), and `version` on
`ScreeningRule`. **22 tables total** — see `entity_relationships.md` §1 for the full
inventory and why each one exists.

**Withdrawal/resubmission policy pass** — clarifies, in §8/§8a, that
`Application.stage` and `ApplicationSubmissionAttempt`'s canonical-reconciliation
fields are read/written by entirely disjoint code paths — no field or constraint was
added or changed; see `business_rules.md` §3a for the policy this clarifies.

**Screening/decision logic verification pass** — adds `education_weight_pct` to
`ScreeningRule` (§9) and `screening_education_component` to `ScreeningRun` (§8b) and
`Application` (§8), adopting the three-weight scoring model; no table added or
removed. See `business_rules.md` §5/§5a.

**Final approval pass** — §9 marks the three-weight model APPROVED with explicit
default values (50/30/20 weights, `pass_threshold_score=70.0`) and states both
zero-division safety guarantees inline.

**Prompt 5 correction pass** — §17 adds
`baseline_validation_report_json`/`post_injection_validation_report_json` to
`GenerationRun`, so baseline validation evidence is retained and reproducible, not
merely inferred. No table added or removed.

**Prompt 5 final clarification pass (this revision)** — §16 flips
`ClosedReqActiveApplications`'s `entity_type` from `JobRequisition` to
`Application` (removing a now-dead `JobRequisition` enum value), so `entity_id` is
uniformly the evaluation/matching key across all five anomaly types; §17 adds
`generator_version` and explicitly separates volatile execution metadata
(`run_id`, `generated_at`, nested report timestamps) from deterministic content
(`seed`, `mode`, `generator_version`, the checksum fields, the two report JSONs'
*results* portions). Anomaly counts, row counts, and the 22-table inventory are
unchanged.

Conventions used in every table below:
- **ID format**: all primary keys are deterministic, zero-padded, prefixed strings. All
  but one are assigned sequentially in generation order (see `architecture.md` §4) —
  never DB autoincrement integers. The one exception is `Application.application_id`,
  which is **derived** from its two parent IDs rather than counted — see §8 below. This
  is what makes exports byte-reproducible across runs.
- **Required** = `Y` (NOT NULL) or `N` (nullable).
- Enum values are the exact strings stored (case-sensitive); the API and frontend never
  invent alternate spellings.
- "Effective dates" are called out per field where a field's meaning depends on time
  (e.g., a salary band that was true *at approval time*, not necessarily today).

---

## 1. Department

Fixed catalog size (A-13): 10 rows, identical in starter and full datasets.

| Field | Type | Req | Allowed values / Units | Unique | Validation rule |
|---|---|---|---|---|---|
| department_id | string, `DEPT-0001` | Y | — | PK | Must match `DEPT-\d{4}` |
| name | string(80) | Y | free text | Y | Non-empty, trimmed |
| cost_center_code | string(10) | Y | free text | Y | Non-empty |
| created_at | datetime (UTC) | Y | ISO-8601 | — | ≤ now |

Cardinality: 1 Department → N JobRequisition. 1 Department → N Interviewer. 1
Department → N SystemActor (an actor's "home department," nullable for
`SYSTEM_ADMINISTRATOR`/`OPERATIONS_ANALYST` roles that are org-wide — see §9).

---

## 2. JobRequisition

| Field | Type | Req | Allowed values / Units | Unique | Validation rule |
|---|---|---|---|---|---|
| requisition_id | string, `REQ-00001` | Y | — | PK | `REQ-\d{5}` |
| department_id | FK → Department | Y | — | — | Must exist |
| title | string(120) | Y | free text | — | Non-empty |
| level | enum | Y | `Junior, Mid, Senior, Lead, Principal` | — | — |
| employment_type | enum | Y | `FullTime, Contract, Intern` | — | — |
| status | enum | Y | `Draft, PendingApproval, Approved, Open, OnHold, Closed, Cancelled` | — | See `business_rules.md` §2 for the transition graph |
| salary_min | integer | Y | USD, annual | — | ≥ 0, ≤ salary_max |
| salary_max | integer | Y | USD, annual | — | ≥ salary_min |
| headcount | integer | Y | count | — | ≥ 1 |
| requested_by_actor_id | FK → SystemActor | Y | — | — | **Changed in Rev 2** (was `hiring_manager_name` free text, A-4). Must exist; expected role `BUSINESS_REQUESTER` (soft check, A-14) |
| opened_at | date | N | — | — | Required once status ∈ {Open, OnHold, Closed}; ≥ approved_at (via history) |
| target_close_date | date | N | — | — | If present, ≥ opened_at |
| closed_at | date | N | — | — | Required iff status ∈ {Closed, Cancelled}; ≥ opened_at |
| created_at | datetime | Y | — | — | ≤ now |

Cardinality: 1 JobRequisition → N Application. 1 JobRequisition → N JobRequisitionSkill
(M:N with Skill). 1 JobRequisition → N ScreeningRule over time, exactly one
`is_current=true` (**changed, this pass** — was strict 1:1; see `data_dictionary.md`
§9). 1 JobRequisition → N RequisitionStatusHistory. 1 SystemActor → N JobRequisition
(via `requested_by_actor_id`).

Effective dates: `salary_min`/`salary_max` are the band **as approved**; if a requisition
is re-approved with a different band, that is a new `RequisitionStatusHistory` row, and
Offer validation always checks against the requisition's **current** band fields (bands
are not versioned separately — see `business_rules.md` §7 limitation).

---

## 3. Skill

Fixed catalog size (A-13): 40 rows, identical in starter and full datasets.

| Field | Type | Req | Allowed values / Units | Unique | Validation rule |
|---|---|---|---|---|---|
| skill_id | string, `SKL-0001` | Y | — | PK | `SKL-\d{4}` |
| name | string(60) | Y | free text | Y | Non-empty |
| category | enum | Y | `Technical, Tool, Domain, Soft` | — | — |
| is_active | boolean | Y | — | — | default true |

---

## 4. JobRequisitionSkill (bridge — supports mandated capability "Departments and required skills", see A-1)

| Field | Type | Req | Allowed values / Units | Unique | Validation rule |
|---|---|---|---|---|---|
| requisition_id | FK → JobRequisition | Y | — | PK (composite with skill_id) | Must exist |
| skill_id | FK → Skill | Y | — | PK (composite) | Must exist |
| min_proficiency_level | enum | Y | `Beginner, Intermediate, Advanced, Expert` | — | — |
| is_mandatory | boolean | Y | — | — | — |
| weight_pct | integer | Y | 0–100 | — | Sum of `weight_pct` across a requisition's skills = 100 |

---

## 5. Candidate

Deliberately excludes demographic fields — see PROJECT_SPEC A-9 and `business_rules.md` §8.

| Field | Type | Req | Allowed values / Units | Unique | Validation rule |
|---|---|---|---|---|---|
| candidate_id | string, `CAND-000001` | Y | — | PK | `CAND-\d{6}` |
| full_name | string(100) | Y | free text (Faker) | — | Non-empty |
| email | string(120) | Y | RFC 5322-ish | Y | Non-empty, contains `@` |
| phone | string(20) | N | free text | — | — |
| location_city | string(60) | Y | free text | — | Non-empty |
| location_country | string(60) | Y | free text | — | Non-empty |
| years_experience | decimal(4,1) | Y | years | — | ≥ 0, ≤ 50 |
| highest_education_level | enum | Y | `HighSchool, Associate, Bachelor, Master, Doctorate` | — | — |
| source_channel | enum | Y | `Referral, Website, LinkedIn, Agency, JobBoard` | — | — |
| created_at | datetime | Y | — | — | ≤ now |

Cardinality: 1 Candidate → N Application. 1 Candidate → N ResumeArtifact. 1 Candidate →
N CandidateSkill (M:N with Skill). 1 Candidate → N ApplicationSubmissionAttempt. No
lifecycle state on Candidate itself — a candidate's progress is tracked per-Application
(one person can be mid-pipeline on one req and rejected on another simultaneously).

---

## 6. ResumeArtifact

| Field | Type | Req | Allowed values / Units | Unique | Validation rule |
|---|---|---|---|---|---|
| resume_artifact_id | string, `RES-000001` | Y | — | PK | `RES-\d{6}` |
| candidate_id | FK → Candidate | Y | — | — | Must exist |
| file_name | string(120) | Y | free text, synthetic | — | Non-empty |
| file_format | enum | Y | `PDF, DOCX` | — | — |
| parsed_years_experience | decimal(4,1) | Y | years | — | ≥ 0; should match Candidate.years_experience at generation time |
| parsed_education_level | enum | Y | same enum as Candidate.highest_education_level | — | — |
| is_latest | boolean | Y | — | — | Exactly one `is_latest=true` per candidate |
| uploaded_at | datetime | Y | — | — | ≥ Candidate.created_at |

Cardinality: 1 Candidate → N ResumeArtifact (a candidate may re-upload between
applications). 1 ResumeArtifact → N Application (an application references the resume
version used at submission time).

---

## 7. CandidateSkill (bridge — one of the 12 mandated entities; not a 13th table, see PROJECT_SPEC §4)

| Field | Type | Req | Allowed values / Units | Unique | Validation rule |
|---|---|---|---|---|---|
| candidate_id | FK → Candidate | Y | — | PK (composite with skill_id) | Must exist |
| skill_id | FK → Skill | Y | — | PK (composite) | Must exist |
| proficiency_level | enum | Y | `Beginner, Intermediate, Advanced, Expert` | — | — |
| years_of_experience | decimal(4,1) | Y | years | — | ≤ Candidate.years_experience |
| source | enum | Y | `ResumeParsed, SelfReported` | — | — |
| updated_at | datetime | Y | — | — | ≥ Candidate.created_at |

---

## 8. Application — revised ID scheme and explainable screening (Rev 2)

| Field | Type | Req | Allowed values / Units | Unique | Validation rule |
|---|---|---|---|---|---|
| application_id | string, derived | Y | `APP-<requisition_id>-<candidate_id>`, e.g. `APP-REQ-00001-CAND-000042` (A-15) | PK | Deterministically computed, never counted; matches `^APP-REQ-\d{5}-CAND-\d{6}$`; see "ID derivation" below |
| candidate_id | FK → Candidate | Y | — | — | Must exist; must equal the candidate_id encoded in application_id |
| requisition_id | FK → JobRequisition | Y | — | — | Must exist; must equal the requisition_id encoded in application_id |
| resume_artifact_id | FK → ResumeArtifact | Y | — | — | Must belong to the same candidate_id |
| applied_at | datetime | Y | — | — | = the canonical `ApplicationSubmissionAttempt.submitted_at` for this pair (§ new table below); ≥ Candidate.created_at and ≥ JobRequisition.opened_at |
| source_channel | enum | Y | same enum as Candidate.source_channel | — | — |
| stage | enum | Y | `Applied, Screening, Interviewing, Offer, Hired, Rejected, Withdrawn` | — | See transition graph, `business_rules.md` §3. **Clarified, this pass:** `stage` is never read or written by `ApplicationSubmissionAttempt`'s canonical-reconciliation logic (§8a) — a resubmission for a `Withdrawn` pair records a new attempt but never changes `stage`; see `business_rules.md` §3a (Option A, approved) |
| screening_score | decimal(5,2) | N | 0–100 | — | **Current value only** — mirrors `ScreeningRun.screening_score` of the row referenced by `latest_screening_run_id` (§8b); required once stage ≠ `Applied` |
| screening_skill_component | decimal(5,4) | N | 0–1 | — | Mirror of the latest `ScreeningRun` row — weighted skill-match fraction, see `business_rules.md` §5 |
| screening_experience_component | decimal(5,4) | N | 0–1 | — | Mirror of the latest `ScreeningRun` row — experience-match fraction |
| screening_education_component | decimal(5,4) | N | 0–1 | — | **New, this pass** — mirror of the latest `ScreeningRun` row — graded education-match fraction, capped at 1.0 once the minimum is met; see `business_rules.md` §5 |
| screening_education_gate_passed | boolean | N | — | — | Mirror of the latest `ScreeningRun` row — hard gate result, independent of score; **unchanged in effect this pass** — still the sole authority over whether `screening_decision` can be `Pass` |
| screening_decision | enum | N | `Pass, Fail` | — | Mirror of the latest `ScreeningRun` row |
| screening_rule_version | integer | N | — | — | Mirror of the latest `ScreeningRun` row — copies `ScreeningRule.version` at the time that run was computed |
| screening_computed_at | datetime | N | — | — | Mirror of the latest `ScreeningRun.computed_at`; ≥ applied_at |
| screening_explanation | string(500) | N | free text, deterministically generated | — | Mirror of the latest `ScreeningRun` row — human-readable rationale, see `business_rules.md` §5 |
| latest_screening_run_id | FK → ScreeningRun | N | — | — | **Changed, this pass** — replaces the retired `screening_history` JSON array (A-2, second revision). Null until the first screening run; must point at the `ScreeningRun` row with `is_latest=true` for this `application_id`, and the eight mirrored columns above must exactly equal that row's values — `validation_strategy.md` §5 |
| rejected_reason | string(200) | N | free text | — | Required iff stage = `Rejected` |
| withdrawn_at | datetime | N | — | — | Required iff stage = `Withdrawn`; ≥ applied_at |
| created_at | datetime | Y | — | — | = applied_at |
| updated_at | datetime | Y | — | — | ≥ created_at |

**ID derivation (replaces Rev 1's sequential `APP-\d{7}` scheme and its "not a DB
constraint" uniqueness note):** `application_id` is computed purely from
`requisition_id` and `candidate_id`, so the PK itself guarantees at most one
`Application` row can ever exist for a given pair — this is now a genuine, enforced
structural constraint, not a validation-only rule (A-10). Exactly one row exists per
pair that was ever submitted at least once. **How repeat submissions for the same pair
are handled** without ever colliding or being discarded: see §8a,
`ApplicationSubmissionAttempt`, immediately below.

Cardinality: 1 Application → N Interview. 1 Application → 0..1 Offer. 1 Application → N
ApplicationStageHistory. 1 Application → N ApplicationSubmissionAttempt. 1 Application
→ N ScreeningRun (§8b); 1 Application → 0..1 ScreeningRun via `latest_screening_run_id`.

---

## 8a. ApplicationSubmissionAttempt (new in Rev 2 — resolves the duplicate-ID conflict)

Logs every submission *event*, including the one that created the `Application` row and
any later duplicate attempts for the same pair. See `business_rules.md` §10 for the
full detection algorithm and `workflow.md` §2a for the end-to-end flow.

| Field | Type | Req | Allowed values / Units | Unique | Validation rule |
|---|---|---|---|---|---|
| attempt_id | string, `ATT-0000001` | Y | — | PK | Sequential in generation order; must match `ATT-\d{7}` |
| canonical_application_id | FK → Application | Y | — | — | Must exist — `Application` is always created before any of its attempts, so this is a true, always-resolvable FK (no circular dependency; see `architecture.md` §4) |
| candidate_id | FK → Candidate | Y | — | — | Denormalized from the parent Application for direct, join-free grouping by the detection algorithm |
| requisition_id | FK → JobRequisition | Y | — | — | Denormalized, same reason |
| submitted_at | datetime | Y | — | — | — |
| is_canonical | boolean | Y | — | — | Exactly one `true` per `canonical_application_id`, and it must be the row with the earliest `submitted_at` for that `canonical_application_id` |
| duplicate_of_attempt_id | FK → ApplicationSubmissionAttempt (self) | N | — | — | Null iff `is_canonical=true`; otherwise must point at the canonical attempt for the same `canonical_application_id` |
| issue_type | enum | Y | `None, DuplicateSubmission` | — | **Detected** value — computed by grouping attempts by `(candidate_id, requisition_id)`, ordering by `submitted_at`; the first is `None`, every later one is `DuplicateSubmission`. The detector never reads `ground_truth_label_id` (see next field) — enforced by a unit test asserting the detection function's input type has no such field at all |
| ground_truth_label_id | FK → AnomalyLabel | N | — | — | **Seeded** value — set only at generation time for the deliberately-injected duplicate attempts (§ below); exists purely for audit traceability and the offline detection-accuracy evaluation step; never consulted by the `issue_type` detector |

**Behavior when the parent `Application` is `Withdrawn` (clarified, this pass —
Option A, approved; see `business_rules.md` §3a):** a resubmission for a pair whose
`Application.stage = Withdrawn` is handled identically to a resubmission for any
other pair — a new attempt row is inserted and `reconcile_canonical()` runs over
all attempts for the pair. Neither that function nor the attempt-insert path reads
`Application.stage`, so withdrawal status has no bearing on `is_canonical`/
`duplicate_of_attempt_id`/`issue_type`, and nothing in this table's write path ever
sets `Application.stage` back to anything else. The original `Application` row is
never deleted, replaced, or duplicated for the pair, regardless of how many
resubmission attempts follow the withdrawal.

**Canonical-uniqueness enforcement (clarified, this pass):**
- **Tie-break rule:** the canonical attempt for a `(candidate_id, requisition_id)` group is the row with the smallest `(submitted_at, attempt_id)` tuple — `submitted_at` first, `attempt_id` (already unique and sequential in generation order) as the deterministic tie-breaker. No two attempts can ever tie on this composite key, so canonicality is always unambiguous, never order-of-insertion-dependent.
- **DB constraint:** a partial unique index — `CREATE UNIQUE INDEX uq_attempt_canonical ON ApplicationSubmissionAttempt(canonical_application_id) WHERE is_canonical = 1;` — makes "at most one canonical attempt per application" structurally impossible to violate, not just conventionally avoided.
- **Check constraint:** `CHECK ((is_canonical = 1 AND duplicate_of_attempt_id IS NULL) OR (is_canonical = 0 AND duplicate_of_attempt_id IS NOT NULL))` — the two fields can never disagree about which case a row is in.
- **Service validation strategy — corrected, this pass (see "Out-of-order arrival"
  below for why):** `services/application_submission.py` is the single write path,
  and it does **not** decide `is_canonical` once at insert time and leave it alone.
  On every new submission, inside one transaction: (1) idempotently ensure
  `Application` exists (`INSERT ... ON CONFLICT (application_id) DO NOTHING` — safe
  under a race, since the PK is derived and therefore identical regardless of which
  transaction gets there first); (2) insert the new `ApplicationSubmissionAttempt`
  row with placeholder flags; (3) re-run the **exact same** deterministic algorithm
  from `business_rules.md` §10 over *all* attempts now on file for the pair, and
  update every row's `is_canonical`/`duplicate_of_attempt_id`/`issue_type` to match.
  Steps (2)+(3) are the same function `validation/rules/duplicate_submissions.py`
  calls independently to recompute/verify — one implementation, two call sites,
  per `architecture.md` §6 — so the write path and the detection path can never
  disagree.
  **Out-of-order arrival:** because the recompute re-sorts by `(submitted_at,
  attempt_id)` across *all* attempts every time, an attempt that is *processed*
  later but has an *earlier* `submitted_at` than the current canonical correctly
  becomes canonical, and the previous canonical is correctly re-flagged as a
  duplicate of it — this is the one case where an existing row's `is_canonical`
  **is** updated after insert (never its `attempt_id`, `candidate_id`,
  `requisition_id`, or `submitted_at` — only the three derived flags). The partial
  unique index remains the structural backstop either way.
  **Concurrency:** SQLite serializes writers at the engine level, so two
  "simultaneous" submissions for the same pair are never actually concurrent at the
  storage layer — they're two transactions applied in *some* order, and the
  recompute above converges to the same correct result regardless of which one that
  order is. A future multi-writer database would need an explicit row-level lock on
  `(candidate_id, requisition_id)` around this transaction; documented here as the
  requirement, not implemented, since this project's stack is SQLite.

Volumes: full = 3,000 canonical attempts (one per `Application`) + 15 seeded duplicate
attempts = **3,015 rows**. Starter = 150 + 3 = **153 rows**.

**How this works alongside `Application`:** `Application` is the single
source-of-truth record for "this candidate applied to this requisition," created once,
on the first submission. `ApplicationSubmissionAttempt` is the append-only audit trail
of every attempt to do that — it never mutates `Application`, never creates a second
`Application` row, and never drops a row. A later duplicate attempt is fully preserved
(candidate_id, requisition_id, submitted_at, and its relationship to the original all
recorded) even though it produces no new business record. This is exactly "do not
create duplicate primary keys or silently discard the second submission."

---

## 8b. ScreeningRun (new, this pass — resolves A-16; see PROJECT_SPEC §5a for the option comparison)

One immutable row per screening execution. Replaces the retired `screening_history`
JSON array that previously lived on `Application` (Rev 2). Rows are only ever
inserted — never updated or deleted — which is what makes "a previous run can never
be silently overwritten" a structural guarantee rather than a coding convention.

| Field | Type | Req | Allowed values / Units | Unique | Validation rule |
|---|---|---|---|---|---|
| screening_run_id | string, `SCRUN-0000001` | Y | — | PK | `SCRUN-\d{7}` |
| application_id | FK → Application | Y | — | — | Must exist |
| screening_rule_id | FK → ScreeningRule | Y | — | — | **New, this pass (resolves the reproducibility question — see note below)** — the exact `ScreeningRule` row in effect at `computed_at`, permanently, regardless of later redefinitions |
| is_latest | boolean | Y | — | — | At most one `is_latest=true` per `application_id` (zero before the first run; exactly one after — see cardinality note below), and it must be the row with the latest `computed_at` for that `application_id` (same pattern as `ResumeArtifact.is_latest`) |
| screening_rule_version | integer | Y | — | — | Denormalized copy of `screening_rule_id`'s `ScreeningRule.version` at the time this run was computed — kept for join-free display; can never drift from `screening_rule_id` because the referenced row is insert-only (see `ScreeningRule`, §9) |
| screening_skill_component | decimal(5,4) | Y | 0–1 | — | `business_rules.md` §5 |
| screening_experience_component | decimal(5,4) | Y | 0–1 | — | `business_rules.md` §5 |
| screening_education_component | decimal(5,4) | Y | 0–1 | — | **New, this pass** — graded education-match fraction (ordinal-rank ratio, capped at 1.0); `business_rules.md` §5 |
| screening_education_gate_passed | boolean | Y | — | — | Hard eligibility result — **independent of `screening_education_component`**; `business_rules.md` §5 |
| screening_score | decimal(5,2) | Y | 0–100 | — | Now a three-term weighted sum (skill/experience/education); `business_rules.md` §5 |
| screening_decision | enum | Y | `Pass, Fail` | — | `business_rules.md` §5 |
| screening_explanation | string(500) | Y | free text, deterministically generated | — | `business_rules.md` §5 |
| computed_at | datetime | Y | — | — | ≥ `Application.applied_at` |

Volumes: in the generated dataset, screening runs exactly once per `Application` —
3,000 rows (full) / 150 rows (starter), a 1:1 shadow of the `Application` count. The
table and its `is_latest`/insert-only design support multiple runs per application
(a future re-screening workflow); the synthetic dataset simply doesn't exercise that,
same as was true of the old `screening_history` array (`business_rules.md` §5).

**Cardinality — explicit zero/one invariant (clarified, this pass):** an `Application`
has **zero** `ScreeningRun` rows before its first screening execution (consistent with
`Application.latest_screening_run_id = NULL` at creation, `workflow.md` §3) and
**exactly one** row with `is_latest=true` after screening has occurred at least once —
never more than one, and never a dangling state where rows exist but none is latest.
1 Application → N `ScreeningRun` (N ≥ 0); `Application.latest_screening_run_id` points
at the current `is_latest=true` row once N ≥ 1.

**DB constraint:** a partial unique index — `CREATE UNIQUE INDEX
uq_screeningrun_latest ON ScreeningRun(application_id) WHERE is_latest = 1;` —
structurally forbids two rows for the same application both being latest.

**Consistency procedure (clarified, this pass) — how `is_latest` and
`Application.latest_screening_run_id`/mirrored columns never drift apart:**
`services/screening.py` performs the following as **one atomic transaction**: (1) if
a prior `is_latest=true` row exists for this `application_id`, flip it to `false`
(a no-op on first screening, since none exists yet); (2) insert the new `ScreeningRun`
row with `is_latest=true`; (3) update `Application.latest_screening_run_id` and its
eight mirrored columns to match the row just inserted. Because all three steps are one
transaction, there is no window in which the partial unique index's invariant holds
but `Application`'s mirror is stale, or vice versa — a crash mid-sequence rolls back
entirely, never leaving a half-updated state. `validation/rules/screening_recompute.py`
re-checks this invariant independently (`validation_strategy.md` §5).

**Relationship to `ScreeningRule` — now a direct FK (revised, this pass):**
`ScreeningRun.screening_rule_id` points at the *exact* `ScreeningRule` row in effect
when that run was computed — not "whichever row is current now." This is what makes
historical runs reproducible even after the requisition's rule is later redefined; see
`ScreeningRule` (§9) for the immutability policy that makes the FK target permanent,
and `business_rules.md` §4 for the full reproducibility explanation. (Rev 2's prior
note here — "no direct FK, reached only indirectly via Application→JobRequisition" —
is superseded; that indirect path still exists and still resolves to the *current*
rule, but the direct FK is what's authoritative for "what this specific run used.")

**Why this doesn't reopen the "three history tables" limit:** that limit, set in the
second review round, was about status-*transition* logs
(`RequisitionStatusHistory`/`ApplicationStageHistory`/`OfferStatusHistory`, each with
a `from_status`/`to_status` pair). `ScreeningRun` has no such shape — it's a
repeatable-event-with-a-result table, the same category as `Interview`, `Feedback`,
and `ApplicationSubmissionAttempt`. See `entity_relationships.md` §4a.

---

## 9. ScreeningRule — versioned/insert-only, three-weight model (APPROVED, this pass)

| Field | Type | Req | Allowed values / Units | Unique | Validation rule |
|---|---|---|---|---|---|
| screening_rule_id | string, `SCR-0001` | Y | — | PK | `SCR-\d{4}` |
| requisition_id | FK → JobRequisition | Y | — | **Changed, this pass** — no longer globally unique (was "Y (1:1)"); see `is_current` below | Must exist |
| is_current | boolean | Y | — | — | At most one `is_current=true` per `requisition_id`; a requisition that has ever had a `ScreeningRule` has exactly one. Enforced by a partial unique index: `CREATE UNIQUE INDEX uq_screeningrule_current ON ScreeningRule(requisition_id) WHERE is_current = 1;` |
| version | integer | Y | ≥ 1 | — | No longer incremented by updating a row in place. A redefinition **inserts a new row** with `version = previous + 1`, `is_current=true`, and flips the previous row's `is_current` to `false` (same pattern as `ResumeArtifact.is_latest`/`ScreeningRun.is_latest`) — never touches the previous row's other fields |
| min_years_experience | decimal(4,1) | Y | years | — | ≥ 0. `0` is valid and means "experience is not a differentiator for this role" — `experience_component` is defined as `1.0` for every candidate in that case (`business_rules.md` §5); never a division by zero |
| min_education_level | enum | Y | same enum as Candidate.highest_education_level | — | Every enum value has ordinal rank ≥ 1, so `education_component`'s denominator can never be 0 regardless of configuration |
| skill_weight_pct | integer | Y | 0–100 | — | **Approved, this pass:** `skill_weight_pct + experience_weight_pct + education_weight_pct = 100` (was a two-term sum). Approved default: **50** |
| experience_weight_pct | integer | Y | 0–100 | — | see above. Approved default: **30** |
| education_weight_pct | integer | Y | 0–100 | — | see above. Approved default: **20** — resolves the contradiction between the prior gate-only treatment of education and the three-weight model (`business_rules.md` §5) |
| pass_threshold_score | decimal(5,2) | Y | 0–100 | — | **Default value, explicitly documented this pass: 70.0.** The generator assigns this value to every `ScreeningRule` row unless a requisition is deliberately configured otherwise; it is a per-row field, not a system-wide constant, so it remains fully configurable |
| created_at | datetime | Y | — | — | ≤ now |

**Immutability policy (new, this pass):** once a `ScreeningRule` row is inserted, none
of its scoring-criteria fields (`min_years_experience` through `pass_threshold_score`)
or `version` are ever updated — the only field any existing row can have changed is
`is_current`, flipped from `true` to `false` when a newer version is created for the
same requisition. No `UPDATE`/`DELETE` path for the criteria fields is exposed above
the ORM layer, mirroring the insert-only guarantee already used for `ScreeningRun`
(§8b). **This is what makes `ScreeningRun.screening_rule_id` a permanently reliable
historical reference** — see `business_rules.md` §4 for the full explanation of why
this resolves reproducibility.

In the generated dataset, every requisition gets exactly one `ScreeningRule` row for
its entire lifetime (`version=1`, `is_current=true` from creation to the end of
generation) — the synthetic data never exercises a redefinition, same as `ScreeningRun`
never exercises more than one run per application. The mechanism exists and is
structurally enforced regardless; it just isn't exercised by this dataset. Row count
is therefore unchanged by this revision: ~100 rows (full) / ~10 rows (starter), one per
requisition.

---

## 10. Interviewer

Fixed catalog size (A-13): 25 rows, identical in starter and full datasets.

| Field | Type | Req | Allowed values / Units | Unique | Validation rule |
|---|---|---|---|---|---|
| interviewer_id | string, `IVR-0001` | Y | — | PK | `IVR-\d{4}` |
| full_name | string(100) | Y | free text | — | Non-empty |
| email | string(120) | Y | — | Y | Contains `@` |
| department_id | FK → Department | Y | — | — | Must exist |
| title | string(80) | Y | free text | — | Non-empty |
| is_active | boolean | Y | — | — | default true |

Cardinality: 1 Interviewer → N InterviewerAvailabilitySlot. 1 Interviewer → N Interview.
1 Interviewer → N Feedback (via Interview). `Interviewer` is deliberately kept separate
from `SystemActor` — see `entity_relationships.md` §4 for why two people-like entities
coexist.

---

## 11. InterviewerAvailabilitySlot (supports mandated capability "Interviewer availability and scheduling")

| Field | Type | Req | Allowed values / Units | Unique | Validation rule |
|---|---|---|---|---|---|
| slot_id | string, `AVAIL-000001` | Y | — | PK | `AVAIL-\d{6}` |
| interviewer_id | FK → Interviewer | Y | — | — | Must exist |
| start_datetime | datetime | Y | — | — | < end_datetime |
| end_datetime | datetime | Y | — | — | > start_datetime |
| is_booked | boolean | Y | — | — | derived: true iff an Interview occupies this window |

A scheduling conflict ("interview scheduled for unavailable interviewer") exists when an
`Interview.scheduled_start/scheduled_end` for an interviewer does not fall fully inside
one of that interviewer's `InterviewerAvailabilitySlot` windows, or overlaps a window
already booked by another Interview.

---

## 12. Interview

| Field | Type | Req | Allowed values / Units | Unique | Validation rule |
|---|---|---|---|---|---|
| interview_id | string, `IVW-000001` | Y | — | PK | `IVW-\d{6}` |
| application_id | FK → Application | Y | — | — | Must exist |
| interviewer_id | FK → Interviewer | Y | — | — | Must exist |
| round_number | integer | Y | 1, 2, 3, … | — | ≥ 1, contiguous per application |
| round_type | enum | Y | `Phone, Technical, Onsite, Panel, HiringManager` | — | — |
| scheduled_start | datetime | Y | — | — | < scheduled_end; ≥ Application.screening_computed_at |
| scheduled_end | datetime | Y | — | — | > scheduled_start |
| status | enum | Y | `Scheduled, Completed, Cancelled, NoShow` | — | transition graph, `business_rules.md` §3 |
| location_mode | enum | Y | `Remote, Onsite` | — | — |
| created_at | datetime | Y | — | — | ≤ scheduled_start |
| updated_at | datetime | Y | — | — | ≥ created_at |

Cardinality: 1 Interview → 0..1 Feedback (required once status = `Completed`, see
`business_rules.md` §6).

---

## 13. Feedback

| Field | Type | Req | Allowed values / Units | Unique | Validation rule |
|---|---|---|---|---|---|
| feedback_id | string, `FBK-000001` | Y | — | PK | `FBK-\d{6}` |
| interview_id | FK → Interview | Y | — | Y (1:1) | Must exist; Interview.status must be `Completed` |
| interviewer_id | FK → Interviewer | Y | — | — | Must equal Interview.interviewer_id |
| recommendation | enum | Y | `StrongYes, Yes, No, StrongNo` | — | — |
| overall_score | integer | Y | 1–5 | — | — |
| strengths_text | string(500) | N | free text | — | — |
| concerns_text | string(500) | N | free text | — | — |
| submitted_at | datetime | Y | — | — | ≥ Interview.scheduled_end |

---

## 14. Offer

| Field | Type | Req | Allowed values / Units | Unique | Validation rule |
|---|---|---|---|---|---|
| offer_id | string, `OFR-00001` | Y | — | PK | `OFR-\d{5}` |
| application_id | FK → Application | Y | — | Y (1:1) | Must exist |
| proposed_salary | integer | Y | USD, annual | — | Checked against the application's requisition `salary_min/max` — violations flagged, not DB-blocked (see salary-band note below) |
| currency | enum | Y | `USD` (single-currency for this dataset) | — | — |
| equity_amount | integer | N | USD-equivalent annual value | — | ≥ 0 |
| status | enum | Y | `Drafted, PendingApproval, Approved, Extended, Accepted, Declined, Rescinded, Expired` | — | transition graph, `business_rules.md` §3 |
| approved_by_actor_id | FK → SystemActor | N | — | — | **Changed in Rev 2** (was `approved_by_name` free text, A-4). Required once status ∈ {Approved, Extended, Accepted}; expected role `APPROVER` (soft check, A-14) |
| approved_at | datetime | N | — | — | Required once status ∈ {Approved, Extended, Accepted} |
| extended_at | datetime | N | — | — | Required once status ∈ {Extended, Accepted, Declined}; ≥ approved_at |
| decision_at | datetime | N | — | — | Required iff status ∈ {Accepted, Declined}; ≥ extended_at |
| expiry_date | date | N | — | — | ≥ extended_at date |
| created_at | datetime | Y | — | — | ≤ now |

**Salary-band note:** "offer salary outside approved band" must be representable in the
dataset, so this is a *validation* rule (`business_rules.md` §7), not a DB `CHECK`
constraint — this never violated structural integrity to begin with (A-10 restated,
PROJECT_SPEC §9), it's a business-threshold check on an otherwise perfectly valid row.
The requisition (and therefore its band) is reached via `Offer.application_id →
Application.requisition_id → JobRequisition.salary_min/max`; `Offer` does not duplicate
the band fields itself.

---

## 15. Event-history tables (immutable, append-only, never updated/overwritten) — three tables, unchanged count from Rev 1

**Audit correction:** these three tables previously used an abbreviated 4-column
layout (Field/Type/Req/Notes) instead of the standard 6-column layout used by every
other table in this document, which meant none of them had an explicit `Unique`
marker or ID regex. Normalized below to the same 6-column schema — no field, type, or
relationship changed, only the presentation and the addition of explicit regexes.

### 15a. RequisitionStatusHistory
| Field | Type | Req | Allowed values / Units | Unique | Validation rule |
|---|---|---|---|---|---|
| history_id | string, `RQH-000001` | Y | — | PK | `RQH-\d{6}` |
| requisition_id | FK → JobRequisition | Y | — | — | Must exist |
| from_status | enum (nullable for first row) | N | same enum as JobRequisition.status | — | Null only for a requisition's very first history row |
| to_status | enum | Y | same enum as JobRequisition.status | — | Must be a legal transition from `from_status` — `business_rules.md` §2 |
| changed_at | datetime | Y | — | — | Strictly increasing per `requisition_id` |
| actor_id | FK → SystemActor | Y | — | — | **Changed in Rev 2** (was `actor_name` free text). Expected role depends on transition type — `business_rules.md` §2 and §11 |
| reason_text | string(200) | N | free text | — | — |

### 15b. ApplicationStageHistory
| Field | Type | Req | Allowed values / Units | Unique | Validation rule |
|---|---|---|---|---|---|
| history_id | string, `APH-000001` | Y | — | PK | `APH-\d{6}` |
| application_id | FK → Application | Y | — | — | Must exist |
| from_stage | enum (nullable for first row) | N | same enum as Application.stage | — | Null only for an application's very first history row |
| to_stage | enum | Y | same enum as Application.stage | — | Must be a legal transition — `business_rules.md` §3 |
| changed_at | datetime | Y | — | — | Strictly increasing per `application_id` |
| actor_id | FK → SystemActor | Y | — | — | Expected role `PROCESS_OWNER` — `business_rules.md` §11 |
| reason_text | string(200) | N | free text | — | — |

### 15c. OfferStatusHistory
| Field | Type | Req | Allowed values / Units | Unique | Validation rule |
|---|---|---|---|---|---|
| history_id | string, `OFH-000001` | Y | — | PK | `OFH-\d{6}` |
| offer_id | FK → Offer | Y | — | — | Must exist |
| from_status | enum (nullable for first row) | N | same enum as Offer.status | — | Null only for an offer's very first history row |
| to_status | enum | Y | same enum as Offer.status | — | Must be a legal transition — `business_rules.md` §3 |
| changed_at | datetime | Y | — | — | Strictly increasing per `offer_id` |
| actor_id | FK → SystemActor | Y | — | — | Expected role depends on transition — `business_rules.md` §11 |
| reason_text | string(200) | N | free text | — | — |

---

## 16. AnomalyLabel (ground truth — isolated, never a feature; see `architecture.md` §5)

| Field | Type | Req | Allowed values / Units | Unique | Validation rule |
|---|---|---|---|---|---|
| label_id | string, `ANOM-0001` | Y | — | PK | `ANOM-\d{4}` |
| entity_type | enum | Y | `Interview, ApplicationSubmissionAttempt, Application, Offer` | — | **Changed, this pass** — `JobRequisition` removed from this enum: `ClosedReqActiveApplications` now uses `entity_type=Application` (flipped from `JobRequisition`, see below), so `JobRequisition` was never actually a value any row takes. `DuplicateApplication` points at `ApplicationSubmissionAttempt` (unchanged, Rev 2) |
| entity_id | string | Y | — | — | FK by convention (not a DB FK — `entity_type` varies). **The evaluation/matching-key field for every anomaly type, uniformly** — `validation_strategy.md` §22 |
| anomaly_type | enum | Y | `UnavailableInterviewer, DuplicateApplication, MissingFeedbackStageAdvanced, SalaryOutsideBand, ClosedReqActiveApplications` | — | matches PROJECT_SPEC §6 exactly |
| related_entity_id | string | N | — | — | Supporting context, never the matching key. For `DuplicateApplication`, the canonical attempt_id. For `MissingFeedbackStageAdvanced`, the specific `Interview` lacking `Feedback`. **For `ClosedReqActiveApplications`, the closed `JobRequisition`'s id — changed, this pass (was `entity_id` before the flip below)** |
| injected_at | datetime | Y | — | — | generation-time timestamp, not a real-world event |
| description | string(200) | Y | free text | — | human-readable explanation, for audit review |

**`ClosedReqActiveApplications` entity assignment — flipped, this pass:**
`entity_type=Application`, `entity_id` = the specific still-active `Application`
(distinct per label row), `related_entity_id` = the closed `JobRequisition` (the
same value repeated across both of one incident's label rows — it's the incident's
*context*, not the thing being evaluated). This was previously the other way
around (`entity_type=JobRequisition`, `entity_id`=the requisition,
`related_entity_id`=the application) — flipped so that `entity_id` is *always* the
evaluation/matching-key field across all five anomaly types uniformly, removing a
type-5-specific exception from the matching-key table
(`validation_strategy.md` §22). Row counts are unaffected by this flip — still 10
(full) / 2 (starter) label rows for this type.

**Row counts, incidents vs. affected rows (Rev 2 correction — see PROJECT_SPEC §6):**
full = 56 rows total (15 `UnavailableInterviewer` + 15 `DuplicateApplication` + 10
`MissingFeedbackStageAdvanced` + 6 `SalaryOutsideBand` + 10 `ClosedReqActiveApplications`,
the last being 5 incidents × 2 affected applications each per A-12); starter = 11 rows
(3+3+2+1+2). This retires Rev 1's 81-row full-scale figure, which had double-counted
the duplicate-application type under the now-superseded two-Application-rows model.

**Generation-order note (audit correction):** each anomaly injector writes its
`AnomalyLabel` row(s) in the same step it creates the anomalous row, not in a later
global pass — see `architecture.md` §4. This matters specifically for
`ApplicationSubmissionAttempt.ground_truth_label_id`, which must resolve to an
already-existing `AnomalyLabel` row at the moment it's set.

## 17. GenerationRun (reproducibility manifest)

| Field | Type | Req | Allowed values / Units | Unique | Validation rule |
|---|---|---|---|---|---|
| run_id | string, `GEN-0001` | Y | — | PK | `GEN-\d{4}` — **volatile, this pass's clarification**: increments once per generator *invocation*, even when the seed and mode are identical — two runs of the same seed are still two different `GenerationRun` rows, by design, so this field is never expected to match across "repeated runs" |
| seed | integer | Y | `20261022` | — | Deterministic-content input — identical across repeated runs by definition |
| mode | enum | Y | `starter, full` | — | Deterministic-content input |
| generator_version | string(40) | Y | e.g. a semantic version or git commit SHA | — | **New, this pass** — identifies the exact generator code that produced this run. "Repeated runs with the same seed produce identical checksums" is conditioned on this also matching — a deliberate code change between two runs is expected to (and allowed to) change the checksums, and this field is what lets a reviewer tell *that* case apart from an actual non-determinism bug |
| generated_by_actor_id | FK → SystemActor | Y | — | — | expected role `SYSTEM_ADMINISTRATOR` (soft check, A-14) |
| generated_at | datetime | Y | — | — | **Volatile, this pass's clarification** — the real wall-clock time this specific invocation ran. Legitimately differs between two runs of the same seed; never expected to match, and never part of any checksum |
| entity_counts_json | text | Y | JSON map of table → row count | — | Deterministic content — row counts per table are fixed by seed+mode (`business_rules.md` §1), so this value is byte-identical across repeated runs |
| table_checksums_json | text | Y | JSON map of table → SHA-256 of its canonical CSV export | — | **Clarified, this pass**: covers the **21 operational/reference content tables** — every table except `GenerationRun` itself. `GenerationRun`'s own exported row is excluded from this map, because every `GenerationRun` row is, by definition, a record of one specific, non-repeatable execution event (see `run_id`/`generated_at` above) — it is not "dataset content" in the sense the other 21 tables are, so checksumming it would make this field spuriously non-reproducible for reasons that have nothing to do with the generator being broken |
| overall_checksum | string(64) | Y | SHA-256 of the concatenation of the 21 table checksums above, in a fixed table order | — | Deterministic content — byte-identical across repeated runs with the same seed, mode, and `generator_version` |
| baseline_validation_report_json | text | Y | — | — | The full VAL-01..VAL-16 result from pipeline step 2 (`business_rules.md` §13), timestamped *before* anomaly injection; must show zero violations across all 16 categories, since step 3 never runs otherwise (`business_rules.md` §13a). **Clarified, this pass**: this JSON object mixes a volatile `checked_at` timestamp (real execution time, excluded from any reproducibility comparison) with deterministic violation-count results (zero, in this case — expected to match across repeated runs). Comparing two runs' reports means comparing the *results* field, not diffing the JSON byte-for-byte |
| post_injection_validation_report_json | text | Y | — | — | The same 16-category result from pipeline step 4, timestamped *after* anomaly injection; VAL-06/08/10/11/12 expected to report their documented non-zero counts, the other 11 categories expected to remain zero. Same volatile-timestamp-vs-deterministic-results split as `baseline_validation_report_json` above. Comparing these two JSON fields' *results* portions is how a reviewer distinguishes baseline validation from post-injection detection — two persisted artifacts on the same row, not an inference |

**Summary — what's volatile vs. deterministic on this one row (new, this pass):**
`run_id`, `generated_at`, and the `checked_at`-style timestamps nested inside the
two report JSON fields are execution metadata — they are expected to differ across
repeated runs and are never included in any checksum. `seed`, `mode`,
`generator_version`, `entity_counts_json`, `table_checksums_json`,
`overall_checksum`, and the *results* portions of both report JSON fields are
deterministic content — expected to be byte-identical across repeated runs that
share the same `seed`, `mode`, and `generator_version`. The manifest retaining both
kinds of field on one row does not break reproducibility comparisons; it just means
"compare the deterministic fields, not the whole row" — exactly the distinction
`validation_strategy.md` §13 draws when checking this.

---

## 18. SystemActor (new in Rev 2)

Fixed catalog size (A-11): 20 rows, identical in starter and full datasets. No
authentication or password fields — this is an audit/attribution identity, not a login
account.

| Field | Type | Req | Allowed values / Units | Unique | Validation rule |
|---|---|---|---|---|---|
| actor_id | string, `ACT-0001` | Y | — | PK | `ACT-\d{4}` |
| full_name | string(100) | Y | free text (Faker) | — | Non-empty |
| role | enum | Y | `BUSINESS_REQUESTER, PROCESS_OWNER, APPROVER, OPERATIONS_ANALYST, SYSTEM_ADMINISTRATOR` | — | — |
| department_id | FK → Department | N | — | — | Required for `BUSINESS_REQUESTER`/`PROCESS_OWNER`; nullable for `APPROVER`/`OPERATIONS_ANALYST`/`SYSTEM_ADMINISTRATOR`, which are modeled as org-wide, not department-scoped |
| email | string(120) | Y | — | Y | Contains `@` |
| is_active | boolean | Y | — | — | default true |
| created_at | datetime | Y | — | — | ≤ now |

Role distribution (A-11): 8 `BUSINESS_REQUESTER`, 4 `PROCESS_OWNER`, 4 `APPROVER`, 2
`OPERATIONS_ANALYST`, 2 `SYSTEM_ADMINISTRATOR`.

Referenced by: `JobRequisition.requested_by_actor_id`,
`RequisitionStatusHistory.actor_id`, `ApplicationStageHistory.actor_id`,
`Offer.approved_by_actor_id`, `OfferStatusHistory.actor_id`,
`GenerationRun.generated_by_actor_id`. Role-appropriateness per transition is a
documented, soft-checked convention (A-14), not a hard FK-level constraint — a
`SystemActor` is not restricted by the schema from being referenced by a transition
outside their "expected" role; the validator only reports it as a finding.
`OPERATIONS_ANALYST` has no FK target on any data row by design — it is the persona
who runs the validation/reconciliation job and reviews the Anomalies dashboard (brief
capability 10), not a participant in any lifecycle transition. See `workflow.md` §6 and
`business_rules.md` §11.
