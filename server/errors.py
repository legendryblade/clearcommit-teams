"""Typed API errors and the response envelope.

Every response uses {"ok": true, "data": ...} or
{"ok": false, "error": {"code", "message", "retryable", "request_id"}}.
"""

from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse


class ApiError(Exception):
    def __init__(self, code: str, message: str, status: int = 400, retryable: bool = False):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.retryable = retryable


def ok(data) -> JSONResponse:
    return JSONResponse({"ok": True, "data": data}, status_code=200)


def accepted(data) -> JSONResponse:
    return JSONResponse({"ok": True, "data": data}, status_code=202)


def fail(request: Request, code: str, message: str, status: int, retryable: bool = False) -> JSONResponse:
    request_id = getattr(request.state, "request_id", None)
    return JSONResponse(
        {
            "ok": False,
            "error": {
                "code": code,
                "message": message,
                "retryable": retryable,
                "request_id": request_id,
            },
        },
        status_code=status,
    )
