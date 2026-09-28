"""Domain exceptions mapped to HTTP status codes by the handler layer."""

from __future__ import annotations

from typing import Any


class ApiError(Exception):
    status_code: int = 500
    error_code: str = "internal_error"

    def __init__(self, message: str, details: Any = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"error": self.error_code, "message": self.message}
        if self.details is not None:
            payload["details"] = self.details
        return payload


class ValidationError(ApiError):
    status_code = 400
    error_code = "validation_error"


class ResourceNotFoundError(ApiError):
    status_code = 404
    error_code = "not_found"


class ResourceConflictError(ApiError):
    status_code = 409
    error_code = "conflict"


class UpstreamAwsError(ApiError):
    status_code = 502
    error_code = "upstream_error"
