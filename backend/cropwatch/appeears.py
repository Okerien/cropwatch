"""NASA AppEEARS async client — the real MODIS NDVI pipeline.

Workflow (per the AppEEARS API): authenticate with Earthdata → submit an *area*
task → poll until ``done`` → discover the result bundle → download and parse the
NDVI GeoTIFF into an :class:`NDVIGrid`.

The control flow (auth, submit, poll, bundle) is fully implemented here. GeoTIFF
decoding needs ``rasterio``, which is a heavy dependency deferred to Phase 3; so
:func:`fetch_grid` imports it lazily and, if it is not installed, raises an
``UpstreamError`` that the route turns into a graceful demo fallback. This keeps
Phase 1 installable in seconds while leaving the live path ready to switch on.
"""
from __future__ import annotations

import io
import re
import time
from datetime import date, timedelta

import numpy as np
import requests

from .config_bridge import config
from .errors import UpstreamError
from .grid import NDVIGrid

_TIMEOUT = 30
_token_cache: dict = {"token": None, "expires_at": 0.0}

PRODUCT_MAP = {
    "MOD13Q1": ("MOD13Q1.061", "_250m_16_days_NDVI"),
    "MYD13Q1": ("MYD13Q1.061", "_250m_16_days_NDVI"),
}


# --------------------------------------------------------------------------- #
# Auth                                                                         #
# --------------------------------------------------------------------------- #
def _get_token() -> str:
    now = time.time()
    if _token_cache["token"] and now < _token_cache["expires_at"]:
        return _token_cache["token"]
    if not config.HAS_EARTHDATA:
        raise UpstreamError("NASA Earthdata credentials are not configured.",
                            code="no_credentials")
    try:
        resp = requests.post(
            f"{config.APPEEARS_BASE}/login",
            auth=(config.EARTHDATA_USERNAME, config.EARTHDATA_PASSWORD),
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as exc:
        raise UpstreamError(f"Could not authenticate with NASA AppEEARS: {exc}") from exc
    token = data.get("token")
    if not token:
        raise UpstreamError("AppEEARS did not return an auth token.")
    _token_cache.update(token=token, expires_at=now + 40 * 60)  # tokens last ~48h; refresh hourly
    return token


def _auth_headers() -> dict:
    return {"Authorization": f"Bearer {_get_token()}"}


# --------------------------------------------------------------------------- #
# Task lifecycle                                                               #
# --------------------------------------------------------------------------- #
def _fmt(d: date) -> str:
    return d.strftime("%m-%d-%Y")  # AppEEARS expects MM-DD-YYYY


def _doy_date(name: str) -> date | None:
    """Parse the composite date from an AppEEARS filename (…doyYYYYDDD…)."""
    m = re.search(r"doy(\d{4})(\d{3})", name)
    if not m:
        return None
    return date(int(m.group(1)), 1, 1) + timedelta(days=int(m.group(2)) - 1)


def submit_task(area_geojson: dict, start: date, end: date, product: str,
                task_name: str = "cropwatch") -> str:
    """Submit an area task and return the AppEEARS task id.

    The requested window is widened to at least ``LIVE_WINDOW_DAYS`` so a 16-day
    MOD13Q1 composite reliably falls inside it; :func:`fetch_grid` then serves
    the most recent one.
    """
    prod, layer = PRODUCT_MAP.get(product, PRODUCT_MAP["MOD13Q1"])
    req_start = min(start, end - timedelta(days=config.LIVE_WINDOW_DAYS))
    payload = {
        "task_type": "area",
        "task_name": task_name,
        "params": {
            "dates": [{"startDate": _fmt(req_start), "endDate": _fmt(end)}],
            "layers": [{"product": prod, "layer": layer}],
            "output": {"format": {"type": "geotiff"}, "projection": "geographic"},
            "geo": area_geojson,
        },
    }
    try:
        resp = requests.post(f"{config.APPEEARS_BASE}/task",
                             json=payload, headers=_auth_headers(), timeout=_TIMEOUT)
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise UpstreamError(f"AppEEARS task submission failed: {exc}") from exc
    task_id = resp.json().get("task_id")
    if not task_id:
        raise UpstreamError("AppEEARS did not return a task id.")
    return task_id


def task_status(task_id: str) -> dict:
    """Return {state, progress_pct} for an AppEEARS task."""
    try:
        resp = requests.get(f"{config.APPEEARS_BASE}/task/{task_id}",
                            headers=_auth_headers(), timeout=_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as exc:
        raise UpstreamError(f"Could not read AppEEARS task status: {exc}") from exc
    state = data.get("status", "pending")
    progress = 0
    if isinstance(data.get("progress"), dict):
        progress = int(data["progress"].get("summary", 0) or 0)
    if state == "done":
        progress = 100
    return {"state": state, "progress_pct": progress}


def _bundle_files(task_id: str) -> list[dict]:
    try:
        resp = requests.get(f"{config.APPEEARS_BASE}/bundle/{task_id}",
                            headers=_auth_headers(), timeout=_TIMEOUT)
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise UpstreamError(f"Could not list AppEEARS result bundle: {exc}") from exc
    return resp.json().get("files", [])


def fetch_grid(task_id: str) -> NDVIGrid:
    """Download the NDVI GeoTIFF from a completed task and parse it into a grid."""
    try:
        import rasterio  # noqa: F401  (heavy; deferred to Phase 3)
        from rasterio.io import MemoryFile
    except ImportError as exc:
        raise UpstreamError(
            "Satellite raster decoding (rasterio) is enabled in a later build "
            "phase — serving synthetic data for now.",
            code="raster_backend_unavailable",
        ) from exc

    files = _bundle_files(task_id)
    tifs = [f for f in files
            if f.get("file_name", "").endswith(".tif") and "NDVI" in f.get("file_name", "")]
    if not tifs:
        raise UpstreamError("No NDVI raster found in the AppEEARS result bundle.")
    # Most recent composite first (the widened window may return several).
    tifs.sort(key=lambda f: _doy_date(f["file_name"]) or date(1970, 1, 1), reverse=True)
    ndvi_file = tifs[0]
    composite_date = _doy_date(ndvi_file["file_name"])
    file_id = ndvi_file["file_id"]
    try:
        resp = requests.get(f"{config.APPEEARS_BASE}/bundle/{task_id}/{file_id}",
                            headers=_auth_headers(), timeout=120)
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise UpstreamError(f"Could not download NDVI raster: {exc}") from exc

    with MemoryFile(io.BytesIO(resp.content)) as mem, mem.open() as ds:
        raw = ds.read(1).astype(np.float64)
        b = ds.bounds
        bbox = [b.left, b.bottom, b.right, b.top]

    lo, hi = config.MODIS_VALID_RANGE
    raw[(raw < lo) | (raw > hi)] = np.nan
    ndvi = raw * config.MODIS_SCALE
    ndvi[ndvi < config.NDVI_NODATA_BELOW] = np.nan
    return NDVIGrid(ndvi=ndvi, bbox=bbox, source="appeears",
                    composite_date=composite_date)
