"""Stress-zone vector polygons (Features 2 + 12) — GIS-ready GeoJSON.

Converts the classified NDVI grid into per-class MultiPolygons using greedy
row-run rectangle decomposition: horizontal runs of same-class pixels are merged
with vertically adjacent identical runs into rectangles, each emitted in real
coordinates. Dependency-free (no scipy/rasterio), exact to the pixel grid, and
imports cleanly into QGIS/ArcGIS. Typically ~100× fewer vertices than one
polygon per pixel.
"""
from __future__ import annotations

import math

import numpy as np

from .config_bridge import config


def _class_index(ndvi: np.ndarray) -> np.ndarray:
    """Integer class per pixel (-1 = no-data) using the configured thresholds."""
    idx = np.full(ndvi.shape, -1, dtype=np.int8)
    valid = np.isfinite(ndvi) & (ndvi >= config.NDVI_NODATA_BELOW)
    for i, (_, low, high, _) in enumerate(config.STRESS_ZONES):
        idx[valid & (ndvi >= low) & (ndvi < high)] = i
    return idx


def _runs_to_rects(idx: np.ndarray) -> dict[int, list[tuple]]:
    """Greedy decomposition into rectangles: (row0, row1_excl, col0, col1_excl)."""
    rows, cols = idx.shape
    open_rects: dict[tuple, list] = {}   # (class, c0, c1) -> [row0, row1)
    done: dict[int, list[tuple]] = {}

    for r in range(rows + 1):
        # Compute this row's runs (empty on the virtual last row to flush).
        runs = set()
        if r < rows:
            c = 0
            while c < cols:
                k = idx[r, c]
                if k < 0:
                    c += 1
                    continue
                c0 = c
                while c < cols and idx[r, c] == k:
                    c += 1
                runs.add((int(k), c0, c))
        # Extend or close open rectangles.
        still_open = {}
        for key, span in open_rects.items():
            if key in runs:
                span[1] = r + 1
                still_open[key] = span
                runs.discard(key)
            else:
                k, c0, c1 = key
                done.setdefault(k, []).append((span[0], span[1], c0, c1))
        for key in runs:                       # newly started runs
            still_open[key] = [r, r + 1]
        open_rects = still_open
    return done


def build_zones(ndvi: np.ndarray, bbox: list[float]) -> dict:
    """Return a GeoJSON FeatureCollection of stress-zone MultiPolygons."""
    rows, cols = ndvi.shape
    min_lon, min_lat, max_lon, max_lat = bbox
    dx = (max_lon - min_lon) / cols
    dy = (max_lat - min_lat) / rows
    clat = (min_lat + max_lat) / 2.0
    km_x = 111.32 * math.cos(math.radians(clat)) * dx
    km_y = 110.57 * dy
    px_km2 = km_x * km_y

    idx = _class_index(ndvi)
    rect_map = _runs_to_rects(idx)

    features = []
    for i, (name, low, high, colour) in enumerate(config.STRESS_ZONES):
        rects = rect_map.get(i, [])
        if not rects:
            continue
        polys = []
        px_count = 0
        for (r0, r1, c0, c1) in rects:
            px_count += (r1 - r0) * (c1 - c0)
            # Row 0 is the northern edge (max_lat).
            n = max_lat - r0 * dy
            s = max_lat - r1 * dy
            w = min_lon + c0 * dx
            e = min_lon + c1 * dx
            polys.append([[[w, s], [e, s], [e, n], [w, n], [w, s]]])
        vals = ndvi[idx == i]
        area_km2 = px_count * px_km2
        features.append({
            "type": "Feature",
            "geometry": {"type": "MultiPolygon", "coordinates": polys},
            "properties": {
                "stress_class": name,
                "ndvi_range": [low, min(high, 1.0)],
                "ndvi_mean": round(float(vals.mean()), 4) if vals.size else None,
                "pixel_count": int(px_count),
                "area_km2": round(area_km2, 2),
                "area_ha": round(area_km2 * 100, 1),
                "colour": colour,
                "rect_count": len(rects),
            },
        })

    return {"type": "FeatureCollection", "features": features}
