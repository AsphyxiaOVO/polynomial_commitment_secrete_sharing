"""Application-level (non-algorithmic) errors shared by services and security.

Algorithm input errors come from ``pcss.errors`` (ValidationError & co.);
both families are translated to HTTP responses in ``app.api.errors``.
"""

from __future__ import annotations


class AppError(Exception):
    """Base class for application errors. ``code`` is a stable machine-readable identifier."""

    code = "app_error"

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class AuthenticationError(AppError):
    """Missing / invalid / expired credentials (HTTP 401)."""

    code = "not_authenticated"


class PermissionDeniedError(AppError):
    """Authenticated but not allowed to perform the action (HTTP 403)."""

    code = "permission_denied"


class NotFoundError(AppError):
    """Resource does not exist, or its existence is hidden from the caller (HTTP 404)."""

    code = "not_found"


class ConflictError(AppError):
    """The request conflicts with the current resource state (HTTP 409)."""

    code = "conflict"


class InvalidRequestError(AppError):
    """Semantically invalid request that passed schema validation (HTTP 422)."""

    code = "invalid_request"
