# Implementation Plan

**Revision 2** — Phase 0 now covers two review rounds; Phase 1's table count and
Phase 2/3's ID-derivation and anomaly-count details are corrected to match
`data_dictionary.md`/`business_rules.md` Rev 2.

**Second verification pass** — Phase 0 now covers a third round (screening-history
redesign, ground-truth scope, pipeline confirmation, role-enforcement split); table
count is 22; Phase 2 adds the baseline-integrity gate and `ScreeningRun` to the
generation order; Phase 5 adds hard role enforcement.

**Implementation-detail clarification pass** — Phase 0 covers a fourth round
(`ScreeningRule` versioning/direct FK, duplicate-attempt tie-break, `ScreeningRun`
latest-row invariant); Phase 1 adds three named partial unique indexes and one
check constraint.

**Prompt 5 passes** — Phase 0 covers rounds five through seven (anomaly/validation
verification, two correction passes: `AnomalyLabel` granularity, baseline/
post-injection volume accounting, `GenerationRun` timestamp/checksum scope,
`entity_type` flip for the closed-requisition anomaly).

**Prompt 6 — Implementation Plan Verification pass (this revision):** this plan is
substantially rewritten. Two real issues were found in the prior version, not just
gaps: (1) **a genuine dependency bug** — the old Phase 4 ("Validation engine") was
sequenced *after* the old Phase 3 ("Anomaly injection"), but the old Phase 2's gate
already required running "the full validation suite" *before* Phase 3 — the
validation code that gate depends on did not exist yet at that point in the old
plan. Fixed by moving validation-engine construction earlier (new Phase 4, before
injection) and splitting "build the engine" from "rerun it post-injection + add
ground-truth evaluation" (new Phase 6). (2) **No explicit project-setup phase
existed** — dependency management, `.gitignore`, and folder scaffolding were
implicitly assumed, not planned. Fixed with a new Phase 1. The previously-open
"Phases 4 and 5 both need the same formula — merge or stub?" sequencing question is
now **resolved** (not left open): shared pure-function formulas are built once, in
the new Phase 4, with zero DB/HTTP dependency, and imported by both validation and
the later live services (new Phase 7) — Option A from the prior open question,
now adopted rather than merely recommended. All phase numbers below are renumbered
accordingly; no table, field, or approved business policy changed — see
`PROJECT_SPEC.md` for the corresponding summary entry.

Development proceeds one module at a time; each phase ends with a checkpoint for
explicit approval before the next phase starts, per the project's stated working
agreement. Nothing in a later phase is started early.

## Phase 0 — Architecture (COMPLETE)

Seven review rounds, summarized in `PROJECT_SPEC.md` §§9–18: the 8 architecture
documents, 19 confirmed/approved assumptions (A-1…A-19), the 22-table inventory,
the three-weight screening model, the withdrawal/resubmission policy, the full
anomaly/validation verification, and this plan's own restructuring. **Gate:** user
approves this revision before Phase 1 begins.

## Dependency graph (revised, this pass)

```
Phase 0 (architecture, DONE)
   │
   ▼
Phase 1 (project setup)
   │
   ▼
Phase 2 (DB schema / models)
   │
   ▼
Phase 3 (baseline generation) ──needs schema from Phase 2
   │
   ▼
Phase 4 (validation engine + shared formulas) ──needs baseline from Phase 3 to run against;
   │                                              needs schema from Phase 2 to query
   ▼
   [GATE: zero violations, or Phase 5 never starts — business_rules.md §13]
   │
   ▼
Phase 5 (anomaly injection + AnomalyLabel) ──needs Phase 4's clean baseline result
   │
   ▼
Phase 6 (rerun Phase 4's engine post-injection + ground-truth evaluation)
   │
   ├──────────────────────────────┐
   ▼                              ▼
Phase 7 (screening + duplicate   Phase 9 (analytics + exports) ──can start once
  services, reusing Phase 4's      Phase 3's data exists; doesn't need Phase 7/8
  shared formulas)                 to be done, only to not conflict with it
   │
   ▼
Phase 8 (workflow services + FastAPI, reusing Phase 7's services)
   │
   ▼
Phase 10 (React frontend) ──needs Phase 8's API contract frozen
   │
   ▼
Phase 11 (integration, docs, submission)
```

**Where this differs from a naive reading of the brief's suggested phase names,
and why:** Phase 9 (analytics/exports) is drawn branching off Phase 6, not chained
strictly after Phase 8, because analytics/exports are read-only consumers of the
database (`architecture.md` §2) and have no structural dependency on the workflow
services or API existing — they can be built and tested against Phase 6's dataset
in parallel with Phase 7/8. They are *listed* after Phase 8 below only to match the
"don't let polish precede correctness" priority ordering (§7), not because of a
hard technical dependency.

## Phase 1 — Project setup and environment — **STATUS: COMPLETE**

| Attribute | Detail |
|---|---|
| **Objective** | A clonable, runnable skeleton exists before any model or business logic is written. |
| **Tasks** | `backend/pyproject.toml` (Python 3.12, pinned versions: FastAPI, SQLAlchemy, Pydantic, Faker, pandas, pytest — `PROJECT_SPEC.md` §8); `frontend/package.json` (React, TypeScript, Vite, Recharts, pinned versions); root `.gitignore`; `backend/app/config.py` (seed=20261022 constant, DB path, mode default); empty package `__init__.py` scaffolding per `architecture.md` §7's directory tree. |
| **Dependencies** | None — this is the first phase after architecture. |
| **Expected files/modules** | `backend/pyproject.toml`, `backend/app/config.py`, `backend/app/main.py`, `backend/app/__init__.py` (+ empty package dirs: `db/`, `db/models/`, `schemas/`, `api/`, `api/v1/`, `services/`, `analytics/`, `validation/`, `validation/rules/`, `data_generation/`, `data_generation/entities/`, `data_generation/anomalies/`), `backend/tests/test_health.py`, `backend/.env.example`, `frontend/` (full Vite `react-ts` scaffold + Recharts), `.gitignore`, `README.md`. |
| **Deliverables** | Actually done, this round: backend package installed editable into a Python 3.12.10 venv; frontend scaffolded via `npm create vite@latest -- --template react-ts` + `npm install recharts`. |
| **Acceptance criteria — actually verified, not just generated:** | `pytest tests/` → 1 passed; `uvicorn app.main:app` → started, `GET /health` returned `{"status":"ok","service":"talentflow-ai-backend"}` (HTTP 200), `GET /docs` returned HTTP 200; `npm run build` → compiled clean (tsc + vite, 222KB bundle); `npm run dev` → started, served HTTP 200 on its bound port. |
| **Tests required** | `backend/tests/test_health.py` — written and passing. |
| **Definition of done** | Met. **One deliberate deviation from the original plan, noted rather than silently skipped:** `scripts/setup.sh`/`setup.ps1` were not created — `README.md`'s inline setup commands cover the same ground for a project this size, and adding wrapper scripts now would be premature abstraction. Revisit only if manual setup proves error-prone in practice. |

## Phase 2 — Database schema and SQLAlchemy models — **STATUS: COMPLETE**

| Attribute | Detail |
|---|---|
| **Objective** | All 22 tables exist as SQLAlchemy models with every FK, enum, composite PK, and constraint from `data_dictionary.md`. |
| **Tasks** | One model module per `architecture.md` §7's file grouping (10 files, 22 tables — see the table-to-module map below); `Application.application_id` as a derived column, populated by application code at insert time (not a SQL `GENERATED ALWAYS AS`, so the derivation logic lives in one Python place shared with validation); the self-referential FK on `ApplicationSubmissionAttempt.duplicate_of_attempt_id`; `ScreeningRun` and `ScreeningRule` with no `UPDATE`/`DELETE` path exposed above the ORM for their scoring/criteria fields; the three named partial unique indexes (`uq_attempt_canonical`, `uq_screeningrun_latest`, `uq_screeningrule_current`) and the one check constraint (`data_dictionary.md` §8a/§8b/§9); a simple `create_all()` bootstrap (no migration tooling — greenfield SQLite, avoid unnecessary complexity). |
| **Dependencies** | Phase 1 (environment must exist to run anything). |
| **Expected files/modules** | `backend/app/db/base.py`, `session.py`, `models/{department,actor,requisition,candidate,skill,application,screening,interview,offer,history,anomaly,generation_run}.py` — see the full 22-table mapping below for exact ownership. |
| **Deliverables — actually done, this round, across 8 incremental commits** | All 22 tables built and committed: (1) `54cf120` Department/Skill/SystemActor/Interviewer/InterviewerAvailabilitySlot; (2) `a4dc147` JobRequisition/JobRequisitionSkill/ScreeningRule; (3) `ab530ae` Candidate/ResumeArtifact/CandidateSkill; (4) `d0153fd` Application/ApplicationSubmissionAttempt/ScreeningRun (including the verified two-table FK cycle between `Application.latest_screening_run_id` and `ScreeningRun.application_id`); (5) `43598a0` Interview/Feedback; (6) `472914c` Offer; (7) `0e81fa8` RequisitionStatusHistory/ApplicationStageHistory/OfferStatusHistory; (8) `20e2357` AnomalyLabel/GenerationRun, plus closing the `ApplicationSubmissionAttempt.ground_truth_label_id` FK deferred since commit 4. |
| **Acceptance criteria — actually verified, not just generated** | `pytest tests/` → **104 passed**, 0 failed (grew from 13 after unit 1 to 104 across all 8 units). Both structural-guarantee cases are real, passing tests: (a) `test_application_valid_insert`'s PK IS the derived `(requisition_id, candidate_id)` pair — verified via the GLOB format check and FK-existence tests; (b) `test_application_submission_attempt_two_canonical_for_same_application_rejected`, `test_screening_run_two_latest_for_same_application_rejected`, and `test_screening_rule_two_current_rows_for_same_requisition_rejected` all pass, proving the three partial unique indexes fire. `Base.metadata.create_all()` succeeds cleanly across the full 22-table schema (verified in the Unit 8 run), confirming no remaining circular-dependency or ordering issues. |
| **Tests required** | `test_models.py`: table creation, every FK/constraint/index negative-tested, enum value rejection, the two cases above. **Met** — 104 test functions. |
| **Definition of done** | `pytest tests/test_models.py` green — **met**. Schema reviewed field-by-field against `data_dictionary.md` by the user — **not yet done; still open**. |
| **Bugs found and fixed during this phase (real, not fabricated)** | (1) `Enum()` needs `create_constraint=True` to emit a CHECK on SQLite — found in Unit 1, applied as the default pattern thereafter. (2) Three separate test-helper collisions (Units 4, 5) where two independent helper functions each re-created the same prerequisite row (`Department`/`SystemActor`/`JobRequisition`), violating a unique constraint — fixed by inserting the shared prerequisite directly instead of through the redundant helper. (3) One test (Unit 4) that wrapped only `session.commit()` in `pytest.raises` when the actual `IntegrityError` fired immediately on the preceding bulk `.update()` call — widened the `pytest.raises` block. |

## Phase 3 — Deterministic baseline data generation — **STATUS: COMPLETE**

| Attribute | Detail |
|---|---|
| **Objective** | A full, internally consistent baseline dataset (no anomalies yet) at both starter and full scale, byte-reproducible under the fixed seed. |
| **Tasks** | `data_generation/generator.py` (`--mode starter\|full --seed 20261022` CLI) + `entities/*.py`, one per table, in the exact order fixed by `architecture.md` §4: `Department → SystemActor → Skill → Interviewer → InterviewerAvailabilitySlot → JobRequisition → JobRequisitionSkill → ScreeningRule → Candidate → ResumeArtifact → CandidateSkill → Application → ApplicationSubmissionAttempt → ScreeningRun → Interview → Feedback → Offer`; reference tables (`Department`=10, `Skill`=40, `Interviewer`=25, `SystemActor`=20) generated at a fixed size regardless of mode (A-13); `Application`+`ApplicationSubmissionAttempt`+`ScreeningRun` generated together per pair, per the insert-then-update sequencing in `architecture.md` §4; Faker driven by the seeded `random.Random` instance, never the global `random` module; `export.py` writing CSV/JSON to `backend/data/exports/` for the 21 operational tables. |
| **Deviations from this row's original text — flagged, not silent** | (1) **Module count**: 8 consolidated entity modules were built instead of 17 one-per-table modules (`reference_data.py`, `requisitions.py`, `candidates.py`, `applications.py`, `interviews.py`, `offers.py`, `history.py`, plus `volumes.py`/`seeding.py`/`export.py`/`generator.py`) — a deliberate time-boxed consolidation of closely-related, together-generated entities, not a scope cut; every table listed in the generation order is still present. (2) **`GenerationRun` is written now, in Phase 3**, not deferred to "Phase 5" as this row previously said — that note was stale (Phase 5 is anomaly injection, not where a reproducibility manifest belongs) and the accelerated-implementation prompt explicitly asked for it this phase; its two validation-report JSON fields honestly store `{"status": "not_yet_run", ...}` rather than fabricated results, since Phase 4 doesn't exist yet. (3) A new shared module, `app/screening_formula.py`, was added as a Phase 3 prerequisite (see its own commit/docstring for the full reasoning — `data_generation/` needs the exact `business_rules.md` §5 formula to produce a genuinely correct baseline, but is architecturally forbidden from importing the not-yet-built `services/`). (4) `seeding.py`'s child-seed derivation uses SHA-256, not Python's builtin `hash()` — `architecture.md` §4's literal wording would silently break reproducibility across process runs (builtin `hash()` on strings is salted per-process). |
| **Dependencies** | Phase 2 (schema must exist to insert into) — met. |
| **Deliverables — actually done, this round, and verified by real command output, not generated-and-assumed** | Both `--mode starter` and `--mode full` run end-to-end successfully. Starter: 10 requisitions / 100 candidates / 150 applications / 30 interviews / 8 offers — exactly matching PROJECT_SPEC.md A-6. Full: 100 / 2,000 / 3,000 / 600 / 150 — exactly matching this prompt's mandated volumes and `business_rules.md` §1's unprefixed (non-"~") headline numbers. `ScreeningRun`/`ApplicationSubmissionAttempt` are a genuine 1:1 shadow of `Application` at both scales (150/150/150, 3,000/3,000/3,000). `AnomalyLabel` has 0 rows at both scales (Phase 5 only, per PROJECT_SPEC.md A-5's baseline-vs-final distinction). Full-mode generation + DB load together took ≈2.2 seconds. |
| **Acceptance criteria — actually verified** | `PRAGMA foreign_key_check` returns zero violations on both generated databases. Re-running the same seed+mode twice produces byte-identical per-table and overall SHA-256 checksums (verified for both starter and full — overall checksums `006859be...` and `fd966ace...` respectively, reproduced exactly on a second run). A different seed (99999) produces a different checksum at the generation layer (verified directly; it cannot be persisted as a `GenerationRun` row, since that table's `seed` CHECK constraint only accepts 20261022 by design — confirmed this correctly raises `IntegrityError`, not a bug). No `Closed`/`Cancelled` requisition has a non-terminal-stage application (the clean baseline never accidentally produces a `ClosedReqActiveApplications`-shaped row). Every required-skill weight set sums to exactly 100. Every `Completed` `Interview` has exactly one `Feedback` row. |
| **Tests required** | `tests/test_screening_formula.py` (7 tests, all 5 worked examples + both boundary-pair cases from `business_rules.md` §5a reproduced exactly) and `tests/test_data_generation.py` (8 tests: starter succeeds and populates all tables appropriately, full-mode volumes match mandated requirements, FK relationships valid via `PRAGMA foreign_key_check`, same-seed reproducibility, different-seed divergence, `GenerationRun` metadata correctness, and the non-mandated-seed rejection). All 15 pass; the pre-existing 105 Phase 2 tests still pass unmodified — **120 passed, 0 failed** total. |
| **Definition of done** | Met. Schema audit against `data_dictionary.md` performed first (per this phase's prompt) — found and fixed one genuine gap (`ResumeArtifact.parsed_years_experience` missing a documented `>= 0` CHECK); no other discrepancies across all 22 tables. Spot-checked sample `Application`/`ScreeningRun` rows by hand against the formula — scores, components, gate results, and explanation text all internally consistent. |

## Phase 4 — Validation engine + shared business-rule formulas (resequenced, this pass) — **STATUS: COMPLETE**

**This is the phase whose position changed to fix the dependency bug described in
this document's banner.** It must exist *before* Phase 5 (anomaly injection),
because Phase 5's own gate requires running it first.

| Attribute | Detail |
|---|---|
| **Objective** | All 16 `VAL-nn` rule categories (`validation_strategy.md` §21) exist as code and can certify the Phase 3 baseline has zero violations; the shared pure-function formulas (screening scoring, canonical-attempt reconciliation) exist in exactly one place, ready to be imported by both this engine and the later live services. |
| **Tasks** | `validation/rules/*.py`, one module per `VAL-nn` category; `validation/reconcile.py` (VAL-12), `validation/checksums.py` (VAL-13), `validation/ground_truth_leakage.py` (VAL-15), `validation/runner.py` (central runner), `validation/gate.py` (the hard abort gate, wired directly into `data_generation/generator.py`'s entrypoint); the whole-package ground-truth non-leakage scan over `services/` and `validation/rules/` — vacuously true for `services/` (doesn't exist yet) and genuinely zero findings for `validation/rules/` on this codebase's real source. |
| **Deviations from this row's original text — flagged, not silent** | (1) **No `services/` module was built.** The row originally said `services/screening.py:compute_screening_score` and `services/application_submission.py:reconcile_canonical` would be built "here as plain functions" — but `services/` is genuinely Phase 7/8 scope (the live workflow/API layer), and this prompt's own boundaries said nothing about building it now. The screening formula already lives at `app/screening_formula.py` (added as a Phase 3 prerequisite, same reasoning as before: `data_generation/` needs it and can't import `services/`). The canonical-attempt reconciliation function (`recompute_canonical_assignment`) lives in `validation/rules/duplicate_submissions.py` instead, since that is its only consumer right now; its docstring states Phase 5/8 must import it from there rather than redefining it. (2) **`GenerationRun` already existed before this phase** — Phase 3 added it with honest placeholder validation-report fields; this phase's real work was replacing those placeholders with the first genuinely computed `baseline_validation_report_json`/`post_injection_validation_report_json`, not creating the row for the first time as this row's last line assumed. (3) **VAL-07 covers three history tables, not two** — `validation_strategy.md` §7's prose says "the three history tables" but the formal catalog only names VAL-07a/VAL-07b; `OfferStatusHistory` transition-legality is checked too, reported under VAL-07b with a distinct `offer_lifecycle` category rather than inventing a new rule ID. (4) **VAL-16 (export consistency) covers CSV only** — no JSON/SQL export format exists yet (already flagged in Phase 3's row). |
| **Dependencies** | Phase 3 (needs a baseline to validate against) — met. |
| **Expected files/modules** | `validation/report.py`, `validation/runner.py`, `validation/gate.py`, `validation/reconcile.py`, `validation/checksums.py`, `validation/ground_truth_leakage.py`, `validation/rules/*.py` (13 modules covering all 17 rule-ID labels). |
| **Deliverables — actually done, verified by real command output** | `python -m app.data_generation.generator --mode starter` and `--mode full` both run the baseline gate as part of generation and report **0 violations, 0 warnings across 17 rules** on both scales. Two genuine bugs were found and fixed by this engine the first time it actually ran against real generator output (not staged corruptions): (a) `data_generation/entities/history.py` reused the same APPROVER actor for every `OfferStatusHistory` transition instead of only the hard-gated one (VAL-14 caught this); (b) offer-bearing applications (hired/declined/pending) could be generated against a requisition whose `OnHold`/`Closed` transition timing predated the offer's actual approval timestamp (VAL-09 caught this) — fixed by restricting those three buckets to `Open`-status requisitions only. A third, unrelated bug (`Decimal` vs `float` string-formatting mismatch between live-DB reads and in-memory generation data) was caught by VAL-13's own test and fixed in `export.py`'s `_cell()`. |
| **Acceptance criteria — actually verified** | Both databases pass the gate with zero violations (see above). `pytest tests/test_validation.py` — **25 passed**, covering all 17 rule-ID labels, both clean-baseline cases, multiple deliberately-corrupted-record detection cases (one per rule, via direct SQL since no CHECK constraint can structurally express most of these cross-table/business-rule invariants), the baseline gate blocking on corrupted data, deterministic output (`results_only()` byte-identical across two runs), and the ground-truth leakage scan returning zero findings on this codebase's actual `app/` tree. Full suite: **145 passed, 0 failed** (120 pre-existing + 25 new). |
| **Tests required** | `tests/test_validation.py` — met, 25 tests. |
| **Definition of done** | `pytest tests/` green with zero violations on both generated baselines — met. One explicitly deferred item, not silently skipped: `test_hard_role_checks_cannot_be_bypassed` (validation_strategy.md §14) needs `services/requisition_lifecycle.py`/`services/offer_lifecycle.py` to exist, which is Phase 7/8 work — deferred until those modules are built. |

## Phase 5 — Anomaly injection and ground-truth generation — **STATUS: COMPLETE**

| Attribute | Detail |
|---|---|
| **Objective** | The five approved anomaly types are injected into the Phase 3 baseline, each `AnomalyLabel` row written inline, and the full `GenerationRun` manifest (including both validation-report fields) is produced. |
| **Tasks** | `data_generation/anomalies/*.py`, one module per type, run only after Phase 4's gate passes; duplicate-application injector adds extra `ApplicationSubmissionAttempt` rows only (never a second `Application` row); closed-requisition injector writes `AnomalyLabel` with `entity_type=Application` (one row per affected application, `entity_id`=that application, `related_entity_id`=the requisition — `data_dictionary.md` §16's flip); `GenerationRun` row written with `seed`, `mode`, `generator_version`, `generated_by_actor_id`, `entity_counts_json`, `table_checksums_json`/`overall_checksum` (the 21 operational tables), and now both `baseline_validation_report_json` (pre-injection) **and** `post_injection_validation_report_json` (a real, genuinely-computed post-injection run — not deferred to Phase 6, since re-running the same VAL-01..16 suite is pipeline step 4, business_rules.md §13, generation-time work; Phase 6 is specifically the separate ground-truth precision/recall/F1 comparison, step 5, which this phase does not implement). |
| **Deviations from this row's original text — flagged, not silent** | (1) No `data_generation/checksums.py` was created — `data_generation/export.py` already owns checksumming (Phase 3) and gained one new function, `read_tables_from_db()`, so exports can reflect the live post-injection database rather than the stale in-memory pre-injection dataset; `validation/checksums.py` (Phase 4) was refactored to reuse it instead of duplicating the row-reading logic. (2) `post_injection_validation_report_json` is populated now, in this phase, not deferred to "once Phase 6 produces it" as this row previously said — see Tasks above for why that's correct, not an overreach into Phase 6. |
| **Dependencies** | Phase 4's gate (zero baseline violations) — met; the gate is wired directly into `generator.py`'s entrypoint and genuinely raises `BaselineValidationFailed` (not just documented) if violated. |
| **Expected files/modules** | `data_generation/anomalies/{unavailable_interviewer,duplicate_application,missing_feedback,salary_band,closed_requisition,injector}.py`. |
| **Deliverables — actually done, verified by real command output** | Full dataset: exactly 56 `AnomalyLabel` rows (15 UnavailableInterviewer, 15 DuplicateApplication, 10 MissingFeedbackStageAdvanced, 6 SalaryOutsideBand, 10 ClosedReqActiveApplications); `ApplicationSubmissionAttempt` at 3,015 (3,000 canonical + 15 duplicates); `Feedback` at 528 (538 − 10). Starter: 11 `AnomalyLabel` rows (3/3/2/1/2); `ApplicationSubmissionAttempt` at 153; `Feedback` at 25 (27 − 2). Both exactly matching `business_rules.md` §9a. |
| **Acceptance criteria — actually verified** | Post-injection validation on both scales: VAL-01/02/03/04/05/07a/07b/09/13/14/15/16 all exactly 0 (structural integrity genuinely unbroken by injection, not assumed); VAL-06/08/10/11/12 exactly 15/10/6/15/10 (full) and 3/2/1/3/2 (starter) — matching `business_rules.md` §9's table exactly, with zero drift between injected counts and detected counts. `PRAGMA foreign_key_check`: zero violations on both post-injection databases. Re-running the same seed twice: identical overall + per-table SHA-256 checksums, **including** `anomaly_label` (full: `649898f0...`, starter: `e026ca7b...`). |
| **Bugs found and fixed during this phase** | Three real defects, all caught by running the injectors against real baseline data, not staged scenarios: (1) picking `Completed` interviews for the unavailable-interviewer anomaly (the spec text allows it) broke `Feedback.submitted_at >= Interview.scheduled_end` when the interview's time was shifted forward — fixed by restricting to `Scheduled` interviews only, which never have `Feedback` yet. (2) the closed-requisition injector computed its `closed_at` timestamp only from the 2 *non-terminal* applications it was leaving active, ignoring other (already-Hired/Rejected) applications on the same requisition whose `Offer.approved_at` could be later — retroactively made a valid historical approval look like it happened against an already-closed requisition (VAL-09) — fixed by computing `closed_at` from every application and offer event on that requisition. (3) `duplicate_submissions.py` (VAL-11) only checked stored-vs-recomputed *consistency* (always 0, since the write path is correct) but never reported detected duplicates as the rule's actual output — the catalog's "15/3 non-canonical attempts post-injection" expectation was a detection-output count, not a consistency-mismatch count — fixed by adding a finding per attempt the shared algorithm determines is a duplicate. A fourth bug (non-deterministic `injected_at` using wall-clock `datetime.now()` instead of a seeded timestamp) was caught by the reproducibility check itself and is detailed in the prompt-log entry. |
| **Tests required** | `tests/test_anomaly_injection.py` — met, 16 tests (exact incident/`AnomalyLabel` counts both scales, entity-type breakdown, per-type affected-record correctness, duplicate-submission linkage to the existing canonical `Application`, no duplicate canonical `Application` rows, structural integrity, determinism, reproducible checksums, baseline-gate-blocks-injection, ground-truth isolation, distinct baseline/post-injection reports). Full suite: **161 passed, 0 failed** (145 pre-existing + 16 new). |
| **Definition of done** | Met. Manually reviewed one example of each anomaly type via direct SQL inspection during development (see this phase's prompt-log entry for the actual queries and output) — the duplicate-application example is confirmed a second `ApplicationSubmissionAttempt` row, never a second `Application`. |

## Phase 6 — Independent anomaly detection and ground-truth evaluation — **STATUS: COMPLETE**

| Attribute | Detail |
|---|---|
| **Objective** | Prove the Phase 4 validation engine, rerun unmodified against the post-injection dataset, finds exactly what Phase 5 seeded — without ever reading `AnomalyLabel` — and produce the precision/recall/F1 evaluation. |
| **Tasks** | Rerun the *same* Phase 4 code (no new detection logic) — `VAL-06/08/10/11/12` are now expected to report their documented non-zero counts; the other 11 categories must still report zero (already wired into `generator.py` since Phase 5); **new code this phase**: `validation/detect.py` (groups the five already-existing rule checks by anomaly type, for duplicate applications reusing `duplicate_submissions.select_detected_duplicates()` rather than redefining anything) and `validation/evaluate.py` (the offline, read-only comparison against ground truth, computing TP/FP/FN/precision/recall/F1 per `validation_strategy.md` §22, keyed uniformly on `entity_id`). |
| **Deviation from this row's original text — flagged, not silent** | `validation/detect.py` was not in the original "Expected files/modules" list — added as the formal detection-entry-point Phase 6's own prompt explicitly asked for ("Independent detector implementation" as a named deliverable, separate from the evaluation module). It contains **zero new detection logic** — every one of its five entries is a direct call into the Phase 4 rule module that already existed (`scheduling_conflicts.check`, `feedback_requirements.check`, `salary_band.check`, `closed_req_active_apps.check`, and `duplicate_submissions.select_detected_duplicates(duplicate_submissions.check(...))`), grouped by anomaly type instead of by `VAL-nn` rule ID purely for the evaluator's convenience. |
| **Dependencies** | Phase 5 (anomalies must exist to detect) — met. |
| **Expected files/modules** | `validation/detect.py`, `validation/evaluate.py` (both new); `validation/ground_truth_leakage.py` extended with `SCAN_FILES` so `detect.py` — an "operational detector module" by this phase's own framing, despite living outside `validation/rules/` for the same organizational reason as `runner.py` — is covered by the leakage scan; `evaluate.py` explicitly excluded from that scan (the one place, alongside `reconcile.py`, permitted to read ground truth). No changes to `validation/rules/*.py` detection logic from Phase 4 (only VAL-11's `rule_category` structure, already done in the P023 preparatory pass). |
| **Deliverables — actually done, verified by real command output** | `python -m app.validation.evaluate --mode starter` and `--mode full` both run end-to-end, writing `data/evaluation_reports/{starter,full}.json` and printing a human-readable per-type + overall summary table. Both scales: **TP=15/15/10/6/10 (full), 3/3/2/1/2 (starter), FP=0, FN=0, for every one of the five categories** — zero drift between what each Phase 5 injector wrote and what the corresponding Phase 4 detector independently re-derives. `Precision=Recall=F1=1.00` per category and overall (micro-averaged), at both scales — the `validation_strategy.md` §22 design projection, now actually measured for the first time, not merely asserted. |
| **Acceptance criteria — actually verified** | Validation counts match `business_rules.md` §9a exactly (56/11 `AnomalyLabel` rows, matched 1:1 by the evaluator at both scales — already true since Phase 5, re-confirmed here). `TN` is `None` with an explanatory note for every category and overall — never fabricated, never silently omitted (this phase's own explicit instruction). Evaluation reports are byte-identical across two fully independent generate→inject→evaluate pipeline runs with the same seed (verified directly, not assumed). Operational detection findings are provably unaffected by deleting all ground truth (a dedicated test deletes every `AnomalyLabel` row, including nulling the one FK that references it, and confirms `detect.run_detectors()` returns identical entity sets before and after). |
| **Tests required** | `tests/test_phase6_detection_evaluation.py` — met, 26 tests (all five detectors + exact counts both scales, TP/FP/FN math on controlled fixtures including every empty-denominator combination, the one-detection-one-TP dedup guarantee, micro-average aggregation, `TN` always `None` with the note, starter/full end-to-end at perfect P=R=F1=1.00, report reproducibility, read-only evaluation via before/after row-count snapshots, ground-truth independence of detection, evaluation changing when ground truth changes while detection does not, the extended leakage scan covering `detect.py`, and `evaluate.py`'s explicit exemption from that scan). Full suite: **191 passed, 0 failed** (165 pre-existing + 26 new). |
| **Definition of done** | Met. This phase's results are the first point in the project where the §22 "EXPECTED" projections become **actual, executed, measured** results, now recorded as such in `validation_strategy.md` §22 itself rather than left as a stale "not yet tested" disclosure. |

## Phase 7 — Screening engine and duplicate-submission reconciliation services

| Attribute | Detail |
|---|---|
| **Objective** | The live write-path services exist, reusing Phase 4's shared formulas verbatim — not reimplementing them. |
| **Tasks** | `services/screening.py` gains the transactional wrapper around Phase 4's pure `compute_screening_score` (insert `ScreeningRun`, flip `is_latest`, update `Application`'s mirror — one atomic transaction, `business_rules.md` §5); `services/application_submission.py` gains the transactional wrapper around Phase 4's pure `reconcile_canonical` (ensure `Application` exists idempotently, insert the new attempt, rerun reconciliation over every attempt for the pair — `business_rules.md` §10, including the out-of-order-arrival case). |
| **Dependencies** | Phase 4 (the pure formulas must already exist to be wrapped, not reimplemented). |
| **Expected files/modules** | `services/screening.py` (extended), `services/application_submission.py` (extended). |
| **Deliverables** | A new submission or screening request, issued directly against these services (no HTTP layer needed yet), produces correct, transactionally-consistent results, including the withdrawal/resubmission and out-of-order-timestamp edge cases. |
| **Acceptance criteria** | All four withdrawal/resubmission test cases (`validation_strategy.md` §18) and all screening test cases (§19) pass against **real code**, not just the design projection. |
| **Tests required** | `test_business_rules.py` (screening + reconciliation, now against live services), the withdrawal/resubmission suite, a concurrency test simulating two near-simultaneous submissions for the same pair (SQLite serialization — `data_dictionary.md` §8a). |
| **Definition of done** | Every test case named in `validation_strategy.md` §18/§19 passes against this phase's code specifically (not the Phase 4 pure-function unit tests alone). |

**STATUS: COMPLETE** (2026-11-13). `services/screening.py` (`run_screening`)
and `services/application_submission.py` (`submit_application`)
implemented exactly as scoped above — both wrap Phase 4's pure functions
(`app.screening_formula.compute_screening_result`,
`app.validation.rules.duplicate_submissions.recompute_canonical_
assignment`) verbatim in one atomic transaction each, with no
reimplementation of either algorithm. `tests/test_services.py` (18 tests)
covers the screening boundary/gate cases, `is_latest`/history
consistency, repeated runs, historical-run survival across rule
redefinition, first-time/duplicate/out-of-order submission reconciliation,
and the withdrawal/resubmission edge cases from `validation_strategy.md`
§18. Full suite: 209 passed, 0 failed. **Note — a prompt issued against
this phase (P026 in `prompts/claude_code_prompts.md`) additionally asked
for requisition/offer lifecycle transitions and their role authorization.
Those are this plan's Phase 8 scope (see below — `requisition_lifecycle.py`
/`offer_lifecycle.py` and the hard APPROVER-role check), not Phase 7's, so
they were left for Phase 8 per that prompt's own instruction to defer
rather than silently expand scope. No lifecycle/authorization code or
tests exist yet; `test_hard_role_checks_cannot_be_bypassed` remains
deferred as already noted in Phase 6's Definition of done above.**

## Phase 8 — Recruitment workflow services and FastAPI backend

| Attribute | Detail |
|---|---|
| **Objective** | Full lifecycle services (requisition/application/offer/interview transitions) and a running API. |
| **Tasks** | `services/requisition_lifecycle.py`, `application_lifecycle.py`, `scheduling.py`, `offer_lifecycle.py` — `requisition_lifecycle.py`/`offer_lifecycle.py` **hard-reject** a `PendingApproval→Approved` transition (and, for offers, setting `approved_by_actor_id`) when the actor's role isn't `APPROVER` (`business_rules.md` §11); every other lifecycle service stays soft/advisory (logs an expected-role mismatch for `role_appropriateness.py` to pick up later, never blocks); `schemas/*.py` Pydantic request/response contracts (see the new API-contract section below — this is where the previously-missing schema/error-format/pagination decisions get made); `api/v1/*.py` routers: CRUD + explicit lifecycle-transition endpoints (`POST /requisitions/{id}/transition`, etc.), the validation-report endpoint, the `SystemActor` read-only reference endpoint (**explicitly documented as carrying no authentication** — `api/v1/actors.py`'s OpenAPI description must state this plainly, so role fields are never mistaken for real access control, per the explicit review requirement). |
| **Dependencies** | Phase 7 (screening/submission services must exist for the application endpoints to call). |
| **Expected files/modules** | `services/{requisition_lifecycle,application_lifecycle,scheduling,offer_lifecycle}.py`, `schemas/*.py` (one module per entity group), `api/v1/*.py` (9 routers). |
| **Deliverables** | A running `uvicorn` server; OpenAPI docs at `/docs` matching the schemas below. |
| **Acceptance criteria** | Every endpoint in the API-contract section below exists, with the documented request/response shape and error format; the two hard-enforced role checks reject bad requests with a documented error shape, not a raw 500. |
| **Tests required** | `test_api.py` (one test class per router — happy path + the hard-enforcement rejection case + at least one validation-error case per endpoint). |
| **Definition of done** | Manual exercise of each endpoint via `/docs`, cross-checked against a known seeded dataset row; `test_api.py` green. |

**STATUS: SERVICES PORTION COMPLETE** (2026-11-13); **API/schema portion not
started.** A prompt against this phase (P027 in
`prompts/claude_code_prompts.md`) explicitly scoped its work to the four
service modules only (`services/requisition_lifecycle.py`,
`application_lifecycle.py`, `scheduling.py`, `offer_lifecycle.py`) and said
nothing about `schemas/*.py` or `api/v1/*.py` — consistent with Phase 7's
own prompt, which likewise covered only its services, not an API layer.
That work is implemented exactly as scoped: both hard APPROVER gates
(`requisition_lifecycle.approve()`, `offer_lifecycle.approve()`), the
`Open`-readiness precondition (§2), the missing-feedback gate for
`Offer`/`Hired` (§6), interview scheduling/availability conflict
prevention (§6/`data_dictionary.md` §11), and the `requisition.status ==
'Open'`-at-approval precondition for offers (§7) — all reusing
`validation/rules/lifecycle_transitions.py`'s legal-edge sets verbatim,
never redefining the transition graphs. `tests/test_lifecycle.py` (31
tests, controlled fixtures) covers valid/invalid transitions for all
three lifecycles, the missing-feedback gate, scheduling conflicts and
availability, salary-band enforcement, both hard-gate-bypass-by-direct-
call cases, and transaction-rollback-leaves-no-partial-state for all four
services. Full suite: 240 passed, 0 failed (209 pre-existing + 31 new).
`schemas/*.py` and `api/v1/*.py` (the FastAPI backend half of this row)
remain fully outstanding — no HTTP layer exists yet; a future prompt
against the remainder of this phase is expected before Phase 9 starts.

## Phase 9 — Analytics and exports

| Attribute | Detail |
|---|---|
| **Objective** | Read-only aggregation endpoints and verified export consistency (`VAL-16`). |
| **Tasks** | `analytics/funnel.py`, `analytics/anomaly_summary.py` — Pandas aggregations, each with its calculation documented in the API-contract section below (dashboard metrics must have a defined calculation, per the explicit review requirement); `validation/rules/export_consistency.py` (`VAL-16`, `validation_strategy.md` §20) actually implemented and run against Phase 5's exports for the first time. |
| **Dependencies** | Phase 3/5 (data must exist); does not depend on Phase 7/8 completing, only on not conflicting with their file ownership (`analytics/` never writes to the DB — `architecture.md` §2). |
| **Expected files/modules** | `analytics/funnel.py`, `analytics/anomaly_summary.py`, `validation/rules/export_consistency.py`. |
| **Deliverables** | `api/v1/analytics.py` serving the defined metrics; `VAL-16` passing against real export files for the first time. |
| **Acceptance criteria** | Every metric listed in the API-contract section below returns a value computable by hand from the known seeded dataset, and matches. |
| **Tests required** | `test_analytics.py` (one test per defined metric, against the seeded dataset's known values), `test_export_consistency.py` (round-trip + SQL-replay + cross-run byte-identity). |
| **Definition of done** | `test_analytics.py` and `test_export_consistency.py` green. |

## Phase 10 — React + TypeScript + Vite frontend

| Attribute | Detail |
|---|---|
| **Objective** | A working dashboard against the frozen Phase 8/9 API, with zero business logic duplicated client-side. |
| **Tasks** | Typed API client (`frontend/src/api/`) generated or hand-written against the OpenAPI schema from Phase 8; pages: Requisitions, Pipeline (funnel view), Interviews (scheduling/availability), Offers, Analytics (Recharts), Anomalies (validation report + ground-truth dev view — the latter explicitly dev-only, not part of the operational UI, since it displays ground truth that production users should not see as a "feature"). |
| **Dependencies** | Phase 8 (API contract must be frozen) and Phase 9 (analytics metrics must exist to display). |
| **Expected files/modules** | `frontend/src/api/`, `frontend/src/pages/*.tsx`, `frontend/src/components/`, `frontend/src/charts/`. |
| **Deliverables** | `npm run dev` serves a working dashboard. |
| **Acceptance criteria** | Every number rendered on every page is a direct, unmodified render of an API response field — no client-side recomputation of a score, decision, or anomaly flag (verified by code review: no scoring/decision logic exists anywhere under `frontend/src/`). |
| **Tests required** | Minimal frontend integration tests (page renders without error against a mocked API response matching the Phase 8 schema); this is explicitly the lowest-priority test tier (§5/§7 — frontend correctness is not where this project's mandatory requirements live). |
| **Definition of done** | Manual walkthrough of each page in a browser, confirmed against `workflow.md`'s flows. |

## Phase 11 — Integration testing, documentation, and submission

| Attribute | Detail |
|---|---|
| **Objective** | A publicly reviewable, reproducible submission. |
| **Tasks** | Full-stack smoke test: starter-mode generation → validation → API startup → one frontend page load, end to end, in one script; full-mode generation + validation run, timed, to confirm the 72-hour budget actually closes (§9 below); `README.md` finalized (setup, run, generate, test, demo commands — all free/local, no external accounts); confirm `prompts/` is current (see the disclosure-staleness gap flagged in this review — §10 below) rather than recreating it; commit the starter dataset + its `GenerationRun` manifest as reproducibility evidence; `git init` (if not already), meaningful incremental commit history, push to a public GitHub repo. |
| **Dependencies** | Every prior phase. |
| **Expected files/modules** | `scripts/smoke_test.sh`, final `README.md`, committed `backend/data/exports/` (starter mode only — full mode is regeneratable, not committed, to keep repo size sane). |
| **Deliverables** | A clone-and-run submission satisfying brief §9's checklist. |
| **Acceptance criteria** | A reviewer who has never seen this project can clone the repo, follow `README.md`, regenerate the starter dataset, run the test suite, and see the dashboard — with no step requiring information not in the repo. |
| **Tests required** | The full-stack smoke test itself is the test; plus a final full run of every test suite from every prior phase, green, in one CI-style invocation. |
| **Definition of done** | Final read-through against the YottaFlex submission checklist (brief §9) before making the repo public; **every claim made in the README or submission narrative is backed by a test that actually ran** — not by a design projection (the §22 lesson generalized: Phase 6 onward, "expected" language must become "measured" language once code exists). |

## Table-to-module mapping (all 22 tables, new this pass)

| Table | Model module (Phase 2) | PK | Key FK dependencies | Constraints/indexes | Owning service (writes) | Key validation rule(s) | Test(s) |
|---|---|---|---|---|---|---|---|
| Department | `models/department.py` | `department_id` | — | unique name/cost_center | generator only (reference data) | VAL-01..04 | `test_models.py` |
| JobRequisition | `models/requisition.py` | `requisition_id` | department_id, requested_by_actor_id | — | `services/requisition_lifecycle.py` | VAL-01..04, 07a, 09 | `test_models.py`, `test_business_rules.py` |
| Candidate | `models/candidate.py` | `candidate_id` | — | unique email | generator only | VAL-01..04 | `test_models.py` |
| Application | `models/application.py` | `application_id` (derived) | candidate_id, requisition_id, resume_artifact_id, latest_screening_run_id | derived-PK uniqueness | `services/application_submission.py`, `services/screening.py` | VAL-01..05, 07b, 11 | `test_models.py`, `test_business_rules.py` |
| ResumeArtifact | `models/candidate.py` | `resume_artifact_id` | candidate_id | one `is_latest` per candidate | generator only | VAL-01..04 | `test_models.py` |
| Skill | `models/skill.py` | `skill_id` | — | unique name | generator only (reference data) | VAL-01..04 | `test_models.py` |
| CandidateSkill (bridge, counted once — one of the 12, not a 13th) | `models/skill.py` | (candidate_id, skill_id) | candidate_id, skill_id | composite PK | generator only | VAL-01..04 | `test_models.py` |
| ScreeningRule | `models/screening.py` | `screening_rule_id` | requisition_id | `uq_screeningrule_current`, weight-sum=100 | generator + a future "redefine rule" service (not built — not exercised by this dataset) | VAL-01..05 | `test_models.py`, `test_business_rules.py` |
| Interview | `models/interview.py` | `interview_id` | application_id, interviewer_id | — | `services/scheduling.py` | VAL-01..04, 06 | `test_models.py`, `test_validation.py` |
| Interviewer | `models/interview.py` | `interviewer_id` | department_id | unique email | generator only (reference data) | VAL-01..04 | `test_models.py` |
| Feedback | `models/interview.py` | `feedback_id` | interview_id, interviewer_id | interviewer_id must equal Interview's | `services/scheduling.py` (or a dedicated `feedback.py`) | VAL-01..04, 08 | `test_models.py`, `test_validation.py` |
| Offer | `models/offer.py` | `offer_id` | application_id, approved_by_actor_id | — | `services/offer_lifecycle.py` | VAL-01..04, 09, 10 | `test_models.py`, `test_business_rules.py` |
| JobRequisitionSkill | `models/requisition.py` | (requisition_id, skill_id) | requisition_id, skill_id | composite PK, weight-sum=100 | generator only | VAL-01..04 | `test_models.py` |
| InterviewerAvailabilitySlot | `models/interview.py` | `slot_id` | interviewer_id | — | generator only | VAL-01..04, 06 | `test_models.py` |
| RequisitionStatusHistory | `models/history.py` | `history_id` | requisition_id, actor_id | — | `services/requisition_lifecycle.py` | VAL-01..04, 07a, 14 | `test_models.py`, `test_business_rules.py` |
| ApplicationStageHistory | `models/history.py` | `history_id` | application_id, actor_id | — | `services/application_lifecycle.py` | VAL-01..04, 07b, 14 | `test_models.py`, `test_business_rules.py` |
| OfferStatusHistory | `models/history.py` | `history_id` | offer_id, actor_id | — | `services/offer_lifecycle.py` | VAL-01..04, 09, 14 | `test_models.py`, `test_business_rules.py` |
| AnomalyLabel | `models/anomaly.py` | `label_id` | entity_id (by convention) | — | `data_generation/anomalies/*.py` only — **never** `services/` or `validation/rules/` | VAL-12, VAL-15 | `test_generation_reproducibility.py`, `test_no_ground_truth_leakage` |
| GenerationRun | `models/anomaly.py` | `run_id` | generated_by_actor_id | — | `data_generation/generator.py` only | VAL-13 | `test_generation_reproducibility.py` |
| SystemActor | `models/actor.py` | `actor_id` | department_id (nullable) | unique email | generator only (reference data) | VAL-01..04, 14 | `test_models.py` |
| ApplicationSubmissionAttempt | `models/application.py` | `attempt_id` | canonical_application_id, candidate_id, requisition_id, duplicate_of_attempt_id, ground_truth_label_id | `uq_attempt_canonical`, check constraint | `services/application_submission.py` | VAL-01..04, 11 | `test_models.py`, `test_business_rules.py` |
| ScreeningRun | `models/screening.py` | `screening_run_id` | application_id, screening_rule_id | `uq_screeningrun_latest` | `services/screening.py` | VAL-01..05 | `test_models.py`, `test_business_rules.py` |

## API and frontend contract (new, this pass — closes a real gap)

**Gap found:** no document previously specified request/response schemas, error
format, or pagination — "build the API" was under-specified. Specified now, to be
implemented in Phase 8/9:

- **Request/response schemas**: one Pydantic model pair per entity in `schemas/`,
  1:1 with `data_dictionary.md`'s field tables — the schema *is* the data
  dictionary's field list, not a separate design.
- **Error format**: a single consistent shape,
  `{"error": {"code": str, "message": str, "field": str | null}}`, returned for
  every 4xx/5xx — including the hard role-enforcement rejections (Phase 8), which
  return `code="role_not_permitted"`, not a generic 500.
- **Pagination/filtering**: list endpoints (`GET /applications`, `GET /interviews`,
  etc.) accept `?limit=&offset=&status=` — simple offset pagination, no cursor
  complexity, consistent with "avoid unnecessary abstraction" (`architecture.md`
  §8).
- **Dashboard metrics, defined calculations** (Phase 9): funnel conversion rate =
  count at stage N / count at stage N-1; time-in-stage = mean(`changed_at` deltas
  per `ApplicationStageHistory` pair); offer acceptance rate = count(`Accepted`) /
  count(`Extended`); anomaly summary = per-category counts from the **live
  validation report**, never from `AnomalyLabel` directly (`workflow.md` §8).
- **No business logic in the frontend**: confirmed as an explicit Phase 10
  acceptance criterion (code review: zero scoring/decision logic under
  `frontend/src/`).
- **Database writes only through service-layer operations**: confirmed —
  `api/v1/*.py` routers never construct a SQLAlchemy session write directly; every
  write goes through a `services/` function (`architecture.md` §6).
- **Analytics/exports as read-only consumers**: confirmed — `analytics/` and
  `data_generation/export.py` never write to the live database.

## P0 / P1 / P2 classification (new, this pass)

| Priority | Scope |
|---|---|
| **P0 — essential** | Phases 1–6: project setup, schema, deterministic generation, validation engine, anomaly injection, detection+evaluation. Without these, there is no valid submission — the data model and its correctness are the actual deliverable the brief is testing. |
| **P0 — essential** | Phase 7: screening + duplicate-submission services — the two most heavily-specified business rules in this project's history (17 of this project's prompts touched these two areas). |
| **P1 — important** | Phase 8 (workflow + API) and Phase 9 (analytics + exports) — needed for a *strong* submission (demonstrable workflow, YottaFlex §9's "executable code"), but a submission with a correct, validated, exported dataset and no API would still satisfy the *data* requirements, just not demonstrate them interactively. |
| **P1 — important** | Phase 10's core pages (Pipeline, Anomalies) — demonstrates the two things this project is actually about (recruitment funnel, anomaly detection). |
| **P2 — optional polish** | Phase 10's remaining pages (Requisitions/Interviews/Offers CRUD views, visual styling), Recharts theming, any dashboard feature beyond rendering API data plainly. |
| **P2 — optional polish** | Anything not explicitly named in brief §2–§8 or this plan — e.g., auth UI (out of scope entirely, `PROJECT_SPEC.md` §2), notification systems, multi-tenancy. |

**What can be simplified without compromising mandatory requirements:** Phase 10
can be reduced to exactly two pages (Pipeline, Anomalies) if the 72-hour budget is
tight (§9 below) — every *other* mandated requirement (schema, generation,
validation, anomaly detection, screening, duplicate handling) has no simplification
available, since each is explicitly named in the brief. **Frontend polish must
never be allowed to delay Phases 1–7** — if time runs short, Phase 10 shrinks or is
cut to a single page proving the API works; Phases 1–7 do not shrink.

## 72-hour feasibility assessment (new, this pass)

Rough budget, assuming one person working from this plan directly (no further
architecture debate — that phase is done):

| Phases | Rough share of 72h |
|---|---|
| 1–2 (setup, schema) | ~6h |
| 3 (generation) | ~10h — the most code-dense phase (17 entity generators) |
| 4 (validation + formulas) | ~10h — 16 rule modules + 2 shared formula functions |
| 5–6 (injection, detection, evaluation) | ~8h |
| 7 (screening/dup services) | ~6h — mostly transactional wrapping, formulas already exist |
| 8 (workflow + API) | ~10h |
| 9 (analytics/exports) | ~6h |
| 10 (frontend) | ~10h if full, ~4h if reduced to 2 pages per the P2 simplification above |
| 11 (integration/docs/submission) | ~6h |
| **Total** | **~72–78h at full scope, ~66–72h with the Phase 10 reduction** |

**Verdict: tight but feasible**, provided Phase 10 is reduced the moment any
upstream phase overruns — the plan has essentially no slack at full frontend
scope. This is a plan-level estimate, not a measured result; it has not been
validated against actual implementation time.

## Repository structure (unchanged from `architecture.md` §7, cross-referenced here)

See `architecture.md` §7 for the authoritative tree (not duplicated here to avoid
two documents drifting apart). Phase-to-file mapping is given per-phase above. Key
structural commitments restated for this plan's purposes: `data_generation/` is
independently executable from the API server (`python -m data_generation.generator
--mode starter`, no `uvicorn` process required); `backend/` and `frontend/` are
fully separate npm/pip projects; `backend/data/exports/` holds the committed
starter dataset (Phase 11) and the regeneratable full dataset (gitignored).

## Submission readiness checklist (new, this pass)

| Item | Status / where it's handled |
|---|---|
| Public GitHub repo | Phase 11 |
| Meaningful incremental commits | Phase 11 (one logical commit per phase, not one giant commit) |
| README setup/run/generate/test/demo commands | Phase 11 |
| No secrets in repo | N/A — no secrets exist anywhere in this design (no auth, no API keys, `PROJECT_SPEC.md` §2) |
| Dataset generation command | Phase 3/11 |
| Validation/test commands | Phase 4/11 |
| Demo workflow | Phase 8/10 |
| Sample outputs | Phase 11 (committed starter exports) |
| Data dictionary / architecture docs | Already complete (`docs/`) |
| AI prompt history and disclosure | **Gap found, this pass** — `prompts/ai_usage_disclosure.md` and `prompts/chatgpt_prompts.md`'s review-status fields are stale (disclosure references only P001–P003 of 17 entries; several `chatgpt_prompts.md` rows are still marked "Pending user confirmation"). Not fixed in this pass — out of this prompt's scope (it names the 8 architecture docs, not `prompts/`) — flagged for a dedicated follow-up before Phase 11. |
| Known limitations and next steps | Partially covered inline across `docs/` (e.g., the salary-band-snapshot limitation, `business_rules.md` §7); should be consolidated into one README section in Phase 11 |
| Human review of generated code | Depends on the user actually reading Phase 2 onward's code, not something this plan can satisfy on its own |

## Critical business-rule implementation checklist (new, this pass)

Every item below maps to a specific task (already placed in a phase above) and a
specific test. None require new design — all are already approved; this section
exists so none can be silently skipped during implementation.

**A. Duplicate application handling**
| Rule | Task (phase) | Test |
|---|---|---|
| One canonical Application per pair | Phase 2 (derived PK) | `test_models.py::test_duplicate_application_pk_rejected` |
| ApplicationSubmissionAttempt preserves all submissions | Phase 7 | `test_business_rules.py::test_attempt_never_discarded` |
| Canonical reconciliation sorts by (submitted_at, attempt_id) | Phase 4 (formula) | `test_business_rules.py::test_reconcile_canonical_tiebreak` |
| Reconciliation is transactional | Phase 7 | `test_business_rules.py::test_reconcile_atomic_on_crash_simulation` |
| Out-of-order submissions handled correctly | Phase 7 | `test_business_rules.py::test_out_of_order_arrival_reassigns_canonical` |
| Withdrawal does not release the pair | Phase 8 (lifecycle) + Phase 7 (reconciliation) | `validation_strategy.md` §18 Test 1 |
| Later submission after withdrawal = duplicate attempt | Phase 7 | §18 Test 1/2 |
| Application remains withdrawn | Phase 8 | §18 Test 1/2 (`test_reconcile_never_touches_application_stage`) |
| Detection never reads ground_truth_label_id | Phase 4 (structural: narrow projection) | `test_no_ground_truth_leakage` |

**B. Screening**
| Rule | Task (phase) | Test |
|---|---|---|
| Weights 50/30/20 | Phase 2 (default), Phase 4 (formula) | `test_business_rules.py::test_screening_formula_examples` |
| Education is also a mandatory gate | Phase 4 | same, CAND-000104 case specifically |
| Default threshold 70.0, inclusive (`≥`) | Phase 2 (default), Phase 4 | the boundary-pair test (70.00/69.25) |
| Zero min-experience → no division by zero | Phase 4 | `test_business_rules.py::test_zero_min_experience_full_credit` |
| ScreeningRun is immutable history | Phase 2 (no UPDATE/DELETE path), Phase 7 | `test_models.py::test_screeningrun_insert_only` |
| ScreeningRun → ScreeningRule direct FK + version snapshot | Phase 2, Phase 4 | `test_business_rules.py::test_historical_rule_reproducible_after_redefinition` |
| `latest_screening_run_id` consistent with `is_latest` | Phase 7 (atomic transaction) | `test_business_rules.py::test_latest_pointer_matches_is_latest_row` |
| Screening decisions reproducible | Phase 4 | `test_business_rules.py::test_identical_inputs_identical_outputs` |

**C. Anomaly generation**
| Rule | Task (phase) | Test |
|---|---|---|
| Five categories, approved counts | Phase 5 | `test_generation_reproducibility.py::test_anomaly_counts_match_spec` |
| Baseline passes before injection | Phase 4→5 gate | the gate itself (no test "passes" a blocked phase — this is enforced by phase ordering, not a unit test) |
| Structural integrity valid after injection | Phase 6 (VAL-01/02 rerun) | `test_validation.py::test_structural_checks_zero_post_injection` |
| Ground truth never accessed by detectors | Phase 4/6 | `test_no_ground_truth_leakage` |
| Evaluation only after detection | Phase 6 (`evaluate.py` runs after, reads detection's finished output) | `test_evaluate.py` (asserts call order via the module boundary itself — `evaluate.py` imports from `validation/rules/` output, never the reverse) |
| Incident-level vs affected-entity-level counts distinct | `business_rules.md` §9b (documentation, done) | `test_business_rules.py::test_incident_vs_entity_counts` |
| Independent detection test per category | Phase 4/6 | one test per `VAL-06/08/10/11/12` |

**D. Reproducibility**
| Rule | Task (phase) | Test |
|---|---|---|
| Seed 20261022 | Phase 1 (config constant) | `test_generation_reproducibility.py` |
| Starter and full modes | Phase 3 | same |
| Generator version recorded | Phase 5 (`GenerationRun.generator_version`) | same |
| Deterministic content + checksums | Phase 3/5 | `test_same_seed_same_checksum` |
| Volatile timestamps excluded from checksums | Phase 5 (field design, `data_dictionary.md` §17) | `test_checksum_excludes_volatile_fields` |
| GenerationRun excluded from its own table checksum | Phase 5 | same |
| Ground-truth reproducibility verified separately | Phase 6 (`evaluate.py` is its own script, its own test) | `test_evaluate.py` |

**E. SystemActor and permissions**
| Rule | Task (phase) | Test |
|---|---|---|
| Role conventions implemented as documented | Phase 8 | `test_api.py` role-check tests |
| Hard vs soft distinguished | Phase 8 (two hard-enforced transitions only) | `test_business_rules.py::test_only_two_transitions_hard_enforced` |
| No implied authentication/authorization security | Phase 8 (OpenAPI description states this explicitly on `api/v1/actors.py` and anywhere a role is checked) | manual review — this is a documentation/wording requirement, not something a unit test can verify |

## Test strategy and acceptance gates — cross-reference (new, this pass)

The 16 test categories named in the review map onto the phases above as follows
(★ = gate that must pass before the next phase starts):

| Test category | Phase | Gate? |
|---|---|---|
| Model and schema tests | 2 | ★ |
| PK/FK and constraint tests | 2 | ★ |
| Generator determinism tests | 3 | ★ |
| Baseline validation tests | 4 | ★ (zero violations) |
| Anomaly injection tests | 5 | ★ |
| Ground-truth leakage tests | 4 (vacuous), 6 (meaningful) | ★ at 6 |
| Duplicate reconciliation tests | 4 (formula), 7 (service) | ★ at 7 |
| Withdrawal/resubmission tests | 7 | ★ |
| Screening formula and boundary tests | 4 (formula), 7 (service) | ★ at 7 |
| Screening history immutability tests | 2 (schema), 7 (service) | ★ at 7 |
| Workflow transition tests | 8 | ★ |
| API tests | 8 | ★ |
| Export round-trip tests | 9 | ★ |
| Checksum tests | 5 | ★ |
| Frontend integration tests | 10 | not a hard gate — P2 priority, §7 |
| Full starter-mode smoke test | 11 | ★ (final) |
| Full-mode generation and validation test | 11 | ★ (final) |

No test execution is claimed anywhere in this document — every result named above
is a planned test, not a reported outcome.

## Open sequencing question — RESOLVED, this pass

Previously open: "Phases 4 and 5 both need the screening/scheduling/lifecycle
formulas — stub-and-reuse, or merge the phases?" **Resolved: Option A, adopted.**
The shared pure-function formulas (`compute_screening_score`,
`reconcile_canonical`) are built once, in Phase 4, with no DB/HTTP dependency, and
imported unchanged by Phase 7's live services. This was always the recommended
option; it is now the committed plan, not an open question carried forward again.
