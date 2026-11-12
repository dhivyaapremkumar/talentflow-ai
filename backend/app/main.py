"""FastAPI application entrypoint.

Phase 1 skeleton only — no routers mounted yet (those arrive in Phase 8, per
implementation_plan.md). This file's only job right now is to prove the
backend process starts and responds.
"""

from fastapi import FastAPI

app = FastAPI(
    title="TalentFlow AI",
    description="Recruitment operations and decision-intelligence backend",
    version="0.1.0",
)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "talentflow-ai-backend"}
