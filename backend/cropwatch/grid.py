"""Shared grid model + JSON serialisation for NDVI rasters.

Both the synthetic demo engine and the real AppEEARS client produce data in this
same shape, so everything downstream (stats, routes, the frontend canvas) is
source-agnostic. Row 0 is the northernmost row; columns run west→east.

Serialisation deliberately sends a flat row-major array plus grid metadata
(bbox + rows + cols) rather than {lat, lon, ndvi} per pixel. For a 160×160 grid
that is ~25k numbers instead of ~75k, and the frontend reconstructs exact pixel
positions from the geotransform in one pass.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .config_bridge import config


@dataclass
class NDVIGrid:
    ndvi: np.ndarray                       # 2D float array, NaN = no-data
    bbox: list[float]                      # [min_lon, min_lat, max_lon, max_lat]
    source: str                            # "demo" | "appeears"

    @property
    def rows(self) -> int:
        return int(self.ndvi.shape[0])

    @property
    def cols(self) -> int:
        return int(self.ndvi.shape[1])

    def cellsize(self) -> list[float]:
        min_lon, min_lat, max_lon, max_lat = self.bbox
        return [(max_lon - min_lon) / self.cols, (max_lat - min_lat) / self.rows]

    def to_payload(self, round_dp: int = 3) -> dict:
        """Compact JSON-ready representation for the frontend."""
        arr = np.where(np.isfinite(self.ndvi), self.ndvi, np.nan)
        flat = [
            None if not np.isfinite(v) else round(float(v), round_dp)
            for v in arr.ravel(order="C")
        ]
        return {
            "grid": {
                "rows": self.rows,
                "cols": self.cols,
                "bbox": [round(c, 6) for c in self.bbox],
                "cellsize_deg": [round(c, 8) for c in self.cellsize()],
                "row_order": "north_to_south",
                "nodata_below": config.NDVI_NODATA_BELOW,
            },
            "ndvi": flat,
        }


def grid_dimensions(bbox: list[float]) -> tuple[int, int]:
    """Choose a grid size at ~250 m spacing, capped for payload sanity."""
    min_lon, min_lat, max_lon, max_lat = bbox
    span_lon = max(max_lon - min_lon, 1e-6)
    span_lat = max(max_lat - min_lat, 1e-6)
    cols = int(np.clip(round(span_lon / config.NATIVE_RES_DEG), 8, config.MAX_GRID_CELLS))
    rows = int(np.clip(round(span_lat / config.NATIVE_RES_DEG), 8, config.MAX_GRID_CELLS))
    return rows, cols
