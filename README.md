# TalentFlow AI

Recruitment operations and decision-intelligence system — YottaFlex AI Associate
Forward Deployed Engineer challenge submission.

**Status: Phases 1-8 complete.** The 22-table schema, the deterministic data
generator, the validation/anomaly-detection engine, anomaly injection,
independent detection + offline evaluation, and the screening/submission/
lifecycle/scheduling/offer service layer are all implemented and tested
(240 backend tests passing). The FastAPI HTTP layer (routers/schemas) and the
React dashboard UI are not implemented yet — see `docs/implementation_plan.md`
for the full phase-by-phase plan and current progress.

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

Requires Python 3.12 and Node.js 20+.

### Backend

```bash
cd backend
py -3.12 -m venv .venv
.venv/Scripts/python.exe -m pip install --upgrade pip
.venv/Scripts/python.exe -m pip install -e ".[dev]"
```

Verify:
```bash
.venv/Scripts/python.exe -m pytest tests/ -v
.venv/Scripts/python.exe -m uvicorn app.main:app --reload
# then: curl http://127.0.0.1:8000/health
```

No `.env` file is required to run — `backend/.env.example` documents the only
two configuration values (`DATABASE_PATH`, `DATASET_MODE`), and this project
has no authentication and no paid external services, so there are no secrets
to configure.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

## Dataset generation and validation

From `backend/`, with the venv set up as above:

```bash
# Generate, inject anomalies, and run baseline + post-injection validation
# in one pass (starter: 150 applications; full: 3,000):
.venv/Scripts/python.exe -m app.data_generation.generator --mode starter
.venv/Scripts/python.exe -m app.data_generation.generator --mode full
```

Each run writes a SQLite database to `backend/data/talentflow_<mode>.db`,
CSV/JSON exports to `backend/data/exports/<mode>/` (the `starter/` exports are
committed; `full/` is regeneratable and gitignored), and prints baseline
validation (expected: 0 violations, 0 warnings) and post-injection validation
(expected: 11 violations at starter scale / 56 at full scale, broken out by
rule ID — the seeded anomaly counts from `business_rules.md` §9).

```bash
# Independent anomaly detection + offline ground-truth evaluation
# (reads the database the generator just wrote):
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
Current coverage: 240 tests across models, the data generator, the
validation engine, anomaly injection, detection/evaluation, and the
screening/submission/lifecycle/scheduling/offer service layer. More tests
land with each subsequent phase — see `docs/implementation_plan.md`'s test
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
