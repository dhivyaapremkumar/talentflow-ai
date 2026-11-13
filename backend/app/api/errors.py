"""Consistent error-response handling — implementation_plan.md's gap-
filled API contract: `{"error": {"code", "message", "field"}}` for every
4xx/5xx, including hard role-enforcement rejections
(`code="role_not_permitted"`). Business decisions themselves stay in
`services/` (Phase 7/8) — this module only ever *translates* an
exception already raised there into the documented HTTP shape; it never
re-decides anything.
"""

from fastapi import Request
from fastapi.responses import JSONResponse

from app.services.application_lifecycle import ApplicationLifecycleError
from app.services.application_submission import ApplicationSubmissionError
from app.services.offer_lifecycle import OfferLifecycleError
from app.services.requisition_lifecycle import RequisitionLifecycleError
from app.services.scheduling import SchedulingError
from app.services.screening import ScreeningError

SERVICE_ERROR_TYPES = (
    RequisitionLifecycleError,
    ApplicationLifecycleError,
    ApplicationSubmissionError,
    ScreeningError,
    SchedulingError,
    OfferLifecycleError,
)


class NotFoundError(Exception):
    """Raised by a router when a path-parameter id does not resolve to a
    row — distinct from a service-layer business-rule rejection."""


def _code_for_message(message: str) -> str:
    if "APPROVER" in message and "requires actor role" in message:
        return "role_not_permitted"
    if "illegal" in message and "transition" in message:
        return "invalid_transition"
    return "business_rule_violation"


def service_error_handler(request: Request, exc: Exception) -> JSONResponse:
    message = str(exc)
    return JSONResponse(
        status_code=400,
        content={"error": {"code": _code_for_message(message), "message": message, "field": None}},
    )


def not_found_handler(request: Request, exc: NotFoundError) -> JSONResponse:
    return JSONResponse(
        status_code=404,
        content={"error": {"code": "not_found", "message": str(exc), "field": None}},
    )


def register_exception_handlers(app) -> None:
    for exc_type in SERVICE_ERROR_TYPES:
        app.add_exception_handler(exc_type, service_error_handler)
    app.add_exception_handler(NotFoundError, not_found_handler)
