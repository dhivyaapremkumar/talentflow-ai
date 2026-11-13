# TalentFlow AI

Recruitment operations and decision-intelligence system — YottaFlex AI Associate
Forward Deployed Engineer challenge submission.

**Status: Phases 1-10 complete.** The 22-table schema, the deterministic data
generator, the validation/anomaly-detection engine, anomaly injection,
independent detection + offline evaluation, the screening/submission/
lifecycle/scheduling/offer service layer, a minimal FastAPI HTTP layer, and a
5-screen React dashboard (Executive Dashboard, Requisitions & Applications,
Screening & Candidate Profile, Interview Management, Offers & Decision
Intelligence) are all implemented and tested (290 backend tests passing) —
see `docs/implementation_plan.md` for the full phase-by-phase plan and
current progress.

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

Tracked as work progresses — see `docs/implementation_plan.md` for the current
phase status and `docs/business_rules.md` for documented design-level
limitations (e.g., the salary-band snapshot limitation, §7).
