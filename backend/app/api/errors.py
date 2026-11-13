"""Consistent error-response handling — implementation_plan.md's gap-
filled API contract: `{"error": {"code", "message", "field"}}` for every
4xx/5xx, including hard role-enforcement rejections
(`code="role_not_permitted"`). Business decisions themselves stay in
`services/` (Phase 7/8) — this module only ever *translates* an
exception already raised there into the documented HTTP shape; it never
re-decides anything.
"""

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.db.session import DatabaseNotConfiguredError
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


_LOC_PREFIXES = ("body", "query", "path", "header")


def _field_for_loc(loc: tuple) -> str | None:
    parts = [str(p) for p in loc if str(p) not in _LOC_PREFIXES]
    return ".".join(parts) if parts else None


def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Maps FastAPI/Pydantic's built-in request-validation failures
    (missing/invalid fields, malformed JSON) onto the same documented
    `{"error": {"code","message","field"}}` shape every other 4xx/5xx
    uses — previously these fell through to FastAPI's own default
    `{"detail": [...]}` body instead (a real inconsistency, found and
    fixed as a follow-up to the Phase 10 review). Only the parsed
    `msg`/`loc` from Pydantic's error list is surfaced — never a raw
    stack trace."""
    errors = exc.errors()
    first = errors[0] if errors else {}
    message = first.get("msg", "Validation failed")
    if len(errors) > 1:
        message = f"{message} (and {len(errors) - 1} more validation error(s))"
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "validation_error",
                "message": message,
                "field": _field_for_loc(tuple(first.get("loc", ()))),
            }
        },
    )


def database_not_configured_handler(request: Request, exc: DatabaseNotConfiguredError) -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={"error": {"code": "database_not_configured", "message": str(exc), "field": None}},
    )


def register_exception_handlers(app) -> None:
    for exc_type in SERVICE_ERROR_TYPES:
        app.add_exception_handler(exc_type, service_error_handler)
    app.add_exception_handler(NotFoundError, not_found_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(DatabaseNotConfiguredError, database_not_configured_handler)
