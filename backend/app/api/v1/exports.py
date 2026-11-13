"""Export endpoints — "export buttons must download actual generated
reports" (Phase 10's own requirement). Each endpoint computes fresh from
the live database via `analytics/` (Phase 9) and returns the result as a
downloadable attachment — never a pre-baked or fabricated file."""

import json

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.analytics.anomaly_summary import operational_anomaly_summary
from app.analytics.funnel import build_funnel_report
from app.api.deps import get_db

router = APIRouter(prefix="/exports", tags=["exports"])


@router.get("/funnel.json")
def export_funnel_json(db: Session = Depends(get_db)) -> Response:
    report = build_funnel_report(db)
    return Response(
        content=json.dumps(report, indent=2),
        media_type="application/json",
        headers={"Content-Disposition": "attachment; filename=funnel_report.json"},
    )


@router.get("/anomaly-summary.json")
def export_anomaly_summary_json(db: Session = Depends(get_db)) -> Response:
    summary = operational_anomaly_summary(db)
    return Response(
        content=json.dumps(summary, indent=2),
        media_type="application/json",
        headers={"Content-Disposition": "attachment; filename=anomaly_summary.json"},
    )
