"""
Custom exception hierarchy for DIOS App.

Rule: every HTTP error has a machine-readable `code` string so clients
can branch on it without parsing English messages.
"""
from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette import status


# ---------------------------------------------------------------------------
# Exception classes
# ---------------------------------------------------------------------------

class DIOSException(Exception):
    """Base class for all application-level errors."""
    http_status: int = status.HTTP_500_INTERNAL_SERVER_ERROR
    code: str = "INTERNAL_ERROR"

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        self.message = message
        self.details = details or {}
        super().__init__(message)

    def to_dict(self) -> dict:
        payload: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.details:
            payload["details"] = self.details
        return payload


class DayAlreadyClosedError(DIOSException):
    http_status = status.HTTP_409_CONFLICT
    code = "DAY_ALREADY_CLOSED"

    def __init__(self, day: date):
        super().__init__(
            message=f"Day {day} is already closed.",
            details={"day": str(day)},
        )


class BatchTooLargeError(DIOSException):
    http_status = status.HTTP_422_UNPROCESSABLE_ENTITY
    code = "BATCH_TOO_LARGE"

    def __init__(self, max_items: int, received: int):
        super().__init__(
            message=f"Batch exceeds maximum size of {max_items} items. Received {received}.",
            details={"max_items": max_items, "received": received},
        )


class EmptyBatchError(DIOSException):
    http_status = status.HTTP_422_UNPROCESSABLE_ENTITY
    code = "EMPTY_BATCH"

    def __init__(self):
        super().__init__(message="Batch must contain at least one item.")


class EntryIngestionError(DIOSException):
    http_status = status.HTTP_500_INTERNAL_SERVER_ERROR
    code = "INGESTION_ERROR"

    def __init__(self, message: str, raw: str | None = None):
        super().__init__(
            message=message,
            details={"raw": raw} if raw else {},
        )


class RouterNoActiveRulesError(DIOSException):
    http_status = status.HTTP_500_INTERNAL_SERVER_ERROR
    code = "ROUTER_NO_ACTIVE_RULES"

    def __init__(self):
        super().__init__(
            message="No active routing rules found. Run migrations to seed defaults.",
        )


# ---------------------------------------------------------------------------
# FastAPI exception handlers
# ---------------------------------------------------------------------------

async def dios_exception_handler(request: Request, exc: DIOSException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.http_status,
        content=exc.to_dict(),
    )


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Return structured 422 with machine-readable field errors."""
    field_errors = []
    for error in exc.errors():
        field_errors.append({
            "field": ".".join(str(loc) for loc in error["loc"] if loc != "body"),
            "message": error["msg"],
            "type": error["type"],
        })
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "code": "VALIDATION_ERROR",
            "message": "Request validation failed.",
            "details": {"errors": field_errors},
        },
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "code": "INTERNAL_ERROR",
            "message": "An unexpected error occurred.",
        },
    )
