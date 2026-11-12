# TalentFlow AI — Project Specification

Status: **Draft for review — Revision 2** · Phase: Architecture (no code written yet)
Owner: Dhivyaa Premkumar · Context: YottaFlex AI Associate Forward Deployed Engineer challenge

## Revision history

- **Rev 1**: initial architecture pass (12 entities, free-text actors, sequential
  Application IDs).
- **Rev 2** (this version): incorporates the first review's decisions — `SystemActor`
  entity, revised Application ID scheme (`APP-<requisition_id>-<candidate_id>`) with a
  supporting `ApplicationSubmissionAttempt` table to resolve the duplicate-ID conflict,
  richer screening explainability on `Application`, confirmed anomaly counts with
  incidents distinguished from affected rows, and a corrected entity/table count. Every
  change and its reasoning is called out inline below; nothing from Rev 1 was dropped
  silently — where Rev 2 supersedes Rev 1 it says so.

## 1. Purpose

TalentFlow AI is a recruitment operations and decision-intelligence system. It models the
full requisition-to-offer hiring lifecycle with a relational schema, a deterministic
synthetic data generator (including labelled anomalies), a validation/reconciliation
engine, a FastAPI backend, and a React analytics frontend.

This document is the canonical restatement of requirements, with every resolved
ambiguity written down explicitly as an **Assumption (A-n)**. Where this document and the
original prompt disagree, this document wins unless the user corrects it — nothing here
silently changes scope, it only fills gaps the original prompt left open.

## 2. Scope

In scope:
- 12 mandated core entities + required bridge/supporting tables + immutable
  event-history tables (22 tables total — see §4 and `entity_relationships.md` §1)
- Deterministic synthetic data generation at starter and full scale, seed `20261022`
- Five labelled anomaly types, ground truth stored separately from operational data,
  with incident counts kept distinct from affected-row counts (§6)
- A validation and reconciliation engine covering the 13 rule categories in §7, which
  never reads ground truth, and which detects business-rule anomalies without ever
  requiring the database to hold a structurally invalid row (A-10)
- CRUD + lifecycle-transition REST API (FastAPI)
- Analytics endpoints backed by SQL/Pandas, charted with Recharts in a React/TS/Vite frontend
- CSV/JSON/SQL reproducible exports
- Pytest coverage for models, business rules, validation, and generator reproducibility

Out of scope (explicitly, to avoid scope creep):
- Authentication/authorization, password management, login sessions — `SystemActor`
  (§4) models *who did what* for audit/approval purposes only; it is not a login system
- Real resume parsing (NLP/OCR) — resumes are synthetic metadata records, not real documents
- Real-time notifications, email/calendar integration
- Any paid or external API (LLM, geocoding, enrichment, etc.)
- Multi-tenancy

## 3. Mandated business capabilities (verbatim from brief)

1. Job requisitions and approvals
2. Departments and required skills
3. Synthetic candidates and resume metadata
4. Candidate applications
5. Structured, job-related screening
6. Interviewer availability and scheduling
7. Interview rounds and structured feedback
8. Candidate stage progression
9. Offer creation and approvals
10. Exception detection and audit history

## 4. Mandated core entities (12) and the corrected total table count

The 12 mandated entities, verbatim, are unchanged from Rev 1:

`JobRequisition, Department, Candidate, Application, ResumeArtifact, Skill, CandidateSkill,
ScreeningRule, Interview, Interviewer, Feedback, Offer`

**Correction from Rev 1:** `CandidateSkill` is one of these 12 (it is the
Candidate↔Skill bridge) — it must never be listed again as if it were a 13th table.
Rev 1's entity-relationship document stated this but phrased it ambiguously; Rev 2
fixes the wording (`entity_relationships.md` §1).

Beyond the 12, this design adds **10 supporting tables**, each tied to a specific
mandated capability or review decision:

| Supporting table | Added for |
|---|---|
| `JobRequisitionSkill` | bridge required by A-1 (required skills attach to the requisition) |
| `InterviewerAvailabilitySlot` | mandated capability 6 ("interviewer availability and scheduling") — without it there is nothing for the "unavailable interviewer" anomaly to violate |
| `RequisitionStatusHistory` | mandated capability 10 (audit history) — immutable requisition state log |
| `ApplicationStageHistory` | mandated capability 10 — immutable stage log |
| `OfferStatusHistory` | mandated capability 10 — immutable offer status log |
| `AnomalyLabel` | brief §5/§6 — isolated ground truth |
| `GenerationRun` | brief §6 — deterministic reproducibility checksum manifest |
| `SystemActor` | **new in Rev 2**, A-4 — synthetic actors behind every approval/audit record |
| `ApplicationSubmissionAttempt` | **new in Rev 2** — resolves the duplicate-application-ID conflict, §5 below |
| `ScreeningRun` | **new, this pass** — resolves A-16/A-2: one immutable row per screening execution, replacing the JSON-array history mechanism; see §5a below |

**Total: 12 + 10 = 22 tables.** Full breakdown and why each one exists:
`entity_relationships.md` §1–§2.

## 5. Application identity and the duplicate-submission design (new in Rev 2)

Per review decision, `Application.application_id` is now a **deterministic, derived**
primary key: `APP-<requisition_id>-<candidate_id>` (the two referenced IDs concatenated
in full, e.g. `APP-REQ-00001-CAND-000042`), not a sequential counter. This makes the PK
itself the uniqueness guarantee for "one candidate, one requisition, one Application
row" — a second submission for the same pair can never produce a second row with a
different PK, and can never silently collide into overwriting the first row either,
because **submissions and applications are no longer the same table**.

- `Application` holds exactly one row per unique `(requisition_id, candidate_id)` pair
  that was ever submitted — 3,000 rows at full scale, as mandated.
- `ApplicationSubmissionAttempt` holds one row per **submission event**, including the
  first (canonical) submission of every pair and every subsequent duplicate attempt.
  At full scale: 3,000 canonical attempts (one per Application) + 15 extra duplicate
  attempts (the seeded anomaly, §6) = **3,015 rows**.
- No submission is ever discarded, and no PK collision is ever attempted against the
  database. Full schema and the detection algorithm: `data_dictionary.md` §8 and
  `business_rules.md` §10.

This directly satisfies the review's A-10 restatement: the database never contains a
structurally invalid row (duplicate PK, dangling FK) in order to represent an anomaly;
the anomaly is represented by a legitimate extra row in a purpose-built table, and
detected by rule logic, not by the schema bending.

## 5a. Screening history: resolved as a dedicated `ScreeningRun` table (resolves A-16)

A-16 (raised in the previous audit, left open) asked how an individual screening
execution should be addressable, since the JSON-array design gave each run no
identity beyond its position in an array. Evaluated against two options — keep JSON
and add a `screening_run_id` string inside each array element, vs. introduce a
dedicated `ScreeningRun` table — **Option B (dedicated table) is adopted.** Full
comparison: this pass's chat response; authoritative field list:
`data_dictionary.md` §8b.

- `ScreeningRun` holds one immutable row per screening execution: its own PK
  (`SCRUN-0000001`), the `application_id` it belongs to, the rule version used, every
  score component, the decision, the explanation, and `computed_at`. Rows are only
  ever inserted, never updated or deleted — this is a structural guarantee, not a
  coding convention, so a prior run can never be silently overwritten.
- `Application` keeps mirrored "current" screening fields (unchanged names:
  `screening_score`, `screening_skill_component`, `screening_experience_component`,
  `screening_education_gate_passed`, `screening_decision`, `screening_rule_version`,
  `screening_computed_at`, `screening_explanation`) for cheap reads without a join,
  plus a new `latest_screening_run_id` FK → `ScreeningRun`. The removed field is
  `screening_history` (the JSON array) — its job is now done by querying
  `ScreeningRun WHERE application_id = ...`.
- This does **not** reopen the "exactly three history tables" constraint from the
  second review round: that constraint was about status-*transition* logs
  (`from_status`/`to_status` pairs — `RequisitionStatusHistory`,
  `ApplicationStageHistory`, `OfferStatusHistory`). `ScreeningRun` has no
  from/to-status shape; it's a repeatable-event-with-a-result table, the same
  category as `Interview`, `Feedback`, and `ApplicationSubmissionAttempt` — none of
  which were ever counted against that three-table limit either.

## 6. Mandated anomaly types (5) — incidents vs. affected rows (new in Rev 2)

| # | Anomaly type | Incidents (full / starter) | Affected rows (full / starter) | Where the affected row lives |
|---|---|---|---|---|
| 1 | Interview scheduled for an unavailable interviewer | 15 / 3 | 15 / 3 | `Interview` (mutated time window) |
| 2 | Duplicate candidate application | 15 / 3 | 15 / 3 | `ApplicationSubmissionAttempt` (the extra, non-canonical attempt) |
| 3 | Missing feedback but application stage advanced | 10 / 2 | 10 / 2 | `Application` (lacks a required `Feedback` row on a `Completed` interview) |
| 4 | Offer salary outside the approved band | 6 / 1 | 6 / 1 | `Offer` (mutated `proposed_salary`) |
| 5 | Closed requisition with active applications | 5 / 1 | 10 / 2 (each incident leaves exactly 2 applications active, A-12) | `JobRequisition` + the 2 `Application` rows it wrongly still has open |

Total `AnomalyLabel` rows: full = 15+15+10+6+10 = **56**; starter = 3+3+2+1+2 = **11**.
(Rev 1 had stated 81/full using a different, since-superseded duplicate-row model —
that number is retired; see `business_rules.md` §9 for the corrected reconciliation
math.)

Ground truth remains isolated in `AnomalyLabel` and is never read by detection logic —
see `architecture.md` §5 for the mechanism, and §7 below for the one deliberate,
narrow exception the review requested.

## 7. Mandated validation categories (13)

Primary-key uniqueness · Foreign-key integrity · Allowed values/required fields ·
Date ordering · Screening score calculations · Scheduling conflicts · Lifecycle
transitions · Feedback requirements · Offer approval rules · Salary-band compliance ·
Duplicate applications · Reconciliation of generated records · Deterministic
reproducibility via checksums.

**Audit correction:** this list has always had 13 items (count them above); the
heading previously said "(12)" in every document that referenced it. That mislabel
is fixed here and in every other document that repeated it — `architecture.md` §2,
`validation_strategy.md` (intro), `workflow.md` §7, `implementation_plan.md` Phase 4.
The rule *content* was never wrong, only this count label; no validation category was
added, removed, or redefined by this fix.

Full rule-by-rule detail: `validation_strategy.md` and `business_rules.md`.

## 8. Technology stack (fixed, no substitutions)

Backend: Python 3.12, FastAPI, SQLAlchemy, Pydantic · DB: SQLite ·
Data generation: Faker + seeded `random`/`numpy` generators · Analytics: SQL + Pandas ·
Frontend: React + TypeScript + Vite, Recharts · Testing: Pytest. All dependencies are
free and run locally; no external network calls at runtime.

## 9. Assumptions requiring review

Confirmed decisions from the first review are marked **[CONFIRMED]**. Everything else
is still a proposal awaiting your sign-off, exactly as in Rev 1 unless noted.

- **A-1 — [CONFIRMED] "Departments and required skills"** → required skills attach to
  `JobRequisition` via `JobRequisitionSkill`, not to `Department`.

- **A-2 — [REVISED AGAIN, this pass] Screening results: current value on
  `Application`, full history in a dedicated `ScreeningRun` table.** `ScreeningRule`
  (1:1 with `JobRequisition`) still defines the rule. Each execution of screening
  inserts one immutable `ScreeningRun` row (score components, decision, rule version,
  explanation, `computed_at`); `Application` mirrors the latest run's values in its
  own `screening_*` columns plus a `latest_screening_run_id` FK, for cheap reads
  without a join. This supersedes the immediately-prior version of A-2 (Rev 2), which
  used a `screening_history` JSON array on `Application` instead of a real table — that
  approach is retired because it gave no queryable identity to an individual run (see
  A-16, now resolved) and had no DB-level protection against an application bug
  silently rewriting array history. Full field list: `data_dictionary.md` §8, §8b;
  comparison and rationale: §5a above.

- **A-3 — [CONFIRMED, unchanged] One interviewer per `Interview` row.** Panel
  interviews are multiple `Interview` rows sharing `application_id` +
  `round_number`, each with its own `Feedback`. No `InterviewPanel` bridge.

- **A-4 — [RESOLVED] `SystemActor` added.** Five roles:
  `BUSINESS_REQUESTER, PROCESS_OWNER, APPROVER, OPERATIONS_ANALYST,
  SYSTEM_ADMINISTRATOR`. No authentication/password fields. Every place Rev 1 used a
  free-text `actor_name` now uses a real FK to `SystemActor.actor_id`:
  `JobRequisition.requested_by_actor_id`, `RequisitionStatusHistory.actor_id`,
  `ApplicationStageHistory.actor_id`, `Offer.approved_by_actor_id`,
  `OfferStatusHistory.actor_id`, and (new) `GenerationRun.generated_by_actor_id`. Rev
  1's "you can't query who approved what by FK join" limitation is now resolved — you
  can. Full role-per-transition convention: `business_rules.md` §2–3 and §11.

- **A-5 — [CONFIRMED] Volumes are final totals, inclusive of anomalies.** Unchanged
  reasoning from Rev 1, now additionally true of `ApplicationSubmissionAttempt` (§5
  above): its 3,015 total is the canonical attempts plus the 15 seeded duplicates, not
  3,000 clean attempts with 15 bolted on separately-counted pairs.

- **A-6 — [CONFIRMED, unchanged] Starter dataset volumes**: 5% of full scale for every
  entity that scales with hiring volume (see A-13 for which entities don't scale):
  10 requisitions / 100 candidates / 150 applications / 30 interviews / 8 offers.

- **A-7 — [CONFIRMED] Anomaly injection counts**, now stated as incidents with affected
  rows distinguished per type — see §6's table above (this supersedes Rev 1's §6 table,
  which conflated the two for the duplicate-application type).

- **A-8 — [CONFIRMED, unchanged] Salary bands live on `JobRequisition`.**

- **A-9 — [CONFIRMED, unchanged] No demographic fields on `Candidate`.**

- **A-10 — [REVISED] Structural database integrity is always preserved; business-rule
  anomalies are detected by separate validation logic, never by storing a structurally
  invalid row.** This sharpens Rev 1's A-10, which allowed a soft "validation-only, not
  a DB constraint" duplicate `Application` row. That's no longer needed: because
  `Application.application_id` is now derived from `(requisition_id, candidate_id)`
  (§5), the PK constraint *itself* makes duplicate Applications structurally
  impossible, and the duplicate-submission anomaly is instead a legitimate extra row in
  `ApplicationSubmissionAttempt` — no constraint is bent anywhere. The
  offer-salary-band and closed-requisition anomalies remain business-rule-only checks
  (never a DB `CHECK` constraint), because neither of those ever violated a structural
  constraint in the first place — only a business threshold, which a structurally valid
  row is allowed to fall outside of until validation flags it.

- **A-11 — [NEW] `SystemActor` population is fixed, not scaled by dataset mode.** 20
  actors total, identical in starter and full datasets: 8 `BUSINESS_REQUESTER`, 4
  `PROCESS_OWNER`, 4 `APPROVER`, 2 `OPERATIONS_ANALYST`, 2 `SYSTEM_ADMINISTRATOR`.
  Rationale: this models an internal staff roster, which doesn't grow because the demo
  dataset is bigger — the same ~20 people process both a 100-req and a 10-req world.

- **A-12 — [NEW] Closed-requisition-with-active-applications incidents leave exactly 2
  applications active each.** Needed to make the incident-count (5 full / 1 starter)
  and affected-row-count (10 full / 2 starter) in §6 exact and reproducible rather than
  randomly variable.

- **A-13 — [NEW] Reference/catalog tables are fixed-size, independent of starter/full
  mode**: `Department` (10), `Skill` (40), `Interviewer` (25), `SystemActor` (20, per
  A-11). Rationale: these represent the org's fixed staff/taxonomy, not
  hiring-volume-dependent data — a smaller demo dataset doesn't imply fewer departments
  or a smaller interviewer panel, it implies less hiring activity flowing through the
  same org. Only `JobRequisition`, `Candidate`, `Application`,
  `ApplicationSubmissionAttempt`, `Interview`, `Offer`, and the rows directly derived
  from them (`JobRequisitionSkill`, `ResumeArtifact`, `CandidateSkill`,
  `InterviewerAvailabilitySlot`, the three history tables, `AnomalyLabel`) scale
  between starter and full.

- **A-14 — [REVISED, this pass] Role-appropriateness is hard-enforced at the service
  layer for the two transitions the brief explicitly calls "approvals"; every other
  role expectation remains a soft, reported-only convention.** Specifically:
  `JobRequisition` approval (`PendingApproval→Approved`) and `Offer` approval
  (`PendingApproval→Approved`, and the `approved_by_actor_id` field generally) require
  the referenced `SystemActor.role = APPROVER` — the service layer rejects the
  transition otherwise, and the validation engine re-checks it defensively as
  `severity: "violation"` (a hit here would mean the service-layer check was bypassed,
  not an expected finding). Every other role expectation in `business_rules.md` §11
  (who *typically* requests a requisition, progresses an application, or is attributed
  as running the generator) stays a soft, `severity: "warning"` convention — not
  hard-enforced, and not expected to be. Rationale for the split: "approvals" is a
  named mandated capability (brief capabilities 1 and 9) where a role mismatch is a
  correctness/compliance issue, not merely a data-hygiene one; the other transitions
  are routine workflow steps where hard-blocking would add rigidity no requirement
  asked for, in a system that explicitly has no authentication to back it with real
  access control. *(Feedback submission is not part of this table at all — it is
  gated by a structural FK-equality check, `Feedback.interviewer_id =
  Interview.interviewer_id`, already hard by construction and unrelated to
  `SystemActor`; see `business_rules.md` §11 note.)* Full table:
  `business_rules.md` §11.

- **A-15 — [NEW] Application ID format uses the full referenced IDs, not just their
  numeric suffixes.** `APP-<requisition_id>-<candidate_id>` is read literally as
  concatenating the complete ID strings (e.g. `APP-REQ-00001-CAND-000042`), not
  `APP-00001-000042`. This is more verbose but unambiguous and still fully
  deterministic. Flag this one specifically if a shorter numeric-only form was intended.

- **A-16 — [RESOLVED] Dedicated `screening_run_id`.** Previously open (raised in a
  clarification exchange, then formally recorded as unresolved in the prior audit).
  Resolved by adopting Option B in §5a: `ScreeningRun.screening_run_id`
  (`SCRUN-0000001`, sequential) is now a real primary key, addressable independently
  of `Application` and queryable like every other event table.

- **A-17 — [NEW, this pass] `ScreeningRule` is versioned and insert-only, with
  `ScreeningRun.screening_rule_id` as a direct FK to it.** Raised as a follow-up
  question to A-16: a direct FK from `ScreeningRun` to `ScreeningRule` only actually
  preserves history if `ScreeningRule`'s target row can never be mutated out from
  under it. Resolved by applying the same insert-only/`is_latest`-style pattern
  already used for `ResumeArtifact` and `ScreeningRun` to `ScreeningRule` itself: a
  redefinition inserts a new row (`version+1`, `is_current=true`) rather than
  updating the existing one, and `is_current` is enforced by a partial unique index.
  This changes `ScreeningRule`'s relationship to `JobRequisition` from strict 1:1 to
  "1:N over time, exactly one current" — a cardinality/constraint refinement to an
  **existing** table, not a new table; the 22-table inventory is unchanged. Full
  reproducibility explanation: `business_rules.md` §4.

- **A-18 — [CONFIRMED — Option A approved, this pass] Withdrawal does not release
  the `(candidate_id, requisition_id)` pair.** If a candidate withdraws and later
  submits again for the same requisition, no new `Application` is created and the
  original is never reopened, deleted, or replaced — the resubmission is recorded as
  an ordinary `ApplicationSubmissionAttempt` against the existing canonical
  `Application`, through the unmodified attempt-insert and canonical-reconciliation
  flow (`business_rules.md` §10). Rationale: `Application.stage` and
  `ApplicationSubmissionAttempt`'s canonical-reconciliation fields were already
  governed by disjoint code paths before this decision — neither reads nor writes
  the other — so "withdrawal doesn't reactivate, doesn't release the pair, doesn't
  require a new Application" falls out of that existing separation rather than
  requiring a new rule, field, lifecycle state, or algorithm branch. Full policy:
  `business_rules.md` §3a; flow: `workflow.md` §2b; test cases:
  `validation_strategy.md` §18.

- **A-19 — [APPROVED] Screening adopts a three-weight model: Skills 50% /
  Experience 30% / Education 20%, with education both scored and gated.** Explicitly
  user-approved, this pass — not merely proposed. Resolves a real inconsistency: the
  prior formula (A-2's lineage) weighted only skills and experience, treating
  education as pass/fail-only — an asymmetric treatment of the three dimensions.
  **Approved education policy (verbatim):**
  1. Education is both a scored component and a mandatory eligibility gate.
  2. Candidates meeting or exceeding the minimum education requirement receive full
     education component credit (1.0).
  3. Candidates failing the minimum education requirement fail the eligibility gate,
     regardless of their numerical screening score.
  4. Education scoring must not reward qualifications above the minimum requirement
     beyond full credit.
  5. The education gate cannot be overridden by skills or experience scores.

  **Rationale:** education now gets a graded `education_component`
  (`business_rules.md` §5), computed with the exact same "capped at 1.0 once the
  minimum is met" philosophy already used for `experience_component` (policy point
  4, satisfied structurally by the `min(1.0, ...)` cap — not by a separate check),
  **and** keeps its independent hard eligibility gate unchanged in effect (policy
  points 1, 3, 5) — a candidate who fails the gate is `Fail` regardless of how high
  the weighted score is (proof case: `business_rules.md` §5a, CAND-000104, score
  93.33, still `Fail`). The default `pass_threshold_score` is now explicitly
  documented as **70.0** (`data_dictionary.md` §9), configurable per
  `ScreeningRule` row. Adds `ScreeningRule.education_weight_pct` and
  `ScreeningRun`/`Application`'s `screening_education_component` — field additions
  to already-approved tables; **no table added or removed.** All five primary
  worked examples and the boundary pair in `business_rules.md` §5a were
  hand-recomputed against this exact approved formula this pass; no numerical
  corrections were required (the boundary pair's placeholder numbers were replaced
  with a fully concrete, verified pair — a presentation fix, not a formula error).

## 10. Consistency check performed (Rev 2)

Re-verified after this revision: (1) all 12 mandated entities still present and
unchanged in shape except `Application`'s screening/ID fields; (2) the corrected
21-table total (as of this revision — superseded by 22 in §11 below, once
`ScreeningRun` was added) was used identically in every doc; (3) every ID format
regex/convention
is updated everywhere it's mentioned, including the new derived `Application` PK; (4)
every FK that used to be free text now points at `SystemActor` consistently across
`data_dictionary.md`, `business_rules.md`, and `workflow.md`; (5) the `AnomalyLabel`
row-count math (56 full / 11 starter) is reproduced identically in
`business_rules.md` §9 and `validation_strategy.md`; (6) `ApplicationSubmissionAttempt`
reconciles exactly against `Application` (every `Application` has ≥1 attempt with
`is_canonical=true`, and canonical attempts = 3,000 = `Application` row count); (7)
ground-truth isolation is preserved except for the one deliberate, documented pointer
field requested in review (`ApplicationSubmissionAttempt.ground_truth_label_id`), which
the detection algorithm is contractually barred from reading — mechanism in
`business_rules.md` §10 and `validation_strategy.md` §11.

## 11. Second verification pass (this round)

Re-verified after resolving the four outstanding items from the architecture
verification: (1) the table count is now **22** (12 mandated + 10 supporting) with
`ScreeningRun` added, updated identically in every document; (2) `ScreeningRun`
carries no ground-truth pointer of any kind — screening is structurally unrelated to
anomaly ground truth, confirmed explicitly rather than merely by omission; (3) the
generation-order diagram (`architecture.md` §4) now states the full five-step
baseline→validate→inject→detect→compare pipeline, with an explicit baseline-integrity
gate before anomaly injection that didn't exist as a named step before; (4) the
ground-truth non-leakage guarantee is generalized from "the one duplicate-detection
module" to all of `services/` and `validation/rules/` (`validation_strategy.md` §17);
(5) role-appropriateness is split into two hard-enforced transitions (requisition and
offer approval) and everything else remaining soft, documented in both
`business_rules.md` §11 and this document's A-14.

## 12. Implementation-detail clarification pass (this round)

Three implementation details were pinned down, none of which changed the approved
22-table inventory: (1) `ScreeningRule` versioning/insert-only + direct
`ScreeningRun.screening_rule_id` FK, resolving historical reproducibility (A-17,
`business_rules.md` §4); (2) `ApplicationSubmissionAttempt` canonical-attempt
uniqueness pinned to a `(submitted_at, attempt_id)` tie-break, backed by a partial
unique index and a check constraint (`data_dictionary.md` §8a); (3) `ScreeningRun`'s
zero-before/one-after cardinality made explicit, backed by a partial unique index and
an atomic three-step consistency procedure with `Application`'s mirrored columns
(`data_dictionary.md` §8b). All three are field/constraint-level refinements to
already-approved tables.

## 13. Withdrawal/resubmission policy pass (this round)

Approved as **Option A** (A-18): withdrawal never releases the candidate-requisition
pair. No table, field, lifecycle state, or algorithm changed — the policy was
already satisfied by the existing orthogonality between `Application.stage` and
`ApplicationSubmissionAttempt`'s canonical-reconciliation logic; this pass makes
that orthogonality explicit in `business_rules.md` §3a, `workflow.md` §2b,
`data_dictionary.md` §8/§8a, `entity_relationships.md` §5, and adds four test cases
in `validation_strategy.md` §18. The 22-table inventory and every existing ID
convention are unchanged.

## 14. Screening/decision logic verification pass (this round)

Resolved the gate-only-vs-weighted-education contradiction by adopting the
three-weight model (A-19): `education_component` is graded exactly like
`experience_component` (capped at 1.0 once the minimum is met), while
`education_gate_passed` keeps independent, unoverridden authority over
`screening_decision`. Added `ScreeningRule.education_weight_pct` and
`ScreeningRun`/`Application`'s `screening_education_component` — field additions
only; **22-table inventory unchanged.** Added an explicit fairness-scope statement
(`business_rules.md` §8 — what the design can and cannot establish; no legal or
bias-free certification is claimed) and five worked candidate examples
(`business_rules.md` §5a). No assumptions remain open from this round.

## 15. Final approval — screening and decision logic (this round)

**A-19 is now marked APPROVED** (not merely confirmed/proposed), with the five
education-policy points recorded verbatim in A-19 above. The exact approved
formula, default weights (50/30/20), and default threshold (70.0, newly and
explicitly documented) are stated identically across `business_rules.md` §5,
`data_dictionary.md` §9, `validation_strategy.md` §5/§19, `workflow.md` §3, and
`architecture.md` §8. Both zero-division risks (`min_years_experience=0`;
`min_education_level`'s ordinal rank) are now stated explicitly as safe by
construction, not left as an implicit formula branch. All five primary worked
examples were hand-reverified against the exact approved formula — **mathematically
correct, no corrections needed**; the boundary pair's previously-unverified
placeholder numbers were replaced with a fully concrete, hand-computed pair
(`70.00`/`69.25`). Historical `ScreeningRun` reproducibility is unaffected and
re-confirmed: `screening_rule_id` still points at the exact, immutable rule row in
effect at `computed_at` (`business_rules.md` §4), now additionally covering
`education_weight_pct`. **22-table inventory unchanged. No remaining assumptions
from this round.**

## 16. Anomaly generation and validation verification pass (this round)

Re-verified all mandated volumes (100/2,000/3,000/600/150), confirmed they are
final/exported totals inclusive of anomalies, not pre-injection baselines
(`business_rules.md` §1, new explicit clarification). Confirmed the five-step
pipeline's abort mechanism concretely (`business_rules.md` §13 — an exception, not
a bypassable flag) and re-verified structural integrity holds unconditionally
post-injection while exactly five business-rule categories are expected to change
from zero to a documented count. Closed one real gap: **export consistency** had
never been a named validation category — added as VAL-16
(`validation_strategy.md` §20). Compiled a formal 16-row `VAL-nn` rule-ID catalog
(§21) mapping every requested validation area to its detection logic, severity, and
baseline-vs-post-injection expected output. Added a formal precision/recall/F1
framework with both a real (1.00/1.00/1.00) and an illustrative hypothetical worked
example (§22). Explicitly assessed three potential indirect ground-truth-leakage
channels (§23) — none currently exploited; one named as a documented boundary of
the leakage guarantee's scope, not a defect. Clarified the "no anomaly-category
overlap" guarantee's precise scope (row-level, not entity-group-level) in
`business_rules.md` §9. **No table added or removed — 22-table inventory
unchanged. No new assumptions requiring approval.**

## 17. Prompt 5 correction pass (this round)

Three issues resolved, none requiring a table change:

1. **AnomalyLabel arithmetic (56/11) was already correct** — the apparent
   51-vs-56 gap is fully explained by type 5's documented "one label per affected
   Application" rule (5 incidents × 2 applications = 10 labels, not 5; same for
   starter). Made explicit in a new granularity table, `business_rules.md` §9a.
   Counts were not changed to force agreement — they were already right; only the
   explanation was missing.
2. **Baseline-vs-post-injection state** — added a complete before/after table for
   every affected table, explicitly distinguishing *modified*, *added* (only
   `ApplicationSubmissionAttempt`, +15), and *removed* (only `Feedback`, −10) rows
   (`business_rules.md` §13a). Baseline validation evidence is now retained and
   reproducible via two new `GenerationRun` fields —
   `baseline_validation_report_json` and `post_injection_validation_report_json`
   (`data_dictionary.md` §17) — giving a reviewer two concrete, timestamped
   artifacts to compare, not an inference.
3. **Detection evaluation consistency** — corrected a real overclaiming issue: the
   prior "TP=15/FP=0/FN=0" result was presented as if tested; relabeled explicitly
   as an **EXPECTED, design-derived projection**, since no detector code exists yet
   (`validation_strategy.md` §22). Clarified evaluation is at **affected-entity
   level**, not incident level, with an explicit per-category matching-key table;
   the closed-requisition detector's reporting granularity was corrected to match
   (`validation_strategy.md` §12).

**No table added or removed — 22-table inventory unchanged.** `GenerationRun`
gained two fields (not a new table). No new assumptions requiring approval.

## 18. Prompt 5 final clarification pass (this round)

Two points resolved:

1. **Closed-requisition anomaly granularity** — four distinct numbers stated side
   by side (incidents: 5/1; affected `JobRequisition`: 5/1; affected `Application`:
   10/2; evaluation units/`AnomalyLabel` rows: 10/2 — `business_rules.md` §9b).
   Flipped `AnomalyLabel.entity_type` for this anomaly type from `JobRequisition`
   to `Application` (`data_dictionary.md` §16) so `entity_id` is uniformly the
   matching key across all five anomaly types — `JobRequisition` is now
   confirmed, structurally, to be incident *context* only (`related_entity_id`),
   never a separately-evaluated entity. This removed a dead `JobRequisition` value
   from the `entity_type` enum and a type-5 exception from the matching-key table
   (`validation_strategy.md` §22). Anomaly counts (10/2 for this type, 56/11
   overall) are unchanged.
2. **Reproducibility and timestamps** — added `GenerationRun.generator_version`
   and explicitly classified every `GenerationRun` field as either volatile
   execution metadata (`run_id`, `generated_at`, nested report timestamps — never
   checksummed, never expected to match across runs) or deterministic content
   (`seed`, `mode`, `generator_version`, the checksum fields, the report JSONs'
   *results* portions — expected to match across runs sharing the same seed/mode/
   version). Corrected `table_checksums_json`'s documented scope from "all 22
   tables" to the 21 operational content tables, explicitly excluding
   `GenerationRun` itself (`data_dictionary.md` §17, `validation_strategy.md`
   §13).

**No table added or removed — 22-table inventory unchanged.** `AnomalyLabel`'s
entity-type enum lost one dead value (`JobRequisition`); `GenerationRun` gained
one field (`generator_version`) — both field-level changes to already-approved
tables. **No anomaly count changed.** No new assumptions requiring approval.

## 19. Implementation Plan Verification pass (this round)

`implementation_plan.md` substantially rewritten — not just reviewed. Two real
issues found, not just gaps: (1) a genuine dependency bug (the old plan sequenced
building the validation engine *after* anomaly injection, while also requiring the
validation engine to run *before* injection as a gate — fixed by moving engine
construction to the new Phase 4, before injection); (2) no explicit project-setup
phase existed. Fixed with a new Phase 1. The plan now has 11 phases (was 7), each
with Objective/Tasks/Dependencies/Files/Deliverables/Acceptance
criteria/Tests/Definition-of-done. The previously-open "merge Phases 4/5 or stub
the shared formula" question is now **resolved** (Option A, adopted — shared
pure-function formulas built once in Phase 4, imported unchanged by Phase 7's live
services), not left open again. Added: a full 22-table-to-module ownership
mapping; an API/frontend contract specification (request/response schema,
error-format, pagination — none of this existed before); a P0/P1/P2 priority
classification; a 72-hour feasibility estimate (tight but feasible, explicitly
labeled as an estimate, not a measured result); a critical-business-rule
implementation checklist (sections A–E, every approved rule mapped to a specific
task and test); a cross-cutting test/acceptance-gate matrix.

**One documentation gap found and flagged, not fixed in this pass** (out of this
prompt's explicit document scope): `prompts/ai_usage_disclosure.md` and parts of
`prompts/chatgpt_prompts.md` are stale relative to the 17 actual prompt-log
entries that now exist — flagged for a dedicated follow-up before Phase 11's
submission packaging, not silently left unmentioned.

**No table added or removed — 22-table inventory unchanged. No approved business
policy changed.** No application code written, no dependencies installed, no
database created. Phase 1 (environment setup) has not started.
