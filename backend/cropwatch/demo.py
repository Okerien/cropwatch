"""Synthetic NDVI engine — plausible satellite data with no NASA credentials.

Why this exists: NASA Earthdata approval, AppEEARS task latency, and free-tier
quotas make it painful to build or demo a UI against the live pipeline. This
engine produces vegetation fields that are (a) deterministic per region+date so
caching and repeat visits are stable, (b) spatially coherent via multi-octave
value noise so heatmaps look like real terrain rather than TV static, and
(c) regionally and seasonally calibrated so the Sahel reads drier than the humid
tropics and the growing season greens up and browns down at the right time.

It is clearly labelled ``source: "demo"`` everywhere it surfaces, and the moment
real Earthdata credentials are configured the routes prefer AppEEARS instead.
"""
from __future__ import annotations

import math
from datetime import date
from functools import lru_cache

import numpy as np

from .config_bridge import config
from .geometry import point_in_polygon
from .grid import NDVIGrid, grid_dimensions


# --------------------------------------------------------------------------- #
# Coherent noise                                                               #
# --------------------------------------------------------------------------- #
def _resize_bilinear(coarse: np.ndarray, rows: int, cols: int) -> np.ndarray:
    gh, gw = coarse.shape
    ry = np.linspace(0, gh - 1, rows)
    rx = np.linspace(0, gw - 1, cols)
    x0 = np.floor(rx).astype(int)
    x1 = np.minimum(x0 + 1, gw - 1)
    wx = rx - x0
    col_i = coarse[:, x0] * (1 - wx) + coarse[:, x1] * wx      # (gh, cols)
    y0 = np.floor(ry).astype(int)
    y1 = np.minimum(y0 + 1, gh - 1)
    wy = (ry - y0)[:, None]
    return col_i[y0, :] * (1 - wy) + col_i[y1, :] * wy         # (rows, cols)


def _value_noise(rows: int, cols: int, seed: int, octaves: int = 5) -> np.ndarray:
    """Fractal value noise in [0, 1] — the basis of realistic terrain patterns."""
    field = np.zeros((rows, cols), dtype=np.float64)
    amp, total = 1.0, 0.0
    for o in range(octaves):
        freq = 2 ** o
        gh, gw = max(2, freq + 1), max(2, freq + 1)
        rng = np.random.default_rng(seed + o * 1009)
        coarse = rng.random((gh, gw))
        field += amp * _resize_bilinear(coarse, rows, cols)
        total += amp
        amp *= 0.5
    return field / total


# --------------------------------------------------------------------------- #
# Regional + seasonal calibration                                             #
# --------------------------------------------------------------------------- #
def _regional_base(lat: float) -> float:
    """Baseline greenness by latitude band (humid tropics green, arid dips)."""
    a = abs(lat)
    base = (0.25
            + 0.45 * math.exp(-((a - 2) / 9.0) ** 2)     # equatorial belt
            - 0.15 * math.exp(-((a - 22) / 8.0) ** 2)    # subtropical deserts
            + 0.20 * math.exp(-((a - 45) / 12.0) ** 2))  # temperate croplands
    return float(np.clip(base, 0.12, 0.80))


def _seasonal_offset(lat: float, day_of_year: int) -> float:
    peak = 196 if lat >= 0 else 196 + 182       # N peaks ~mid-July, S ~mid-Jan
    phase = 2 * math.pi * ((day_of_year - peak) % 365) / 365.0
    return 0.12 * math.cos(phase)


# --------------------------------------------------------------------------- #
# Field construction                                                          #
# --------------------------------------------------------------------------- #
@lru_cache(maxsize=1024)
def _stable_field_cached(seed: int, rows: int, cols: int, clat_q: float,
                         doy: int) -> np.ndarray:
    """Cacheable core of the stable field.

    The time-stable field depends only on (seed, grid shape, centre latitude,
    day-of-year) — never on the year. So a 20-year stack for one calendar window
    computes this ONCE and reuses it, which is what makes historical mode fast.
    The returned array is treated as read-only by callers (they always add to it,
    producing a new array), so sharing the cached instance is safe.
    """
    base = _regional_base(clat_q) + _seasonal_offset(clat_q, doy)
    texture = (_value_noise(rows, cols, seed) - 0.5) * 0.36
    gy = np.linspace(-1, 1, rows)[:, None]
    gx = np.linspace(-1, 1, cols)[None, :]
    grad_angle = (seed % 360) * math.pi / 180.0
    gradient = 0.08 * (gy * math.sin(grad_angle) + gx * math.cos(grad_angle))
    field = base + texture + gradient

    if seed % 3 == 0:  # occasional visible stress lobe so the map tells a story
        cy, cx = (seed % 100) / 100.0, ((seed // 100) % 100) / 100.0
        yy = np.linspace(0, 1, rows)[:, None]
        xx = np.linspace(0, 1, cols)[None, :]
        lobe = np.exp(-(((yy - cy) / 0.35) ** 2 + ((xx - cx) / 0.35) ** 2))
        field = field - 0.30 * lobe
    field.flags.writeable = False
    return field


def _stable_field(bbox, rows, cols, seed: int, composite_date: date) -> np.ndarray:
    """Regional/seasonal base + texture + lobe — the year-invariant backbone."""
    min_lon, min_lat, max_lon, max_lat = bbox
    clat = round((min_lat + max_lat) / 2.0, 3)
    return _stable_field_cached(seed, rows, cols, clat,
                                composite_date.timetuple().tm_yday)


def _year_shift(seed: int, year: int) -> float:
    """A whole-region good/bad-year offset (drought vs bumper), ~N(0, 0.06)."""
    rng = np.random.default_rng((seed ^ (year * 2654435761)) % (2 ** 31))
    return float(np.clip(rng.normal(0, 0.06), -0.18, 0.18))


def _year_field(bbox, rows, cols, seed: int, composite_date: date,
                year: int | None) -> np.ndarray:
    """Stable backbone + per-year spatial variation + per-year offset, clipped."""
    field = _stable_field(bbox, rows, cols, seed, composite_date)
    if year is not None:
        yr_seed = (seed + year * 7919) % (2 ** 31)
        year_var = (_value_noise(rows, cols, yr_seed, octaves=4) - 0.5) * 0.14
        field = field + year_var + _year_shift(seed, year)
    return np.clip(field, -0.05, 0.95)


# Mask cache: the polygon mask never changes for a given geometry + grid shape,
# but the pure-Python ray-casting loop costs seconds at 160×160. Keyed by the
# geometry hash the callers already carry.
_mask_cache: dict[tuple, np.ndarray] = {}


def polygon_mask(bbox, rows, cols, polygons, cache_key: str | None = None) -> np.ndarray:
    """Boolean grid: True where a cell centre falls inside the requested area."""
    if cache_key is not None:
        key = (cache_key, rows, cols)
        hit = _mask_cache.get(key)
        if hit is not None:
            return hit

    min_lon, min_lat, max_lon, max_lat = bbox
    lon_centers = np.linspace(min_lon, max_lon, cols, endpoint=False) + (max_lon - min_lon) / (2 * cols)
    lat_centers = np.linspace(max_lat, min_lat, rows, endpoint=False) - (max_lat - min_lat) / (2 * rows)
    mask = np.zeros((rows, cols), dtype=bool)
    for r in range(rows):
        lat = float(lat_centers[r])
        for c in range(cols):
            lon = float(lon_centers[c])
            if any(point_in_polygon(lon, lat, p) for p in polygons):
                mask[r, c] = True

    if cache_key is not None:
        if len(_mask_cache) > 256:
            _mask_cache.clear()
        _mask_cache[(cache_key, rows, cols)] = mask
    return mask


# --------------------------------------------------------------------------- #
# Public generators                                                           #
# --------------------------------------------------------------------------- #
def generate(bbox: list[float], polygons: list, seed_hash: str,
             composite_date: date) -> NDVIGrid:
    """Single snapshot (used by /ndvi and the time slider).

    Includes the per-year field so composites vary across dates the way real
    imagery does — the time-slider animation shows evolving spatial pattern,
    not just a uniform seasonal brightening.
    """
    rows, cols = grid_dimensions(bbox)
    seed = int(seed_hash, 16) % (2 ** 31)
    ndvi = _year_field(bbox, rows, cols, seed, composite_date, composite_date.year)
    mask = polygon_mask(bbox, rows, cols, polygons, cache_key=seed_hash)
    ndvi = np.where(mask, ndvi, np.nan)
    return NDVIGrid(ndvi=ndvi, bbox=list(bbox), source="demo")


def historical_fields(bbox: list[float], polygons: list, seed_hash: str,
                      target_date: date, record_start: int = 2001) -> dict:
    """Build a masked NDVI stack for the same calendar window across many years.

    Returns the current-year field, a {year: masked field} record from
    ``record_start`` to the year before target, and the shared mask — everything
    the z-score and analogue-year engines need, with the polygon mask computed
    once and reused across all years.
    """
    rows, cols = grid_dimensions(bbox)
    seed = int(seed_hash, 16) % (2 ** 31)
    mask = polygon_mask(bbox, rows, cols, polygons, cache_key=seed_hash)

    def masked(year):
        return np.where(mask, _year_field(bbox, rows, cols, seed, target_date, year), np.nan)

    target_year = target_date.year
    record = {y: masked(y) for y in range(record_start, target_year)}
    current = masked(target_year)
    return {
        "rows": rows, "cols": cols, "bbox": list(bbox), "mask": mask,
        "current": current, "record": record, "target_year": target_year,
        "seed": seed,
    }


def region_mean_at(bbox, polygons, seed_hash, d: date, grid: int = 40) -> float | None:
    """Masked region-mean NDVI at a single date on a coarse grid (cheap, reusable)."""
    seed = int(seed_hash, 16) % (2 ** 31)
    mask = polygon_mask(bbox, grid, grid, polygons, cache_key=seed_hash)
    field = np.where(mask, _year_field(bbox, grid, grid, seed, d, d.year), np.nan)
    vals = field[np.isfinite(field)]
    return float(vals.mean()) if vals.size else None


def season_mean_series(bbox, polygons, seed_hash, year: int,
                       n_points: int = 12) -> list[float]:
    """Masked-mean NDVI across a year's growing season (for analogue sparklines).

    A region average per date, so a coarse grid gives the same curve far cheaper.
    """
    rows = cols = 40
    seed = int(seed_hash, 16) % (2 ** 31)
    mask = polygon_mask(bbox, rows, cols, polygons, cache_key=seed_hash)
    out = []
    for i in range(n_points):
        doy = int(15 + i * (350 / n_points))
        d = date(year, 1, 1) + __import__("datetime").timedelta(days=doy - 1)
        field = np.where(mask, _year_field(bbox, rows, cols, seed, d, year), np.nan)
        vals = field[np.isfinite(field)]
        out.append(round(float(vals.mean()), 3) if vals.size else None)
    return out
