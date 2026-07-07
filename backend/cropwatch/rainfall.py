"""Precipitation anomaly + NDVI–rainfall correlation (spec Features 5 and 16).

Rainfall is what turns CropWatch from "vegetation is stressed" into "vegetation
is stressed *because of drought*" — or, when the correlation is weak, "the stress
is NOT rain-driven, investigate pests/disease/soil." That diagnostic is the
single most decision-relevant relationship in the tool.

Real CHIRPS access (OpenDAP/GeoTIFF) lands with the geospatial stack in a later
build; here the demo engine produces a climatologically-shaped rainfall series
whose interannual anomaly is driven by the *same* latent signal as the region's
NDVI (with rainfall leading vegetation), so the correlation the frontend plots is
genuine and the "less rain → browner" story holds. Labelled ``source: "demo"``.
"""
from __future__ import annotations

import math
from datetime import date, timedelta

import numpy as np

from . import demo
from .config_bridge import config
from .geometry import geometry_hash

# --------------------------------------------------------------------------- #
# Rainfall climatology                                                        #
# --------------------------------------------------------------------------- #
def _annual_mm(clat: float) -> float:
    a = abs(clat)
    return (300
            + 1400 * math.exp(-((a - 2) / 10.0) ** 2)     # humid tropics
            + 400 * math.exp(-((a - 45) / 12.0) ** 2))    # temperate belt


def _monthly_climatology(clat: float) -> np.ndarray:
    """12 monthly mean rainfall totals (mm), shaped by a single wet season."""
    peak = 8 if clat >= 0 else 2         # N tropics peak ~Aug, S ~Feb
    k = 1.6
    months = np.arange(1, 13)
    weights = np.exp(k * np.cos(2 * math.pi * (months - peak) / 12.0))
    weights /= weights.sum()
    return weights * _annual_mm(clat)


# --------------------------------------------------------------------------- #
# Periods                                                                      #
# --------------------------------------------------------------------------- #
def _periods(start: date, end: date):
    """Yield (label, mid_date) buckets — weekly for <6mo ranges, else monthly."""
    span_days = (end - start).days
    if span_days <= 190:
        d = start
        while d <= end:
            yield d.strftime("%d %b"), d + timedelta(days=3)
            d += timedelta(days=7)
    else:
        y, m = start.year, start.month
        while date(y, m, 1) <= end:
            yield date(y, m, 15).strftime("%b %Y"), date(y, m, 15)
            m += 1
            if m > 12:
                m, y = 1, y + 1


def _anomaly_factor(seed: int, mid: date, ndvi_anom: float) -> float:
    """Rainfall multiplier around 1.0, driven by the region's latent good/bad-year
    signal (shared with NDVI) plus intra-seasonal noise. Rainfall leads NDVI."""
    rng = np.random.default_rng((seed ^ (mid.toordinal() * 2246822519)) % (2 ** 31))
    noise = float(rng.normal(0, 0.14))
    factor = 1.0 + ndvi_anom * 2.4 + noise
    return float(np.clip(factor, 0.15, 2.1))


# --------------------------------------------------------------------------- #
# Verbal scale (Feature 16)                                                    #
# --------------------------------------------------------------------------- #
def _corr_label(r: float) -> str:
    if r < 0:
        return "inverse"
    if r < 0.2:
        return "very weak"
    if r < 0.4:
        return "weak"
    if r < 0.6:
        return "moderate positive"
    return "strong positive"


def _corr_note(r: float) -> str | None:
    if r < 0.4:
        return (f"Correlation is weak ({r:.2f}) — rainfall alone does not explain "
                "the observed vegetation stress. Consider field investigation for "
                "pest, disease, or soil-related causes.")
    return None


# --------------------------------------------------------------------------- #
# Public entry point                                                          #
# --------------------------------------------------------------------------- #
def compute(bbox: list[float], start: date, end: date,
            polygons: list | None = None) -> dict:
    min_lon, min_lat, max_lon, max_lat = bbox
    clat = (min_lat + max_lat) / 2.0
    clim = _monthly_climatology(clat)

    # Derive a deterministic seed + polygon from the bbox when no polygon given.
    if polygons is None:
        rect = {"type": "Polygon", "coordinates": [[
            [min_lon, min_lat], [max_lon, min_lat], [max_lon, max_lat],
            [min_lon, max_lat], [min_lon, min_lat]]]}
        polygons = [rect["coordinates"]]
        seed_hash = geometry_hash(rect)
    else:
        seed_hash = geometry_hash({"type": "MultiPolygon",
                                   "coordinates": [[[list(p) for p in ring]
                                                    for ring in poly] for poly in polygons]})
    seed = int(seed_hash, 16) % (2 ** 31)

    bars, rain_series, ndvi_series = [], [], []
    for label, mid in _periods(start, end):
        clim_mm = float(clim[mid.month - 1])
        ndvi_anom = demo._year_shift(seed, mid.year)
        factor = _anomaly_factor(seed, mid, ndvi_anom)
        actual = clim_mm * factor / (4.3 if (end - start).days <= 190 else 1.0)  # weekly share
        anomaly_pct = round(100 * factor, 1)

        ndvi_mean = demo.region_mean_at(bbox, polygons, seed_hash, mid)
        bars.append({
            "period": label,
            "date": mid.isoformat(),
            "rainfall_mm": round(actual, 1),
            "climatology_mm": round(clim_mm / (4.3 if (end - start).days <= 190 else 1.0), 1),
            "anomaly_pct": anomaly_pct,
            "deficit": anomaly_pct < 100,
        })
        rain_series.append(factor)
        ndvi_series.append(ndvi_mean if ndvi_mean is not None else np.nan)

    corr = _pearson(ndvi_series, rain_series)
    return {
        "aggregation": "weekly" if (end - start).days <= 190 else "monthly",
        "start": start.isoformat(),
        "end": end.isoformat(),
        "bars": bars,
        "baseline_pct": 100,
        "deficit_threshold_pct": 75,
        "correlation": {
            "coefficient": round(corr, 2) if corr is not None else None,
            "label": _corr_label(corr) if corr is not None else "n/a",
            "note": _corr_note(corr) if corr is not None else None,
            "display": (f"Rainfall-NDVI correlation: {corr:.2f} ({_corr_label(corr)})"
                        if corr is not None else "Rainfall-NDVI correlation: n/a"),
        },
        "source": "demo",
    }


def _pearson(a, b) -> float | None:
    av, bv = np.array(a, dtype=float), np.array(b, dtype=float)
    mask = np.isfinite(av) & np.isfinite(bv)
    if mask.sum() < 3 or av[mask].std() < 1e-9 or bv[mask].std() < 1e-9:
        return None
    return float(np.corrcoef(av[mask], bv[mask])[0, 1])
