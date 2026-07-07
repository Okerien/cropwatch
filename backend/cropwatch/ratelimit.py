"""In-memory sliding-window rate limiting (spec Feature 19).

A dependency-free limiter that fits the single-worker, in-process model: a deque
of hit timestamps per (bucket, identifier). Anonymous callers are keyed by IP;
callers with a valid API key are keyed by their key and get the higher limits.

Buckets and limits live in ``config.RATE_LIMITS``: 10/hr anonymous NDVI, 100/hr
with a key; 60/hr other endpoints anonymous, 1000/hr with a key.
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

from flask import request

from . import apikeys
from .config_bridge import config
from .errors import RateLimitError

_lock = threading.Lock()
_hits: dict[tuple[str, str], deque] = defaultdict(deque)

# The strict NDVI cap exists to protect the NASA AppEEARS quota. Demo-mode
# responses are synthetic and cache-served — they cost nothing upstream — so
# limits are multiplied in demo mode (the time slider alone needs ~12 frames).
DEMO_MULTIPLIER = 30


def _identifier() -> tuple[str, bool]:
    """Return (identity, has_valid_key). Key from Authorization: Bearer <key>."""
    auth = request.headers.get("Authorization", "")
    key = auth[7:].strip() if auth.lower().startswith("bearer ") else None
    if key and apikeys.is_valid(key):
        return f"key:{key}", True
    ip = (request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
          or request.remote_addr or "unknown")
    return f"ip:{ip}", False


def enforce(kind: str) -> dict:
    """Enforce a limit for ``kind`` in {"ndvi", "default"}; raise 429 if exceeded.

    Returns rate-limit metadata for response headers on success.
    """
    identity, has_key = _identifier()
    limit_key = f"{kind}_{'key' if has_key else 'anon'}"
    max_req, window = config.RATE_LIMITS.get(limit_key, config.RATE_LIMITS["default_anon"])
    if config.DEMO_MODE_DEFAULT:
        max_req *= DEMO_MULTIPLIER
    now = time.time()
    bucket = (limit_key, identity)

    with _lock:
        q = _hits[bucket]
        while q and q[0] <= now - window:
            q.popleft()
        if len(q) >= max_req:
            retry = int(q[0] + window - now) + 1
            raise RateLimitError(
                f"Rate limit exceeded ({max_req} requests/hour). "
                + ("Register a free API key for higher limits." if not has_key
                   else "Try again shortly."),
                hint=f"Retry in about {retry} seconds.")
        q.append(now)
        remaining = max_req - len(q)
        reset = int(q[0] + window) if q else int(now + window)

    return {"limit": max_req, "remaining": remaining, "reset": reset,
            "authenticated": has_key}


def apply_headers(response, meta: dict):
    if meta:
        response.headers["X-RateLimit-Limit"] = str(meta["limit"])
        response.headers["X-RateLimit-Remaining"] = str(meta["remaining"])
        response.headers["X-RateLimit-Reset"] = str(meta["reset"])
    return response
