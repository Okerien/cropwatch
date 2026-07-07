"""Historical anomaly engine — z-scores, anomaly time series, analogue years.

This is the analytically sophisticated core (spec Modes 3 + Features 6, 7, 17).
Everything is computed pixel-by-pixel against a per-pixel historical baseline,
because "normal" NDVI varies within a single district by soil, topography, and
land use — a region-mean baseline would wash that out.
"""
from __future__ import annotations

import math
from datetime import date, timedelta

import numpy as np

from . import demo, faostat
from .config_bridge import config
from .stats import severity_score

# z-score anomaly categories (spec Feature 6 diverging blue-white-red scale).
Z_CATEGORIES = [
    ("severe_low", -math.inf, -2.0, "#B22222"),
    ("moderate_low", -2.0, -1.0, "#E8870A"),
    ("mild_low", -1.0, -0.5, "#F5D08A"),
    ("near_normal", -0.5, 0.5, "#FAFAFA"),
    ("mild_high", 0.5, 1.0, "#9ECAE1"),
    ("moderate_high", 1.0, 2.0, "#4292C6"),
    ("severe_high", 2.0, math.inf, "#1A237E"),
]

_MIN_STD = 1e-3  # below this the baseline is degenerate → z undefined


def _phi(z: float) -> float:
    """Standard-normal CDF — used to phrase 'worse than X% of years'."""
    return 0.5 * (1 + math.erf(z / math.sqrt(2)))


def _baseline(record: dict, window_years: list[int]):
    stack = np.stack([record[y] for y in window_years])         # (k, rows, cols)
    mean = np.nanmean(stack, axis=0)
    std = np.nanstd(stack, axis=0)
    std = np.where(std < _MIN_STD, np.nan, std)                 # guard degenerate pixels
    return mean, std


def _zscore(field: np.ndarray, mean: np.ndarray, std: np.ndarray) -> np.ndarray:
    return (field - mean) / std


def _z_payload(z: np.ndarray, bbox: list[float]) -> dict:
    rows, cols = z.shape
    flat = [None if not np.isfinite(v) else round(float(v), 3) for v in z.ravel()]
    min_lon, min_lat, max_lon, max_lat = bbox
    return {
        "grid": {
            "rows": rows, "cols": cols, "bbox": [round(c, 6) for c in bbox],
            "cellsize_deg": [round((max_lon - min_lon) / cols, 8),
                             round((max_lat - min_lat) / rows, 8)],
            "row_order": "north_to_south",
        },
        "zscore": flat,
    }


def _z_distribution(z: np.ndarray) -> dict:
    valid = z[np.isfinite(z)]
    total = int(valid.size)
    out = {}
    for name, low, high, colour in Z_CATEGORIES:
        count = int(((valid >= low) & (valid < high)).sum())
        out[name] = {"pixel_count": count,
                     "pct": round(100 * count / total, 2) if total else 0.0,
                     "colour": colour}
    return out


def _interpretation(mean_z: float, years: int) -> str:
    pct = _phi(mean_z) * 100
    if mean_z <= -0.5:
        return (f"This region is {abs(mean_z):.1f} standard deviations below the "
                f"{years}-year average — conditions this poor or worse have occurred "
                f"in roughly {pct:.1f}% of observations for this calendar period.")
    if mean_z >= 0.5:
        return (f"This region is {mean_z:.1f} standard deviations above the "
                f"{years}-year average — among the more favourable conditions on "
                f"record for this time of year.")
    return (f"This region is close to its {years}-year average for this calendar "
            "period (within half a standard deviation).")


# --------------------------------------------------------------------------- #
# Analogue Year Finder (Feature 7)                                            #
# --------------------------------------------------------------------------- #
def _spatial_correlation(a: np.ndarray, b: np.ndarray) -> float:
    """Pearson correlation between two z-score fields over shared valid pixels."""
    mask = np.isfinite(a) & np.isfinite(b)
    if mask.sum() < 8:
        return 0.0
    av, bv = a[mask], b[mask]
    if av.std() < 1e-6 or bv.std() < 1e-6:
        return 0.0
    return float(np.corrcoef(av, bv)[0, 1])


def _analogue_years(fields: dict, mean: np.ndarray, std: np.ndarray,
                    z_current: np.ndarray, area_meta: dict, seed_hash: str,
                    polygons: list) -> list[dict]:
    record = fields["record"]
    ctx = faostat.infer_context(area_meta["centroid"])
    record_years = sorted(record.keys())
    fao = faostat.fetch_yield_deviations(ctx["area_code"], ctx["item_code"], record_years)

    scored = []
    for year in record_years:
        z_year = _zscore(record[year], mean, std)
        corr = _spatial_correlation(z_current, z_year)
        mean_z = float(np.nanmean(z_year))
        scored.append((year, corr, mean_z))

    scored.sort(key=lambda t: t[1], reverse=True)
    top = scored[:3]

    out = []
    for year, corr, mean_z in top:
        if year in fao:
            yield_dev, yield_source = fao[year], "FAOSTAT"
        else:
            # Coherent modelled fallback: worse anomaly → lower yield.
            yield_dev = round(float(np.clip(mean_z * 11.0, -45, 30)), 1)
            yield_source = "modelled"
        out.append({
            "year": year,
            "correlation": round(corr, 3),
            "match_quality": "High" if corr >= 0.6 else ("Medium" if corr >= 0.35 else "Low"),
            "mean_z": round(mean_z, 2),
            "yield_deviation_pct": yield_dev,
            "yield_source": yield_source,
            "crop": ctx["crop"],
            "country": ctx["country"],
            "note": faostat.notable_event(ctx["country"], year),
            "season_sparkline": demo.season_mean_series(
                area_meta["bbox"], polygons, seed_hash, year, n_points=12),
        })
    return {"analogues": out, "context": ctx}


# --------------------------------------------------------------------------- #
# Anomaly time series (Feature 17)                                            #
# --------------------------------------------------------------------------- #
def _anomaly_time_series(bbox, polygons, seed_hash, target_date: date,
                         record_years: list[int], n_points: int = 12) -> dict:
    """Region-mean z-score per composite across the current season.

    Computed on a deliberately coarse grid: this is a spatial *average* per
    date, so full 250 m resolution buys nothing while costing ~25× the field
    generations. 40×40 gives an identical region mean far faster.
    """
    rows = cols = 40
    seed = int(seed_hash, 16) % (2 ** 31)
    mask = demo.polygon_mask(bbox, rows, cols, polygons)

    def region_mean(year, d):
        f = np.where(mask, demo._year_field(bbox, rows, cols, seed, d, year), np.nan)
        v = f[np.isfinite(f)]
        return float(v.mean()) if v.size else np.nan

    points = []
    for i in range(n_points):
        # even 8-day-ish steps across the season ending at target_date
        d = target_date - timedelta(days=(n_points - 1 - i) * config.COMPOSITE_DAYS)
        cur = region_mean(d.year, d)
        hist = [region_mean(y, _def_replace_year(d, y)) for y in record_years]
        hist = np.array([h for h in hist if np.isfinite(h)])
        if hist.size >= 3 and hist.std() > _MIN_STD and np.isfinite(cur):
            z = (cur - hist.mean()) / hist.std()
        else:
            z = None
        points.append({"date": d.isoformat(),
                       "mean_z": round(z, 3) if z is not None else None})

    # Trend over the last 4 points (spec: fitted direction indicator).
    ys = [p["mean_z"] for p in points[-4:] if p["mean_z"] is not None]
    slope = None
    if len(ys) >= 2:
        xs = np.arange(len(ys))
        slope = round(float(np.polyfit(xs, ys, 1)[0]), 3)
    return {"points": points, "recent_slope_per_composite": slope,
            "trend_summary": _trend_summary(slope)}


def _trend_summary(slope: float | None) -> str:
    if slope is None:
        return "Not enough data to determine a trend."
    if slope <= -0.1:
        return f"Conditions are deteriorating (~{abs(slope):.2f} SD per composite)."
    if slope >= 0.1:
        return f"Conditions are recovering (~{slope:.2f} SD per composite)."
    return "Conditions have been broadly stable."


def _def_replace_year(d: date, year: int) -> date:
    """date.replace that survives 29 Feb."""
    try:
        return d.replace(year=year)
    except ValueError:
        return d.replace(year=year, day=28)


# --------------------------------------------------------------------------- #
# Public entry point                                                          #
# --------------------------------------------------------------------------- #
def compute(bbox, polygons, seed_hash, target_date: date, years: int,
            area_meta: dict) -> dict:
    fields = demo.historical_fields(bbox, polygons, seed_hash, target_date)
    target_year = fields["target_year"]
    available = sorted(fields["record"].keys())
    window_years = [y for y in available if y >= target_year - years]
    if len(window_years) < 3:
        window_years = available            # not enough history yet — use all

    mean, std = _baseline(fields["record"], window_years)
    z_current = _zscore(fields["current"], mean, std)
    mean_z = float(np.nanmean(z_current))

    # Current-year absolute stats + severity WITH the anomaly component (Phase 2
    # completes the 3-component score that was 'partial' in Phase 1).
    from .stats import summarize
    stats = summarize(fields["current"], mean_z=mean_z)

    analogue = _analogue_years(fields, mean, std, z_current, area_meta, seed_hash, polygons)
    anomaly_series = _anomaly_time_series(bbox, polygons, seed_hash, target_date, window_years)

    return {
        "target_date": target_date.isoformat(),
        "comparison_years": years,
        "baseline_years_used": len(window_years),
        "baseline_range": [min(window_years), max(window_years)],
        **_z_payload(z_current, bbox),
        "z_distribution": _z_distribution(z_current),
        "mean_z": round(mean_z, 3),
        "interpretation": _interpretation(mean_z, years),
        "severity": stats["severity"],
        "stats": stats,
        "analogue_years": analogue["analogues"],
        "crop_context": analogue["context"],
        "anomaly_time_series": anomaly_series,
        "source": "demo",
        "area": {"bbox": area_meta["bbox"], "area_km2": area_meta["area_km2"],
                 "centroid": area_meta["centroid"]},
    }
