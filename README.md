# TalentFlow AI

Recruitment operations and decision-intelligence system — YottaFlex AI Associate
Forward Deployed Engineer challenge submission.

**Status: Phases 1-10 complete; Phase 11 (final integration, verification, and
submission readiness) in progress.** The 22-table schema, the deterministic
data generator, the validation/anomaly-detection engine, anomaly injection,
independent detection + offline evaluation, the screening/submission/
lifecycle/scheduling/offer service layer, a minimal FastAPI HTTP layer, and a
5-screen React dashboard (Executive Dashboard, Requisitions & Applications,
Screening & Candidate Profile, Interview Management, Offers & Decision
Intelligence) are all implemented and tested (290 backend tests passing). The
setup instructions below have been verified end-to-end from a genuinely fresh
`git clone` (new venv, new `npm install`, no reused state) — see
`docs/implementation_plan.md` for the full phase-by-phase plan and current
progress.

## What this is

A deterministic, seed-reproducible synthetic recruitment dataset (22 tables),
a validation/anomaly-detection engine, and a FastAPI + React application over
it. Full design rationale, data dictionary, business rules, and validation
strategy are in `docs/`. The complete record of prompts used to build this
project, and an AI-usage disclosure, are in `prompts/`.

## Repository layout

```
docs/               Architecture, data dictionary, business rules, validation
                     strategy, implementation plan (read these first)
prompts/             Verbatim AI prompt history and usage disclosure
backend/             Python 3.12 / FastAPI / SQLAlchemy backend + data generator
frontend/            React + TypeScript + Vite dashboard
```

## Setup

Requires Python 3.12 and Node.js 20+. Follow this order on a fresh clone —
the backend API server needs a generated database to serve, and the
frontend needs the backend running: generate data, then start the backend,
then start the frontend.

### 1. Backend environment

```bash
cd backend
py -3.12 -m venv .venv
.venv/Scripts/python.exe -m pip install --upgrade pip
.venv/Scripts/python.exe -m pip install -e ".[dev]"
```

Verify:
```bash
.venv/Scripts/python.exe -m pytest tests/ -v
```

No `.env` file is required to run — `backend/.env.example` documents the only
two configuration values (`DATABASE_PATH`, `DATASET_MODE`), and this project
has no authentication and no paid external services, so there are no secrets
to configure.

### 2. Generate the starter dataset

Still from `backend/`:

```bash
.venv/Scripts/python.exe -m app.data_generation.generator --mode starter
```

Writes `backend/data/talentflow_starter.db` (150 applications), plus CSV/JSON
exports to `backend/data/exports/starter/`, and prints baseline validation
(expected: 0 violations, 0 warnings) and post-injection validation (expected:
11 violations, broken out by rule ID — the seeded anomaly counts from
`business_rules.md` §9). **This step is required before starting the
backend** — the API server's default `DATABASE_PATH` points at exactly this
file, and it refuses to start serving data (a clear `database_not_configured`
error, not a silent empty database) until it exists.

### 3. Start the backend API server

Still from `backend/`:

```bash
.venv/Scripts/python.exe -m uvicorn app.main:app --reload
# then: curl http://127.0.0.1:8000/health
# and:  curl http://127.0.0.1:8000/api/v1/requisitions
```

No environment variable is needed — `DATABASE_PATH` defaults to
`backend/data/talentflow_starter.db` (resolved from the backend directory,
not the shell's current working directory, so this works the same regardless
of where `uvicorn` is launched from). To serve a different database instead
(e.g. the full-mode one generated below), set `DATABASE_PATH` explicitly
before starting uvicorn — either absolute, or relative to `backend/`:

```bash
DATABASE_PATH=data/talentflow_full.db .venv/Scripts/python.exe -m uvicorn app.main:app --reload
```

### 4. Start the frontend

In a separate terminal:

```bash
cd frontend
npm install
npm run dev
```

Open the printed `localhost` URL (typically `http://localhost:5173`) — the
dashboard renders real data read live from the backend API started in step 3.

### Optional: full-scale dataset

```bash
cd backend
.venv/Scripts/python.exe -m app.data_generation.generator --mode full
```

Writes `backend/data/talentflow_full.db` (3,000 applications) and
`backend/data/exports/full/` (regeneratable, gitignored — unlike the
committed `starter/` exports). Point the backend at it as shown in step 3
above to browse the full-scale dataset in the dashboard instead of starter.

```bash
# Independent anomaly detection + offline ground-truth evaluation
# (reads whichever database was just generated):
.venv/Scripts/python.exe -m app.validation.evaluate --mode starter
.venv/Scripts/python.exe -m app.validation.evaluate --mode full
```

Writes a JSON report to `backend/data/evaluation_reports/<mode>.json` and
prints a per-anomaly-type TP/FP/FN/precision/recall/F1 table (expected:
precision = recall = F1 = 1.00 for every type, both modes — exact match
against the isolated `AnomalyLabel` ground truth, never used as a detection
input; see `docs/validation_strategy.md` §22).

## Tests

Backend: `pytest tests/` from `backend/`, with the venv activated as above.
Current coverage: 290 tests across models, the data generator, the
validation engine, anomaly injection, detection/evaluation, the
screening/submission/lifecycle/scheduling/offer service layer, and the
FastAPI HTTP layer (routing, pagination/filtering, the hard-gate rejections,
and the documented error-response contract). Frontend: no automated test
framework is wired up yet (`npm run build` verifies the TypeScript compiles
and the production bundle builds); see `docs/implementation_plan.md`'s test
matrix for what's planned.

## Documentation

- `docs/PROJECT_SPEC.md` — requirements, scope, and all approved assumptions
- `docs/architecture.md` — system architecture and key decisions
- `docs/data_dictionary.md` — every table and field, in full
- `docs/entity_relationships.md` — the 22-table inventory and cardinalities
- `docs/business_rules.md` — screening formula, anomaly spec, lifecycle rules
- `docs/workflow.md` — end-to-end process flows
- `docs/validation_strategy.md` — the validation/detection rule catalog
- `docs/implementation_plan.md` — phase-by-phase build plan and current status

## AI usage

- `prompts/claude_code_prompts.md` — every prompt submitted to Claude Code, verbatim
- `prompts/chatgpt_prompts.md` — ChatGPT usage, where applicable
- `prompts/ai_usage_disclosure.md` — narrative disclosure of AI usage and human review

## Known limitations

Consolidated here per `docs/implementation_plan.md`'s own Phase 11 instruction
to gather these into one place, rather than leaving them scattered:

- **Interview scheduling against the committed starter dataset has a hard
  expiry.** The starter dataset's interviewer availability data runs through
  **2026-05-20**. Once the real date passes that point, `POST /interviews`
  against this dataset will always be rejected (`scheduled_start must be >=
  Application.screening_computed_at`) for any application screened after that
  date, since no availability slot exists later than it. This was verified
  directly (every one of 13 checked interviewers has zero slots after
  2026-11-13, and a live scheduling attempt against the latest known slot was
  genuinely rejected). **This is a property of the fixed-seed dataset's
  generation window versus wall-clock time passing, not an application
  defect** — the scheduling service's date checks are working exactly as
  designed, and no data, dates, or business rules were changed to work around
  it. Regenerating with a later-dated availability window (or running the
  system against live, forward-dated availability) resolves it.
- **Offer/Hired progression is not blocked by missing interviews.** The
  missing-feedback business rule (`business_rules.md` §6) only requires that
  any *completed* interview has feedback — an application with zero
  interviews satisfies this vacuously. This is documented behavior, not a
  gap: an application can legitimately reach `Hired` without ever having an
  interview scheduled, which is exactly what the limitation above means in
  practice for new data against this specific starter dataset.
- **Salary-band compliance is a business-rule, not a database, constraint**
  (`business_rules.md` §7) — the live offer-creation service hard-rejects an
  out-of-band salary at draft time (an interpretive decision, documented in
  `offer_lifecycle.py`), but because the band lives on the current
  `JobRequisition` row rather than a versioned snapshot, changing a
  requisition's band after an offer against it was approved could
  retroactively flag a historically-valid offer. The generator never does
  this; a production system would need a band-snapshot field on `Offer` to
  fully close the gap.
- **No disparate-impact or legal fairness certification is made** for the
  screening formula (`business_rules.md` §8). Excluding named
  protected-characteristic fields from the schema is a structural safeguard
  against those specific proxies, not a guarantee of fairness in any broader
  statistical or legal sense.
- **No authentication exists anywhere in this system** (`data_dictionary.md`
  §18) — the "Acting as" actor picker in the frontend and the `SystemActor`
  reference endpoint are an audit/attribution convenience for demonstrating
  the two hard-gated role checks, never a real access-control mechanism.
- **The FastAPI layer is minimal, not the full Phase 8 API surface** — built
  only to the extent Phase 10's dashboard needed real data (list/detail reads,
  plus the specific write actions each screen demonstrates). Full CRUD,
  pagination-cursor complexity, and an OpenAPI-documented contract beyond
  what `/docs` auto-generates were not built, since nothing requested them.
- **No automated frontend test framework** (vitest/React Testing Library or
  similar) exists. Frontend verification relies on a successful production
  build (`npm run build`) plus Playwright-driven smoke checks run manually
  during development and review, not a committed regression suite.
- **The production JS bundle is ~721KB**, unsplit — noted by Vite's own build
  warning. Code-splitting was not implemented since nothing requested it and
  it does not affect functional correctness.

See `docs/implementation_plan.md` for phase-by-phase status and
`prompts/ai_usage_disclosure.md` §6 for the AI-process-level limitations
(scope ambiguity, self-review vs. independent review, human review scope).
