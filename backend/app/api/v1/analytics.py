"""Analytics endpoints — thin HTTP wrappers around `analytics/funnel.py`
and `analytics/anomaly_summary.py` (Phase 9). No calculation happens
here; this router only calls those modules and serializes their return
value. `GET /analytics/anomaly-summary` is `operational_anomaly_summary`
(no ground truth, safe for the operational dashboard); there is no
evaluation-reporting endpoint — that stays a dev-only CLI/report path,
per requirement 8's "unless explicitly required for evaluation
reporting" (the ordinary dashboard is not that context)."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.analytics.anomaly_summary import operational_anomaly_summary
from app.analytics.funnel import build_funnel_report
from app.api.deps import get_db
from app.schemas.analytics import AnomalySummary, FunnelReport

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/funnel", response_model=FunnelReport)
def get_funnel_report(db: Session = Depends(get_db)):
    return build_funnel_report(db)


@router.get("/anomaly-summary", response_model=AnomalySummary)
def get_anomaly_summary(db: Session = Depends(get_db)):
    return operational_anomaly_summary(db)
