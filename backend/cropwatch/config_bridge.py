"""Re-exports the top-level ``config`` object for use inside the package.

This keeps ``from .config_bridge import config`` working whether the app is
started from /backend (gunicorn app:app) or imported in tests, without every
module needing to know where the settings file physically lives.
"""
import os
import sys

# Ensure the backend root (containing config.py) is importable.
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from config import config  # noqa: E402

__all__ = ["config"]
