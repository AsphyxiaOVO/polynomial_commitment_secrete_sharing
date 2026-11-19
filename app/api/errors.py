"""Unified error responses: ``{"error": {"code": ..., "message": ..., "details"?: [...]}}``.

* No tracebacks or internal state reach the client.
* Validation errors never echo the submitted input (it may contain secrets).
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from pcss.errors import (DecodingError, InconsistentSharesError, InsufficientSharesError, PCSSError,
                         ProtocolError, ValidationError)

from app.errors import (AppError, AuthenticationError, ConflictError, InvalidRequestError,
                        NotFoundError, PermissionDeniedError)

logger = logging.getLogger("app.errors")

_APP_STATUS = {
    AuthenticationError: 401,
    PermissionDeniedError: 403,
    NotFoundError: 404,
    ConflictError: 409,
    InvalidRequestError: 422,
}

_CORE_CODES = [
    (InsufficientSharesError, "insufficient_shares"),
    (InconsistentSharesError, "inconsistent_shares"),
    (DecodingError, "decoding_failed"),
    (ValidationError, "invalid_input"),
]


def error_response(status: int, code: str, message: str,
                   details: Optional[List[Dict[str, Any]]] = None,
                   headers: Optional[Dict[str, str]] = None) -> JSONResponse:
    body: Dict[str, Any] = {"error": {"code": code, "message": message}}
    if details:
        body["error"]["details"] = details
    return JSONResponse(status_code=status, content=body, headers=headers)


async def _app_error(_: Request, exc: AppError) -> JSONResponse:
    status = next((s for cls, s in _APP_STATUS.items() if isinstance(exc, cls)), 400)
    headers = {"WWW-Authenticate": "Bearer"} if status == 401 else None
    return error_response(status, exc.code, exc.message, headers=headers)


async def _core_error(request: Request, exc: PCSSError) -> JSONResponse:
    if isinstance(exc, ValidationError):
        code = next(c for cls, c in _CORE_CODES if isinstance(exc, cls))
        message = str(exc)
        if isinstance(exc, DecodingError):
            message += (" - the submitted shares are probably wrong; note that this is a decoding "
                        "check, not a cryptographic share-validity check")
        return error_response(422, code, message)
    # ProtocolError / other core invariants: internal problem, do not leak details
    logger.error("core invariant violated on %s %s: %s", request.method, request.url.path,
                 type(exc).__name__)
    return error_response(500, "internal_error", "Internal server error")


async def _request_validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
    details = [{"loc": [str(p) for p in err.get("loc", ())], "msg": err.get("msg", ""),
                "type": err.get("type", "")} for err in exc.errors()]   # no "input" / "ctx"
    return error_response(422, "validation_error", "Request validation failed", details)


async def _http_exception(_: Request, exc: StarletteHTTPException) -> JSONResponse:
    code = {401: "not_authenticated", 403: "permission_denied", 404: "not_found",
            405: "method_not_allowed"}.get(exc.status_code, "http_error")
    return error_response(exc.status_code, code, str(exc.detail), headers=getattr(exc, "headers", None))


async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
    logger.error("unhandled %s on %s %s", type(exc).__name__, request.method, request.url.path)
    return error_response(500, "internal_error", "Internal server error")


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, _app_error)
    app.add_exception_handler(PCSSError, _core_error)
    app.add_exception_handler(RequestValidationError, _request_validation_error)
    app.add_exception_handler(StarletteHTTPException, _http_exception)
    app.add_exception_handler(Exception, _unhandled)


__all__ = ["register_exception_handlers", "error_response", "ProtocolError"]
