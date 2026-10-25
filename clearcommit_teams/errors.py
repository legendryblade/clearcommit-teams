"""Typed application errors with user-safe messages.

Every error crossing the bridge is converted to a stable code plus a message
that never contains credentials, raw provider bodies, or file contents.
"""

from __future__ import annotations

from typing import Any, Optional


class AppError(Exception):
    code = "app_error"
    retryable = False

    def __init__(self, message: str, *, detail: Any = None) -> None:
        super().__init__(message)
        self.message = str(message)
        self.detail = detail

    def to_payload(self) -> dict:
        payload = {
            "code": self.code,
            "message": self.message,
            "retryable": self.retryable,
        }
        if self.detail not in (None, ""):
            payload["detail"] = self.detail
        return payload


class ValidationError(AppError):
    code = "validation_error"


class NotFoundError(AppError):
    code = "not_found"


class ConflictError(AppError):
    code = "conflict"


class InsufficientEvidenceError(AppError):
    code = "insufficient_evidence"


class ProviderError(AppError):
    code = "provider_error"
    retryable = True


class ProviderNotConfiguredError(AppError):
    code = "provider_not_configured"


class ProviderTimeoutError(ProviderError):
    code = "provider_timeout"


class ProviderAuthError(AppError):
    code = "provider_auth"


class ProviderRateLimitError(ProviderError):
    code = "provider_rate_limit"


class ProviderUnavailableError(ProviderError):
    code = "provider_unavailable"


class InvalidModelOutputError(AppError):
    code = "invalid_model_output"


class PathConfinementError(AppError):
    code = "path_not_allowed"


class PersistenceError(AppError):
    code = "persistence_error"


class BridgeError(AppError):
    code = "bridge_error"


def error_payload(exc: BaseException) -> dict:
    """Convert any exception to the public bridge envelope error."""
    if isinstance(exc, AppError):
        return exc.to_payload()
    return {
        "code": "internal_error",
        "message": "The workspace hit an unexpected error. Try again.",
        "retryable": False,
    }
