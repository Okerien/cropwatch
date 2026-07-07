"""GeoJSON parsing, validation, and lightweight geometry math.

Phase 1 avoids the heavy geospatial stack (shapely/rasterio) on purpose so the
backend installs and boots in seconds. The maths we need here — bounding box,
spherical polygon area, point-in-polygon, centroid — is small and exact enough
for validation and demo-grid generation. Shapely arrives in Phase 3 for the
shapefile/repair work that genuinely needs it.
"""
from __future__ import annotations

import hashlib
import json
import math
from typing import Any

from .config_bridge import config
from .errors import ValidationError

EARTH_RADIUS_KM = 6371.0088


# --------------------------------------------------------------------------- #
# Parsing / normalising                                                        #
# --------------------------------------------------------------------------- #
def extract_polygons(geojson: Any) -> list[list[list[list[float]]]]:
    """Return a list of polygons (each a list of linear rings) from any GeoJSON.

    Accepts a Feature, FeatureCollection, Geometry, or raw geometry dict with
    Polygon or MultiPolygon geometry. Raises ValidationError otherwise.
    """
    if not isinstance(geojson, dict):
        raise ValidationError("Area must be a GeoJSON object.")

    gtype = geojson.get("type")
    if gtype == "FeatureCollection":
        polys: list = []
        for feat in geojson.get("features", []):
            polys.extend(extract_polygons(feat))
        if not polys:
            raise ValidationError("The FeatureCollection contains no polygons.")
        return polys
    if gtype == "Feature":
        geom = geojson.get("geometry")
        if geom is None:
            raise ValidationError("Feature has no geometry.")
        return extract_polygons(geom)
    if gtype == "Polygon":
        return [_validate_polygon(geojson.get("coordinates"))]
    if gtype == "MultiPolygon":
        coords = geojson.get("coordinates")
        if not isinstance(coords, list):
            raise ValidationError("MultiPolygon coordinates are malformed.")
        return [_validate_polygon(p) for p in coords]

    raise ValidationError(
        f"Geometry type {gtype!r} is not supported — please provide a Polygon "
        "or MultiPolygon.",
        hint="Draw an area, search a place, or upload a Polygon GeoJSON.",
    )


def _validate_polygon(rings: Any) -> list[list[list[float]]]:
    if not isinstance(rings, list) or not rings:
        raise ValidationError("Polygon has no coordinate rings.")
    clean_rings = []
    for ring in rings:
        if not isinstance(ring, list) or len(ring) < 4:
            raise ValidationError("A polygon ring needs at least 4 points.")
        pts = []
        for pt in ring:
            if (not isinstance(pt, (list, tuple)) or len(pt) < 2
                    or not all(isinstance(c, (int, float)) for c in pt[:2])):
                raise ValidationError("Coordinate values must be [lon, lat] numbers.")
            lon, lat = float(pt[0]), float(pt[1])
            pts.append([lon, lat])
        clean_rings.append(pts)
    return clean_rings


# --------------------------------------------------------------------------- #
# Derived geometry                                                             #
# --------------------------------------------------------------------------- #
def bounding_box(polygons: list) -> tuple[float, float, float, float]:
    """Return (min_lon, min_lat, max_lon, max_lat) across all polygons."""
    min_lon = min_lat = math.inf
    max_lon = max_lat = -math.inf
    for poly in polygons:
        for ring in poly:
            for lon, lat in ring:
                min_lon, max_lon = min(min_lon, lon), max(max_lon, lon)
                min_lat, max_lat = min(min_lat, lat), max(max_lat, lat)
    if not math.isfinite(min_lon):
        raise ValidationError("Could not compute a bounding box for this area.")
    return (min_lon, min_lat, max_lon, max_lat)


def _ring_area_m2(ring: list[list[float]]) -> float:
    """Spherical polygon area (m^2) via the shoelace formula on a sphere."""
    if len(ring) < 4:
        return 0.0
    total = 0.0
    r = EARTH_RADIUS_KM * 1000.0
    n = len(ring)
    for i in range(n):
        lon1, lat1 = ring[i]
        lon2, lat2 = ring[(i + 1) % n]
        total += math.radians(lon2 - lon1) * (
            2 + math.sin(math.radians(lat1)) + math.sin(math.radians(lat2))
        )
    return abs(total * r * r / 2.0)


def area_km2(polygons: list) -> float:
    """Total area in km^2 (outer rings minus holes)."""
    total = 0.0
    for poly in polygons:
        for i, ring in enumerate(poly):
            a = _ring_area_m2(ring) / 1e6
            total += a if i == 0 else -a
    return total


def centroid(polygons: list) -> tuple[float, float]:
    """Area-agnostic centroid of the outer rings (good enough for labelling)."""
    xs, ys, n = 0.0, 0.0, 0
    for poly in polygons:
        for lon, lat in poly[0][:-1]:
            xs += lon
            ys += lat
            n += 1
    if n == 0:
        raise ValidationError("Empty geometry.")
    return (xs / n, ys / n)


def point_in_polygon(lon: float, lat: float, poly: list[list[list[float]]]) -> bool:
    """Ray-casting test against a polygon's outer ring minus its holes."""
    def in_ring(ring):
        inside = False
        n = len(ring)
        j = n - 1
        for i in range(n):
            xi, yi = ring[i]
            xj, yj = ring[j]
            if (yi > lat) != (yj > lat):
                x_cross = (xj - xi) * (lat - yi) / (yj - yi + 1e-15) + xi
                if lon < x_cross:
                    inside = not inside
            j = i
        return inside

    if not in_ring(poly[0]):
        return False
    for hole in poly[1:]:
        if in_ring(hole):
            return False
    return True


# --------------------------------------------------------------------------- #
# Validation entry point                                                       #
# --------------------------------------------------------------------------- #
def validate_area(geojson: Any) -> dict:
    """Validate a requested area and return normalised geometry + metadata.

    Checks MODIS latitude coverage and the AppEEARS single-task area ceiling,
    returning plain-English errors the frontend can show verbatim.
    """
    polygons = extract_polygons(geojson)
    min_lon, min_lat, max_lon, max_lat = bounding_box(polygons)

    if min_lat < config.LAT_MIN or max_lat > config.LAT_MAX:
        raise ValidationError(
            f"This area falls outside MODIS coverage (must be between "
            f"{config.LAT_MIN}° and {config.LAT_MAX}° latitude).",
            code="out_of_coverage",
        )
    if not (config.LON_MIN <= min_lon <= config.LON_MAX
            and config.LON_MIN <= max_lon <= config.LON_MAX):
        raise ValidationError("Longitude values must be between -180° and 180°.")

    area = area_km2(polygons)
    if area > config.MAX_AREA_KM2:
        raise ValidationError(
            f"This area is {area:,.0f} km² — larger than the {config.MAX_AREA_KM2:,} "
            "km² limit for a single request.",
            code="area_too_large",
            hint="Zoom in or split the area into smaller regions.",
        )
    if area < config.MIN_AREA_KM2:
        raise ValidationError(
            "This area is too small to contain even one satellite pixel "
            "(each pixel is ~6.25 hectares).",
            code="area_too_small",
        )

    return {
        "polygons": polygons,
        "bbox": [min_lon, min_lat, max_lon, max_lat],
        "area_km2": round(area, 2),
        "centroid": list(centroid(polygons)),
    }


def geometry_hash(geojson: Any) -> str:
    """Stable short hash of a geometry, used for cache keys and task IDs."""
    canonical = json.dumps(geojson, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]
