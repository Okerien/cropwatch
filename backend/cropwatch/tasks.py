"""NDVI task orchestration — the async workflow the frontend polls against.

One code path, two engines. In demo mode the work is fast and runs inline, but
still surfaces through the same task/status contract so the frontend's progress
flow is identical to production. With Earthdata credentials, the real AppEEARS
task is submitted and a background thread polls NASA and fills in the result.

Task ids are a hash of (geometry + date window + product), so identical requests
deduplicate: two users watching the same district share one satellite task and
one cache entry.
"""
from __future__ import annotations

import threading
import time
from datetime import date, datetime, timedelta, timezone

from . import appeears, demo
from .cache import cache
from .config_bridge import config
from .errors import CropWatchError, UpstreamError, ValidationError
from .geometry import geometry_hash, validate_area
from .stats import summarize


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def default_window() -> tuple[date, date]:
    """Most recent completed 8-day composite, accounting for MODIS data latency."""
    end = date.today() - timedelta(days=10)
    start = end - timedelta(days=config.COMPOSITE_DAYS - 1)
    return start, end


def _parse_date(value, fallback: date) -> date:
    if not value:
        return fallback
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except (ValueError, TypeError) as exc:
        raise ValidationError(
            f"Date {value!r} is not in YYYY-MM-DD format.") from exc


def _task_key(geo_hash: str, start: date, end: date, product: str) -> str:
    return f"task:{geo_hash}:{start}:{end}:{product}"


def _to_feature_collection(geojson: dict, polygons: list) -> dict:
    """Wrap normalised geometry as a FeatureCollection for AppEEARS."""
    return {
        "type": "FeatureCollection",
        "features": [{
            "type": "Feature", "properties": {},
            "geometry": {"type": "MultiPolygon",
                         "coordinates": [[[list(pt) for pt in ring] for ring in poly]
                                         for poly in polygons]},
        }],
    }


def _build_result(grid, area_meta: dict, start: date, end: date, product: str) -> dict:
    payload = grid.to_payload()
    return {
        "composite": {
            "start": start.isoformat(),
            "end": end.isoformat(),
            "product": product,
            "date_label": f"{start.strftime('%d %b')} – {end.strftime('%d %b %Y')}",
            "age_days": (date.today() - end).days,
        },
        "area": {
            "bbox": area_meta["bbox"],
            "area_km2": area_meta["area_km2"],
            "centroid": area_meta["centroid"],
        },
        **payload,
        "stats": summarize(grid.ndvi),
        "source": grid.source,
        "generated_at": _now_iso(),
    }


# --------------------------------------------------------------------------- #
# Entry point                                                                 #
# --------------------------------------------------------------------------- #
def create_ndvi_task(geojson: dict, start_str: str | None, end_str: str | None,
                     product: str, force_demo: bool) -> dict:
    """Validate the request and start (or return a cached) NDVI task."""
    if product not in config.VALID_PRODUCTS:
        raise ValidationError(
            f"Unknown product {product!r}. Choose one of {config.VALID_PRODUCTS}.")

    d_start_default, d_end_default = default_window()
    start = _parse_date(start_str, d_start_default)
    end = _parse_date(end_str, d_end_default)
    if start > end:
        raise ValidationError("start_date must be on or before end_date.")

    area_meta = validate_area(geojson)          # raises plain-English errors
    geo_hash = geometry_hash(geojson)
    key = _task_key(geo_hash, start, end, product)

    existing = cache.get(key)
    if existing and existing.get("status") in {"complete", "processing"}:
        out = dict(existing)
        out["cached"] = existing.get("status") == "complete"
        return out

    use_demo = force_demo or config.DEMO_MODE_DEFAULT or not config.HAS_EARTHDATA
    task = {
        "task_id": f"{geo_hash}-{product}-{start:%Y%m%d}-{end:%Y%m%d}",
        "status": "processing",
        "progress": 5,
        "message": "Preparing satellite request…",
        "source": "demo" if use_demo else "appeears",
        "created_at": _now_iso(),
        "cache_key": key,
        "params": {"start": start.isoformat(), "end": end.isoformat(),
                   "product": product, "geo_hash": geo_hash},
        "result": None,
        "error": None,
        "cached": False,
    }
    cache.set(key, task, ttl=config.CACHE_TTL["ndvi"])

    if use_demo:
        _run_demo(task, geojson, area_meta, start, end, product)
    else:
        _start_appeears(task, geojson, area_meta, start, end, product)

    return cache.get(key) or task


def create_historical(geojson: dict, target_str: str | None, years: int) -> dict:
    """Compute (or return cached) historical anomaly analysis for an area.

    In demo mode this runs inline (deterministic, ~1–2s). The result carries the
    z-score grid, anomaly distribution, analogue years, and anomaly time series.
    """
    from . import historical  # local import to avoid heavy load at startup

    if years not in (5, 10, 20):
        raise ValidationError("years must be one of 5, 10, or 20.")

    _, default_end = default_window()
    target = _parse_date(target_str, default_end)

    area_meta = validate_area(geojson)
    geo_hash = geometry_hash(geojson)
    key = f"hist:{geo_hash}:{target}:{years}"

    cached = cache.get(key)
    if cached:
        out = dict(cached)
        out["cached"] = True
        return out

    result = historical.compute(area_meta["bbox"], area_meta["polygons"],
                                geo_hash, target, years, area_meta)
    result["cached"] = False
    cache.set(key, result, ttl=config.CACHE_TTL["historical"])
    return result


def get_task(task_id: str) -> dict | None:
    """Look up a task by its public id (scans cache keys ending with the id)."""
    # task_id encodes the geo hash + product; find its live cache entry.
    for suffix_match in _iter_task_entries():
        if suffix_match.get("task_id") == task_id:
            out = dict(suffix_match)
            out["cached"] = suffix_match.get("status") == "complete"
            return out
    return None


def _iter_task_entries():
    # cache internals are private; snapshot values that look like tasks.
    with cache._lock:  # noqa: SLF001 — intentional, single-process cache
        for entry in list(cache._store.values()):
            val = entry.get("value")
            if isinstance(val, dict) and "task_id" in val and "status" in val:
                yield val


# --------------------------------------------------------------------------- #
# Engines                                                                     #
# --------------------------------------------------------------------------- #
def _run_demo(task: dict, geojson, area_meta, start, end, product) -> None:
    key = task["cache_key"]
    try:
        cache.update(key, progress=45, message="Compositing vegetation index…")
        grid = demo.generate(area_meta["bbox"], area_meta["polygons"],
                             geometry_hash(geojson), end)
        result = _build_result(grid, area_meta, start, end, product)
        cache.update(key, status="complete", progress=100,
                     message="Snapshot ready.", result=result, source="demo")
    except CropWatchError as exc:
        cache.update(key, status="failed", error=exc.to_dict()["error"],
                     message=exc.message)
    except Exception as exc:  # pragma: no cover — defensive
        cache.update(key, status="failed",
                     error={"code": "internal", "message": str(exc)},
                     message="Snapshot generation failed.")


def _start_appeears(task: dict, geojson, area_meta, start, end, product) -> None:
    key = task["cache_key"]
    fc = _to_feature_collection(geojson, area_meta["polygons"])

    def worker():
        try:
            appeears_id = appeears.submit_task(fc, start, end, product)
            cache.update(key, progress=15,
                         message="NASA is processing your request… (1–3 min)",
                         appeears_task_id=appeears_id)
            deadline = time.time() + 15 * 60
            while time.time() < deadline:
                st = appeears.task_status(appeears_id)
                cache.update(key, progress=max(15, min(95, st["progress_pct"])))
                if st["state"] == "done":
                    grid = appeears.fetch_grid(appeears_id)
                    result = _build_result(grid, area_meta, start, end, product)
                    cache.update(key, status="complete", progress=100,
                                 message="Snapshot ready.", result=result,
                                 source="appeears")
                    return
                if st["state"] in {"error", "expired"}:
                    raise UpstreamError("NASA AppEEARS reported a task error.")
                time.sleep(10)
            raise UpstreamError("Satellite request timed out. Please try again.")
        except UpstreamError as exc:
            # Graceful degrade: fall back to synthetic data with a clear note.
            _fallback_to_demo(key, geojson, area_meta, start, end, product, exc.message)
        except Exception as exc:  # pragma: no cover — defensive
            cache.update(key, status="failed",
                         error={"code": "internal", "message": str(exc)},
                         message="Satellite request failed.")

    threading.Thread(target=worker, daemon=True).start()


def _fallback_to_demo(key, geojson, area_meta, start, end, product, reason) -> None:
    try:
        grid = demo.generate(area_meta["bbox"], area_meta["polygons"],
                             geometry_hash(geojson), end)
        result = _build_result(grid, area_meta, start, end, product)
        result["fallback_reason"] = reason
        cache.update(key, status="complete", progress=100,
                     message="Showing synthetic data (live satellite unavailable).",
                     result=result, source="demo")
    except Exception as exc:  # pragma: no cover
        cache.update(key, status="failed",
                     error={"code": "internal", "message": str(exc)},
                     message="Request failed.")
