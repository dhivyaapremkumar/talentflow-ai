"""FastAPI application entrypoint.

Phase 10's minimal API layer: routers are thin HTTP adapters over the
existing `services/`/`analytics/` modules (architecture.md §6 — "database
writes only through service-layer operations"); no business logic is
duplicated here. CORS is wide open (`allow_origins=["*"]`) because this
project has no authentication at all (PROJECT_SPEC.md §2) — there is no
session/cookie to protect, so the usual CORS-tightening rationale does
not apply; this is documented, not an oversight.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.errors import register_exception_handlers
from app.api.v1 import analytics, applications, candidates, exports, interviews, offers, reference, requisitions

app = FastAPI(
    title="TalentFlow AI",
    description="Recruitment operations and decision-intelligence backend",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

register_exception_handlers(app)

app.include_router(reference.router, prefix="/api/v1")
app.include_router(requisitions.router, prefix="/api/v1")
app.include_router(candidates.router, prefix="/api/v1")
app.include_router(applications.router, prefix="/api/v1")
app.include_router(interviews.router, prefix="/api/v1")
app.include_router(offers.router, prefix="/api/v1")
app.include_router(analytics.router, prefix="/api/v1")
app.include_router(exports.router, prefix="/api/v1")


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "talentflow-ai-backend"}
