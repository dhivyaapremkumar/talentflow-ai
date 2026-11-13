# Architecture

**Revision 2** — reflects `SystemActor`, `ApplicationSubmissionAttempt`, the derived
`Application` ID, and the corrected 21-table count throughout.

**Second verification pass** — adds `ScreeningRun` (22 tables total), confirms the
five-step generation-and-verification pipeline (§4), and confirms `ScreeningRun`
carries no ground-truth pointer (§5).

**Implementation-detail clarification pass** — `ScreeningRule` becomes
versioned/insert-only with a direct `ScreeningRun.screening_rule_id` FK (§8);
duplicate-attempt and screening-run uniqueness are now backed by named partial unique
indexes, not just application-level discipline (§8).

**Screening/decision logic verification pass** — §8 adds one decision-table row for
the education scoring/gating resolution.

**Final approval pass (this revision)** — §8's education row marked APPROVED; one
new row for the explicit default-threshold documentation decision.

## 1. System overview

```
┌─────────────────────────┐        ┌──────────────────────────────────────┐
│  React + TS + Vite SPA   │  HTTP  │              FastAPI backend          │
│  (Recharts dashboards)   │◄──────►│                                        │
└─────────────────────────┘  JSON  │  api/        — routers (thin)          │
                                     │  services/   — business rules,        │
                                     │                lifecycle transitions, │
                                     │                screening calc         │
                                     │  analytics/  — SQL + Pandas reports    │
                                     │  validation/ — rule engine, checksums  │
                                     │  db/models/  — SQLAlchemy ORM          │
                                     │  schemas/    — Pydantic I/O models     │
                                     └──────────────┬─────────────────────────┘
                                                     │
                                            ┌────────▼─────────┐
                                            │  SQLite database  │
                                            │  talentflow.db     │
                                            └────────┬─────────┘
                                                     │
                                     ┌───────────────▼────────────────────────┐
                                     │  data_generation/ (offline, standalone) │
                                     │  entities/  — per-entity generators    │
                                     │  anomalies/ — anomaly injectors         │
                                     │  export.py  — CSV / JSON / SQL dumps   │
                                     │  checksums.py — reproducibility proof  │
                                     └──────────────────────────────────────┘
```

The data generator is a standalone CLI module, not an API-triggered process. It writes
directly to SQLite (and to `data/exports/{csv,json,sql}`) and is run before the API
server starts. This keeps "how data is created" fully decoupled from "how data is
served," per brief §8 ("separate data generation, database models, business rules,
APIs and frontend").

## 2. Layering and responsibility boundaries

| Layer | Responsibility | Must NOT do |
|---|---|---|
| `data_generation/` | Deterministic baseline + anomaly synthesis, export, checksum manifest | Import from `api/` or `services/`; must be runnable with zero API/db-session dependency beyond the ORM models |
| `db/models/` | SQLAlchemy table definitions, FK/constraint declarations, enums | Contain business logic (e.g., no score calculation inside a model method) |
| `schemas/` | Pydantic request/response contracts, field-level validation (types, ranges, allowed values) | Contain cross-entity logic (e.g., no "does this interviewer have a conflict" check here) |
| `services/` | Business rules: lifecycle transitions, screening score formula, scheduling-conflict checks, offer-approval rules, salary-band checks, submission-attempt handling | Contain HTTP concerns (status codes, request parsing) |
| `validation/` | Batch/offline rule engine — the 13 mandated validation categories plus role-appropriateness (`validation_strategy.md`), reconciliation, checksum verification | Mutate data (read-only engine; it reports, `services/` fixes) |
| `analytics/` | Pandas/SQL aggregations for dashboards (funnel, time-to-hire, offer acceptance rate, anomaly summaries) | Write to the database |
| `api/` | FastAPI routers: request parsing, calling into `services/`/`analytics/`, HTTP status mapping | Contain business logic directly in a route function |
| `frontend/` | Presentation, charts, forms | Compute business rules client-side (e.g., no screening score math in TS — it only renders what the API returns) |

## 3. Why SQLite + SQLAlchemy

- Free, zero-install, file-based — satisfies "free, locally runnable dependencies only"
  and makes the repo trivially cloneable/runnable for YottaFlex reviewers.
- A single `.db` file is itself a reproducibility artifact: the committed starter DB can
  be diffed/checksummed directly.
- SQLAlchemy gives explicit FK/constraint declarations (needed for the FK-integrity and
  PK-uniqueness validation categories) while staying swappable to Postgres later without
  touching `services/`/`api/` (not planned, but it's a free property of using an ORM
  instead of raw `sqlite3`).

## 4. Determinism strategy (updated for the derived Application ID)

Every source of randomness in `data_generation/` is seeded from a single
`base_seed = 20261022`. Each entity generator derives its own child seed
deterministically (`child_seed = hash((base_seed, entity_name)) mod 2**32`) rather than
sharing one global `random.Random()` instance, so adding/removing an unrelated entity
generator later cannot shift the random stream of entities generated before it.

IDs are assigned in a fixed, documented generation order, never from DB autoincrement:

```
Department → SystemActor → Skill → Interviewer → InterviewerAvailabilitySlot →
JobRequisition → JobRequisitionSkill → ScreeningRule →
Candidate → ResumeArtifact → CandidateSkill →
Application (ID derived, not counted — see below) → ApplicationSubmissionAttempt →
ScreeningRun → Interview → Feedback → Offer →
[baseline-integrity validation gate — see pipeline below] →
anomaly injection pass (each injector writes its own AnomalyLabel row(s) as part of
the same step — see note below) → history backfill (RequisitionStatusHistory,
ApplicationStageHistory, OfferStatusHistory) → GenerationRun
```

**`ScreeningRun`'s place in this order:** it sits right after
`ApplicationSubmissionAttempt`, mirroring how `services/screening.py` actually runs
in the live workflow (`workflow.md` §3) — an `Application` row is inserted first with
minimal fields (`stage=Applied`, `latest_screening_run_id=NULL`), then its
`ScreeningRun` row is inserted (needs `application_id` to already exist), then the
`Application` row is updated to mirror that run's results and advance `stage`. This
two-phase write is not new complexity introduced by `ScreeningRun` — it's the same
insert-then-update sequencing `Application.stage` already needed regardless.

**Confirmed five-step generation-and-verification pipeline (this pass — see
`business_rules.md` §13 for full detail):**
```
1. Generate valid baseline data        (everything through Offer/ScreeningRun above)
2. Validate baseline structural integrity  (all 13+1 rule modules — must be zero violations)
3. Inject labelled anomalies           (AnomalyLabel written inline per injector — see below)
4. Run anomaly detection, independent of ground truth  (same rule modules, rerun)
5. Compare detected anomalies against AnomalyLabel     (offline, diagnostic only)
```
Step 2 is a named, explicit gate added in this pass — if the clean baseline fails any
of the 13 mandated categories, generation aborts rather than proceeding to inject
anomalies on top of a broken baseline; this makes any later violation attributable to
an intentional anomaly, not a generator bug, by construction rather than by
assumption.

**Audit correction (carried from the prior pass):** earlier wording placed
`AnomalyLabel` as a separate, later global step after "anomaly injection pass" in
this diagram. That would leave
`ApplicationSubmissionAttempt.ground_truth_label_id` (business_rules.md §9, type 2)
pointing at an `AnomalyLabel` row that doesn't exist yet at the moment the duplicate
attempt is inserted — a real FK-ordering problem, not just a wording nit. Each
anomaly injector now explicitly writes its own `AnomalyLabel` row(s) in the same step
it mutates or adds the anomalous row, so every such FK resolves immediately. This is a
sequencing clarification only — it changes no entity, field, or count.

**`Application` is the one table whose ID is *derived*, not sequentially counted:**
`application_id = f"APP-{requisition_id}-{candidate_id}"`. Because both
`requisition_id` and `candidate_id` are themselves already-deterministic sequential
IDs assigned earlier in this order, `application_id` is still 100% reproducible under
the fixed seed — it just isn't assigned by an incrementing counter the way the other 21
tables' PKs are. This also means `Application` rows can be (and are) created in
`(requisition_id, candidate_id)` iteration order rather than literal submission-time
order; the submission timeline itself is reconstructed afterward through
`ApplicationSubmissionAttempt.submitted_at`, not through `Application`'s own insertion
order.

A `checksums.py` pass hashes each of the 22 exported tables and records it in a
`GenerationRun` manifest row, attributed to a `SYSTEM_ADMINISTRATOR`-role `SystemActor`
via `generated_by_actor_id` — this is the evidence artifact for "deterministic
reproducibility using checksums" (brief §6).

## 5. Anomaly isolation (one deliberate, narrow exception added in Rev 2)

`AnomalyLabel` (ground truth) lives in its own table and its own export file
(`anomaly_labels.{csv,json}`), keyed by `(entity_type, entity_id, anomaly_type)`. No
operational table has a generic `is_anomaly` column. Consequences of this design,
stated explicitly:
- Anomaly-detection logic in `validation/` must re-derive each anomaly from first
  principles (e.g., actually checking interviewer availability overlap, or actually
  grouping submission attempts by candidate+requisition), then the detection output is
  compared against `AnomalyLabel` **only** in a separate evaluation step, never during
  detection itself.
- This is the mechanism that satisfies "never use ground truth as a feature in anomaly
  detection" (brief §5) structurally, not just by convention.

**The one exception, requested in review:**
`ApplicationSubmissionAttempt.ground_truth_label_id` is a nullable FK pointing *from*
an operational row *to* `AnomalyLabel`, added for audit traceability on the duplicate-
submission anomaly specifically. This does not weaken the isolation principle: the
field exists on the row, but the duplicate-detection function
(`business_rules.md` §10) is written to accept only a narrow projection of the table's
columns that excludes `ground_truth_label_id` entirely, so it is physically incapable
of reading it, not merely asked nicely not to. A test over the module's import graph
and function signature enforces this, generalized in this pass to cover all of
`services/` and `validation/rules/`, not just the one duplicate-detection module
(`validation_strategy.md` §17). No other operational table was given an equivalent
pointer, to keep this exception as narrow as the review's request — confirmed
explicitly for `ScreeningRun` in this verification pass: it has no ground-truth
column of any kind, so screening is structurally, not just conventionally,
unrelated to anomaly ground truth.

## 6. Module boundaries inside the backend (import direction)

```
api/  →  services/  →  db/models/
api/  →  analytics/  →  db/models/
api/  →  validation/ →  db/models/
services/  →  db/models/   (never the reverse)
data_generation/  →  db/models/   (never into api/ or services/)
```
`services/`, `analytics/`, and `validation/` do not import each other — if validation
needs a business-rule formula (e.g., the screening score formula, or the duplicate-
submission grouping logic), that formula is defined once in `services/` and imported by
both `services/` and `validation/`, so the rule is never duplicated or allowed to drift
between "how it's computed" and "how it's checked."

## 7. Proposed directory structure (updated for `SystemActor` / `ApplicationSubmissionAttempt`)

```
TalentFlowAI/
├── README.md
├── LICENSE
├── .gitignore
├── docs/
│   ├── PROJECT_SPEC.md
│   ├── architecture.md
│   ├── data_dictionary.md
│   ├── entity_relationships.md
│   ├── business_rules.md
│   ├── workflow.md
│   ├── validation_strategy.md
│   └── implementation_plan.md
├── prompts/                              # YottaFlex: auditable AI-usage record — created; see prompts/README.md
│   ├── README.md
│   ├── claude_code_prompts.md
│   ├── chatgpt_prompts.md
│   └── ai_usage_disclosure.md
├── backend/
│   ├── pyproject.toml
│   ├── app/
│   │   ├── main.py
│   │   ├── config.py
│   │   ├── db/
│   │   │   ├── base.py
│   │   │   ├── session.py
│   │   │   └── models/                   # 22 tables total — entity_relationships.md §1
│   │   │       ├── department.py
│   │   │       ├── actor.py              # SystemActor (new, Rev 2)
│   │   │       ├── requisition.py        # JobRequisition, JobRequisitionSkill
│   │   │       ├── candidate.py          # Candidate, ResumeArtifact
│   │   │       ├── skill.py              # Skill, CandidateSkill
│   │   │       ├── application.py        # Application (derived ID), ApplicationSubmissionAttempt (new, Rev 2)
│   │   │       ├── screening.py          # ScreeningRule (versioned/insert-only) + ScreeningRun (direct FK to it)
│   │   │       ├── interview.py          # Interviewer, InterviewerAvailabilitySlot, Interview, Feedback
│   │   │       ├── offer.py
│   │   │       ├── history.py            # RequisitionStatusHistory, ApplicationStageHistory, OfferStatusHistory — still exactly 3
│   │   │       └── anomaly.py            # AnomalyLabel, GenerationRun
│   │   ├── schemas/                      # mirrors db/models, 1:1 Pydantic contracts
│   │   ├── api/v1/
│   │   │   ├── departments.py
│   │   │   ├── requisitions.py
│   │   │   ├── candidates.py
│   │   │   ├── applications.py           # includes the submission-attempt endpoint
│   │   │   ├── interviews.py
│   │   │   ├── offers.py
│   │   │   ├── actors.py                 # SystemActor read endpoints (no auth)
│   │   │   ├── analytics.py
│   │   │   └── validation.py
│   │   ├── services/
│   │   │   ├── requisition_lifecycle.py  # enforces APPROVER on PendingApproval→Approved (hard, this pass)
│   │   │   ├── application_submission.py # new: canonical-ID derivation + attempt logging
│   │   │   ├── application_lifecycle.py
│   │   │   ├── screening.py              # explanation-string generation + ScreeningRun insert (this pass)
│   │   │   ├── scheduling.py
│   │   │   └── offer_lifecycle.py        # enforces APPROVER on PendingApproval→Approved (hard, this pass)
│   │   ├── analytics/
│   │   │   ├── funnel.py
│   │   │   └── anomaly_summary.py
│   │   └── validation/
│   │       ├── rules/                    # one module per validation category, incl. role_appropriateness.py
│   │       ├── reconcile.py
│   │       └── checksums.py
│   ├── data_generation/
│   │   ├── generator.py                  # entrypoint: --mode starter|full --seed
│   │   ├── seeding.py                    # child-seed derivation
│   │   ├── entities/                     # one module per entity, in the §4 generation order
│   │   ├── anomalies/                    # one module per anomaly type
│   │   ├── export.py
│   │   └── checksums.py
│   ├── data/
│   │   ├── talentflow.db
│   │   └── exports/{csv,json,sql}/
│   └── tests/
│       ├── test_models.py
│       ├── test_business_rules.py
│       ├── test_validation.py
│       ├── test_generation_reproducibility.py
│       └── test_api.py
├── frontend/
│   ├── package.json
│   ├── vite.config.ts
│   └── src/
│       ├── main.tsx
│       ├── App.tsx
│       ├── api/                          # typed fetch client
│       ├── pages/                        # Requisitions, Pipeline, Interviews, Offers, Analytics, Anomalies
│       ├── components/
│       ├── charts/                       # Recharts wrappers
│       └── types/
└── scripts/
    ├── setup.sh / setup.ps1
    ├── seed_db.py
    └── reconcile.py
```

**As actually built (Phase 11 note, added rather than silently left
inconsistent):** the module boundaries above (`analytics/`, `validation/rules/`,
`data_generation/{entities,anomalies}`, `services/`, `api/v1/`, `schemas/`)
all match exactly. Differences from this "proposed" tree, each already
documented at the phase that introduced it: `backend/data/` holds
`talentflow_starter.db`/`talentflow_full.db`, never a bare `talentflow.db`
(README's Setup section); exports are `exports/{starter,full}/` — CSV + two
JSON summary files, no SQL export format was ever built
(`export_consistency.py`'s own docstring flags this as deferred, not an
oversight); `backend/tests/` has ten files reflecting the real phase-by-phase
split (`test_models.py`, `test_data_generation.py`, `test_validation.py`,
`test_anomaly_injection.py`, `test_phase6_detection_evaluation.py`,
`test_services.py`, `test_lifecycle.py`, `test_analytics.py`, `test_api.py`,
`test_config.py`) rather than the four named here; `frontend/src/` additionally
has `context/` (actor/toast state) and `hooks/`, and `pages/` is organized by
feature folder (`requisitions/`, `screening/`, `interviews/`, `offers/`, plus
a top-level `Dashboard.tsx`) rather than one flat `Pipeline`/`Analytics`/
`Anomalies` page split — the approved 5-screen scope (`implementation_plan.md`
Phase 10) folds funnel/anomaly analytics into the Executive Dashboard instead
of separate pages; no repo-root `scripts/` directory exists — the README
documents the actual generation/startup commands directly instead.
## 8. Key architectural decisions and why

| Decision | Why | Alternative considered |
|---|---|---|
| SQLite over Postgres | Zero-install, file is itself a shippable artifact | Postgres — rejected: needs a running service, against "locally runnable, no unnecessary complexity" |
| Business rules in a `services/` layer, not in ORM models or route handlers | Keeps rules unit-testable without HTTP or DB-session mocking, and reusable by `validation/` | "Fat model" (rules as model methods) — rejected: `validation/` would need to instantiate full ORM objects just to re-check a rule |
| Anomalies as mutation/addition of rows within the mandated totals (A-5) | Keeps total counts exactly matching the mandated volumes | Generate N valid + M anomalous on top — rejected: silently inflates the mandated counts |
| Ground truth in a separate table/export | Structurally prevents leakage into detection logic (§5) | `is_anomaly` flag column on every operational table — rejected: too easy for detection code to accidentally read it |
| `Application.application_id` derived from `(requisition_id, candidate_id)` **(Rev 2)** | Makes "no duplicate Application for one pair" a structural PK guarantee instead of a soft validation rule | Keep the Rev 1 sequential ID and a soft uniqueness check — rejected per review: it let a duplicate anomaly be represented as a second row sharing an informally-unique key, which review flagged as a conflict risk |
| `ApplicationSubmissionAttempt` as a separate audit-trail table **(Rev 2)** | Preserves every submission event, including duplicates, without ever needing a colliding PK or a discarded row | Store a `submission_count` field on `Application` — rejected: loses per-attempt timestamps and can't support an independent detection algorithm |
| `SystemActor` with 5 roles, no auth **(Rev 2)** | Gives approvals/audit records real FK attribution (brief capability 1 & 10) without building authentication | Free-text `actor_name` (Rev 1) — superseded: couldn't be joined/queried; a full `User`+auth system — rejected as scope creep for a system explicitly excluding authentication |
| `ScreeningRun` as a dedicated, insert-only table **(this pass, supersedes the row below)** | Gives every screening execution a real, queryable PK; stronger immutability guarantee than JSON; doesn't violate "three history tables" since it's a result-log, not a status-transition log (`entity_relationships.md` §4a) | JSON-array `screening_history` on `Application` (Rev 2) — retired: no queryable run identity, no DB-level protection against in-place rewriting |
| ~~Screening history as JSON-on-`Application` (Rev 2)~~ | ~~Satisfies "preserve previous screening decisions" while keeping the history-table count at exactly 3~~ | Superseded by the row above, this pass — kept here for the audit trail, not as current design |
| Hard-enforce `APPROVER` role on requisition/offer approval only **(this pass)** | "Approvals" is a brief-named capability (1 and 9) where a role mismatch is a correctness issue, not just hygiene; every other transition stays soft to avoid rigidity no requirement asked for | Hard-enforce all role conventions — rejected: over-constrains routine workflow steps in a system with no real authentication to back broader access control |
| `ScreeningRule` made versioned/insert-only with `is_current`, `ScreeningRun.screening_rule_id` a direct FK **(this pass)** | The only way a historical `ScreeningRun` stays reproducible after the current rule is redefined — the FK target must never be mutated | Keep `ScreeningRule` mutable and add only `screening_rule_id` — rejected: the FK would point at a row whose criteria could change underneath it, defeating the reproducibility goal the field exists for |
| Duplicate-attempt/screening-run uniqueness enforced by named partial unique indexes, not application discipline alone **(this pass)** | Makes "at most one canonical attempt" / "at most one latest run" structurally impossible to violate, matching how `Application`'s PK already enforces its own uniqueness guarantee | Rely on service-layer discipline alone, checked only by validation after the fact — rejected: weaker guarantee, inconsistent with the structural-integrity-first principle (A-10) used everywhere else |
| Education scored *and* gated, via a graded `education_component` plus an unchanged independent hard gate **(APPROVED)** | Resolves an asymmetry (skill/experience were graded, education was gate-only); mirrors the existing `experience_component` capping philosophy exactly, so it's not a new concept | Make education score-only (drop the gate) — rejected: brief explicitly asks for an "eligibility gate" on education specifically; dropping it would silently relax a requirement |
| Default `pass_threshold_score=70.0`, documented explicitly rather than left as "per-rule, no stated default" **(this pass)** | Requirement 5 of the final approval explicitly asked for a documented default; without one, the generator had no stated basis for what value to assign | Leave it fully open per-rule with no default — rejected: would under-specify the generator, same category of gap as the earlier undocumented `screening_run_id` (A-16) |
