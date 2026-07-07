"""NDVI summary statistics, stress classification, and the severity score.

This is computed once, server-side, so every downstream consumer — the summary
panel, region cards, alert banner, PDF headline, CSV export — reads the exact
same numbers. Keeping it here (not in the frontend) guarantees consistency.
"""
from __future__ import annotations

import numpy as np

from .config_bridge import config

SEVERITY_LABELS = [
    (0, 25, "Severe stress", "#B71C1C"),
    (26, 45, "Significant stress", "#E64A19"),
    (46, 60, "Moderate stress", "#F9A825"),
    (61, 75, "Mild stress", "#C0CA33"),
    (76, 90, "Good conditions", "#43A047"),
    (91, 100, "Excellent conditions", "#1B5E20"),
]


def _clean(ndvi: np.ndarray) -> np.ndarray:
    """Flatten to valid (non-nodata, finite) NDVI values only."""
    flat = np.asarray(ndvi, dtype=np.float64).ravel()
    return flat[np.isfinite(flat) & (flat >= config.NDVI_NODATA_BELOW)]


def classify_zones(ndvi: np.ndarray) -> dict:
    """Return per-zone pixel counts and percentages of valid vegetated pixels."""
    valid = _clean(ndvi)
    total = int(valid.size)
    zones = {}
    for name, low, high, colour in config.STRESS_ZONES:
        mask = (valid >= low) & (valid < high)
        count = int(mask.sum())
        zones[name] = {
            "pixel_count": count,
            "pct": round(100 * count / total, 2) if total else 0.0,
            "range": [low, min(high, 1.0)],
            "colour": colour,
        }
    return zones


def severity_score(mean_ndvi: float, stressed_area_pct: float,
                   mean_z: float | None = None) -> dict:
    """The 0–100 crop-stress severity score (Feature 11).

    Three weighted components: absolute mean NDVI (35%), stressed-area
    proportion (35%), historical anomaly z-score (30%). When the historical
    baseline is not yet available (Phase 1, before /historical exists), the
    anomaly component is omitted and the remaining weights are renormalised —
    the score is still valid, just marked ``partial``.
    """
    w = config.SEVERITY_WEIGHTS
    comp_ndvi = float(np.clip(mean_ndvi, 0, 1)) * 100
    comp_area = float(np.clip(100 - stressed_area_pct, 0, 100))

    if mean_z is None:
        weight_sum = w["ndvi"] + w["stressed_area"]
        score = (comp_ndvi * w["ndvi"] + comp_area * w["stressed_area"]) / weight_sum
        partial = True
        comp_anom = None
    else:
        comp_anom = float(np.clip((mean_z + 3) / 6, 0, 1)) * 100  # z=-3→0, z=+3→100
        score = (comp_ndvi * w["ndvi"] + comp_area * w["stressed_area"]
                 + comp_anom * w["anomaly"])
        partial = False

    score = int(round(np.clip(score, 0, 100)))
    label, colour = _severity_label(score)
    return {
        "score": score,
        "label": label,
        "colour": colour,
        "partial": partial,
        "components": {
            "ndvi": round(comp_ndvi, 1),
            "stressed_area": round(comp_area, 1),
            "anomaly": round(comp_anom, 1) if comp_anom is not None else None,
        },
    }


def _severity_label(score: int) -> tuple[str, str]:
    for low, high, label, colour in SEVERITY_LABELS:
        if low <= score <= high:
            return label, colour
    return "Unknown", "#9E9E9E"


def summarize(ndvi: np.ndarray, mean_z: float | None = None) -> dict:
    """Full statistics bundle for a region's NDVI grid."""
    valid = _clean(ndvi)
    total_pixels = int(np.asarray(ndvi).size)
    valid_pixels = int(valid.size)
    water_pixels = total_pixels - valid_pixels

    if valid_pixels == 0:
        return {
            "mean": None, "median": None, "std": None, "min": None, "max": None,
            "valid_pixels": 0, "total_pixels": total_pixels, "water_pixels": water_pixels,
            "zones": classify_zones(ndvi),
            "severity": severity_score(0.0, 100.0, mean_z),
            "note": "No vegetated pixels found — the area may be water, cloud, or bare.",
        }

    mean = float(valid.mean())
    zones = classify_zones(ndvi)
    stressed_pct = zones["severe"]["pct"] + zones["moderate"]["pct"]

    return {
        "mean": round(mean, 4),
        "median": round(float(np.median(valid)), 4),
        "std": round(float(valid.std()), 4),
        "min": round(float(valid.min()), 4),
        "max": round(float(valid.max()), 4),
        "p10": round(float(np.percentile(valid, 10)), 4),
        "p90": round(float(np.percentile(valid, 90)), 4),
        "valid_pixels": valid_pixels,
        "total_pixels": total_pixels,
        "water_pixels": water_pixels,
        "coverage_pct": round(100 * valid_pixels / total_pixels, 1) if total_pixels else 0.0,
        "zones": zones,
        "stressed_area_pct": round(stressed_pct, 2),
        "severity": severity_score(mean, stressed_pct, mean_z),
    }
