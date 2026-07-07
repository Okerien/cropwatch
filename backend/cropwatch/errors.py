"""Consistent, plain-English error handling.

Every failure the user can trigger returns the same JSON shape so the frontend
never has to guess. Messages are written to be read by a non-technical user
(a farmer, a journalist) — not a stack trace.
"""
from __future__ import annotations


class CropWatchError(Exception):
    """Base class for expected, user-facing errors."""

    status_code = 400
    code = "bad_request"

    def __init__(self, message: str, *, code: str | None = None,
                 status_code: int | None = None, hint: str | None = None):
        super().__init__(message)
        self.message = message
        if code:
            self.code = code
        if status_code:
            self.status_code = status_code
        self.hint = hint

    def to_dict(self) -> dict:
        body = {"error": {"code": self.code, "message": self.message}}
        if self.hint:
            body["error"]["hint"] = self.hint
        return body


class ValidationError(CropWatchError):
    status_code = 422
    code = "validation_error"


class UpstreamError(CropWatchError):
    """A dependency (NASA, geocoder, ...) failed."""
    status_code = 502
    code = "upstream_error"


class NotFoundError(CropWatchError):
    status_code = 404
    code = "not_found"


class RateLimitError(CropWatchError):
    status_code = 429
    code = "rate_limited"
