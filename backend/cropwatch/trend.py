"""Region-mean NDVI time series (spec Feature 4's data source).

The spec had the frontend fetch every composite raster to build the trend chart.
Serving the series directly is ~100× lighter: one request returns every 8-day
composite mean for the range. Full rasters are only fetched by the time slider,
which genuinely needs pixels.

Values come from the same deterministic engine as the snapshot (coarse grid —
a spatial mean doesn't benefit from 250 m resolution), so the last trend point
always matches the snapshot's mean for the same composite window.
"""
from __future__ import annotations

from datetime import date, timedelta

from . import demo
from .config_bridge import config
from .errors import ValidationError
from .stats import severity_score

RANGES = {"3m": 92, "6m": 183, "12m": 365, "5y": 5 * 365}


def _classify(v: float) -> str:
    for name, low, high, _ in config.STRESS_ZONES:
        if low <= v < high:
            return name
    return "dense_healthy"


def compute(bbox: list[float], polygons: list, seed_hash: str,
            range_key: str, end: date | None = None) -> dict:
    if range_key not in RANGES:
        raise ValidationError(f"range must be one of {sorted(RANGES)}.")
    end = end or (date.today() - timedelta(days=10))
    start = end - timedelta(days=RANGES[range_key])

    points = []
    step = timedelta(days=config.COMPOSITE_DAYS)
    d = start
    while d <= end:
        mean = demo.region_mean_at(bbox, polygons, seed_hash, d)
        if mean is not None:
            points.append({
                "date": d.isoformat(),
                "mean_ndvi": round(mean, 4),
                "classification": _classify(mean),
            })
        d += step

    means = [p["mean_ndvi"] for p in points]
    yoy = None
    if range_key in ("12m", "5y") and len(points) > 46:
        yoy = round(means[-1] - means[-47], 4)  # vs same composite last year

    return {
        "range": range_key,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "composite_days": config.COMPOSITE_DAYS,
        "points": points,
        "summary": {
            "latest": means[-1] if means else None,
            "min": min(means) if means else None,
            "max": max(means) if means else None,
            "yoy_change": yoy,
            "direction": ("rising" if len(means) >= 2 and means[-1] > means[-2]
                          else "falling" if len(means) >= 2 else "flat"),
        },
        "thresholds": [
            {"value": hi, "label": name} for name, lo, hi, _ in config.STRESS_ZONES[:-1]
        ],
        "source": "demo",
    }
