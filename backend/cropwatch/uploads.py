"""Shapefile → GeoJSON conversion and GeoJSON validation (spec §3.4, §3.5).

Shapefile parsing uses pyshp (pure Python, no binary build). Reprojection
(pyproj) and self-intersection repair (shapely) are treated as optional: if a
non-WGS84 .prj is present but pyproj isn't installed, we surface a clear warning
rather than silently mis-placing the boundary. This keeps the backend installable
in seconds while remaining correct about what it did and didn't do.
"""
from __future__ import annotations

import io
import zipfile

from .errors import ValidationError
from .geometry import bounding_box, extract_polygons, validate_area


def _find_member(names: list[str], ext: str) -> str | None:
    for n in names:
        if n.lower().endswith(ext) and not n.startswith("__MACOSX"):
            return n
    return None


def _is_wgs84(prj_text: str) -> bool:
    t = prj_text.upper()
    return ("WGS_1984" in t or "WGS 84" in t or "GCS_WGS_1984" in t
            or "4326" in t or not t.strip())


def _reproject_coords(features: list[dict], prj_text: str) -> tuple[list[dict], list[str]]:
    try:
        from pyproj import CRS, Transformer
    except ImportError:
        return features, ["The shapefile is not in WGS84 and coordinate "
                          "reprojection (pyproj) is not available in this build — "
                          "the boundary may appear in the wrong location."]
    try:
        transformer = Transformer.from_crs(CRS.from_wkt(prj_text), "EPSG:4326",
                                           always_xy=True)
    except Exception:
        return features, ["Could not interpret the .prj projection; assuming WGS84."]

    def tx(coords):
        if isinstance(coords[0], (int, float)):
            x, y = transformer.transform(coords[0], coords[1])
            return [x, y]
        return [tx(c) for c in coords]

    for f in features:
        f["geometry"]["coordinates"] = tx(f["geometry"]["coordinates"])
    return features, []


def convert_shapefile(zip_bytes: bytes) -> dict:
    try:
        import shapefile  # pyshp
    except ImportError as exc:  # pragma: no cover
        raise ValidationError("Shapefile support (pyshp) is not installed.",
                              status_code=501) from exc

    try:
        zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
    except zipfile.BadZipFile as exc:
        raise ValidationError("The uploaded file is not a valid ZIP archive.") from exc

    names = [n for n in zf.namelist() if not n.endswith("/")]
    shp = _find_member(names, ".shp")
    dbf = _find_member(names, ".dbf")
    shx = _find_member(names, ".shx")
    prj = _find_member(names, ".prj")

    if not shp:
        raise ValidationError("The ZIP is missing the required .shp (geometry) file.")
    if not dbf:
        raise ValidationError("The ZIP is missing the required .dbf (attributes) file.")

    warnings = []
    try:
        reader = shapefile.Reader(
            shp=io.BytesIO(zf.read(shp)),
            dbf=io.BytesIO(zf.read(dbf)),
            shx=io.BytesIO(zf.read(shx)) if shx else None,
        )
        fields = [f[0] for f in reader.fields[1:]]  # skip DeletionFlag
        features = []
        for sr in reader.shapeRecords():
            geom = sr.shape.__geo_interface__
            if geom.get("type") not in {"Polygon", "MultiPolygon"}:
                continue
            props = dict(zip(fields, list(sr.record)))
            features.append({"type": "Feature", "geometry": geom, "properties": props})
    except Exception as exc:
        raise ValidationError(f"Could not read the shapefile: {exc}") from exc

    if not features:
        raise ValidationError("The shapefile contains no polygon geometry.")

    if prj:
        prj_text = zf.read(prj).decode("utf-8", errors="ignore")
        if not _is_wgs84(prj_text):
            features, warns = _reproject_coords(features, prj_text)
            warnings += warns
    else:
        warnings.append("No .prj file found — assuming WGS84 (EPSG:4326) coordinates.")

    fc = {"type": "FeatureCollection", "features": features}
    try:
        bbox = list(bounding_box([r for f in features for r in extract_polygons(f)]))
    except ValidationError:
        bbox = None

    return {"geojson": fc, "feature_count": len(features),
            "attribute_fields": fields, "bbox": bbox, "warnings": warnings}


def inspect_geojson(obj) -> dict:
    """Validate an uploaded GeoJSON and return usable metadata for the frontend."""
    meta = validate_area(obj)              # raises plain-English errors
    features = []
    if isinstance(obj, dict) and obj.get("type") == "FeatureCollection":
        for i, f in enumerate(obj.get("features", [])):
            props = f.get("properties") or {}
            name = props.get("name") or props.get("NAME") or f"Feature {i + 1}"
            features.append({"index": i, "name": name, "properties": props})
    return {
        "valid": True,
        "bbox": meta["bbox"],
        "area_km2": meta["area_km2"],
        "centroid": meta["centroid"],
        "feature_count": max(1, len(features)),
        "features": features,
    }
