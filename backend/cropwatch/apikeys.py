"""Free API-key registration (spec Feature 19).

Email-only, no payment. Keys are UUID4 strings stored in a small SQLite file on
the backend and passed as ``Authorization: Bearer <key>``. A valid key raises the
caller's rate limits (see :mod:`ratelimit`). Uses the stdlib ``sqlite3`` — no
extra dependency, no external service.
"""
from __future__ import annotations

import os
import re
import sqlite3
import threading
import uuid
from datetime import datetime, timezone

from .config_bridge import config
from .errors import ValidationError

_lock = threading.Lock()
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _connect() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(config.API_KEY_DB), exist_ok=True)
    conn = sqlite3.connect(config.API_KEY_DB)
    conn.execute("""CREATE TABLE IF NOT EXISTS keys (
        key TEXT PRIMARY KEY, email TEXT NOT NULL,
        created_at TEXT NOT NULL, request_count INTEGER DEFAULT 0)""")
    return conn


def register(email: str) -> dict:
    if not email or not _EMAIL_RE.match(email.strip()):
        raise ValidationError("Please provide a valid email address.")
    key = f"cw_{uuid.uuid4().hex}"
    with _lock, _connect() as conn:
        conn.execute("INSERT INTO keys (key, email, created_at) VALUES (?, ?, ?)",
                     (key, email.strip().lower(), datetime.now(timezone.utc).isoformat()))
    return {"api_key": key, "email": email.strip().lower(),
            "message": "Store this key securely — it will not be shown again. "
                       "Pass it as 'Authorization: Bearer <key>'."}


def is_valid(key: str | None) -> bool:
    if not key:
        return False
    with _lock, _connect() as conn:
        row = conn.execute("SELECT 1 FROM keys WHERE key = ?", (key,)).fetchone()
        if row:
            conn.execute("UPDATE keys SET request_count = request_count + 1 WHERE key = ?", (key,))
        return row is not None
