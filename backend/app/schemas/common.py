"""Shared response shapes — Phase 10's minimal API layer.

Pagination is simple offset/limit, per implementation_plan.md's own gap
analysis ("simple offset pagination, no cursor complexity, consistent
with 'avoid unnecessary abstraction'"). The error shape is the single
consistent `{"error": {"code", "message", "field"}}` contract that same
section specifies for every 4xx/5xx, including hard role-enforcement
rejections (`code="role_not_permitted"`).
"""

from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    limit: int
    offset: int


class ErrorDetail(BaseModel):
    code: str
    message: str
    field: str | None = None


class ErrorResponse(BaseModel):
    error: ErrorDetail
