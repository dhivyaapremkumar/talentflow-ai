"""Analytics response shapes — thin pass-through wrappers around
`analytics/funnel.py`/`analytics/anomaly_summary.py`'s plain-dict return
values (Phase 9). No new calculation lives here."""

from typing import Any

from pydantic import BaseModel


class FunnelReport(BaseModel):
    requisition_funnel_overall: list[dict[str, Any]]
    requisition_funnel_by_requisition: list[dict[str, Any]]
    requisition_funnel_by_department: list[dict[str, Any]]
    requisition_status_distribution: list[dict[str, Any]]
    time_in_stage: dict[str, Any]
    interviewer_load: list[dict[str, Any]]
    offer_acceptance_rate_overall: list[dict[str, Any]]
    offer_acceptance_rate_by_department: list[dict[str, Any]]
    offer_acceptance_rate_by_level: list[dict[str, Any]]
    duplicate_submission_rate_by_requisition: list[dict[str, Any]]
    duplicate_submission_rate_by_department: list[dict[str, Any]]


class AnomalySummary(BaseModel):
    checked_at: str
    counts_by_anomaly_type: dict[str, int]
    total_violations: int
