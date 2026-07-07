"""HTTP routes for Phase 1 — NDVI snapshot, task status, health.

Thin controllers: parse the request, delegate to the service layer, shape the
response. All error translation happens through the shared error handlers wired
in :mod:`app`.
"""
from __future__ import annotations

from datetime import datetime, timezone

from flask import Blueprint, g, jsonify, request

from . import __version__
from .cache import cache
from .config_bridge import config
from .errors import NotFoundError, ValidationError
from .ratelimit import enforce
from .tasks import (create_historical, create_ndvi_task, default_window,
                    get_task)

bp = Blueprint("api", __name__)


def _check(kind: str) -> None:
    """Enforce the rate limit for an endpoint class and stash header metadata."""
    g.rate_meta = enforce(kind)


@bp.after_request
def _add_rate_headers(response):
    meta = getattr(g, "rate_meta", None)
    if meta:
        response.headers["X-RateLimit-Limit"] = str(meta["limit"])
        response.headers["X-RateLimit-Remaining"] = str(meta["remaining"])
        response.headers["X-RateLimit-Reset"] = str(meta["reset"])
    return response


def _truthy(value: str | None) -> bool:
    return str(value).lower() in {"1", "true", "yes", "on"} if value else False


def _parse_date_arg(value, fallback):
    from datetime import datetime
    if not value:
        return fallback
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        raise ValidationError(f"Date {value!r} must be YYYY-MM-DD.")


@bp.post("/ndvi")
def post_ndvi():
    """Submit an NDVI snapshot request for a GeoJSON area.

    Body: { "geojson": <Feature|FeatureCollection|Geometry>,
            "start_date"?: "YYYY-MM-DD", "end_date"?: "YYYY-MM-DD",
            "product"?: "MOD13Q1"|"MYD13Q1" }
    Returns the task envelope (with the result inline when it completes instantly
    in demo mode).
    """
    _check("ndvi")
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        raise ValidationError("Request body must be JSON.")
    geojson = body.get("geojson") or body.get("geometry") or body.get("area")
    if geojson is None:
        raise ValidationError("Provide an area as 'geojson'.",
                              hint="Draw, search, or upload a Polygon.")

    force_demo = _truthy(request.args.get("demo")) or bool(body.get("demo"))
    task = create_ndvi_task(
        geojson=geojson,
        start_str=body.get("start_date"),
        end_str=body.get("end_date"),
        product=body.get("product", "MOD13Q1"),
        force_demo=force_demo,
    )
    status = 200 if task.get("status") == "complete" else 202
    return jsonify(task), status


@bp.get("/ndvi/status/<task_id>")
def get_ndvi_status(task_id: str):
    """Poll a submitted task. Returns progress while processing, result when done."""
    task = get_task(task_id)
    if task is None:
        raise NotFoundError(
            "That task was not found — it may have expired from the cache. "
            "Please resubmit the area.")
    status = 200 if task.get("status") in {"complete", "failed"} else 202
    return jsonify(task), status


@bp.post("/historical")
def post_historical():
    """Historical anomaly analysis (z-score map, analogue years, anomaly series).

    Body: { "geojson": <area>, "target_date"?: "YYYY-MM-DD",
            "years"?: 5|10|20 }
    """
    _check("default")
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        raise ValidationError("Request body must be JSON.")
    geojson = body.get("geojson") or body.get("geometry") or body.get("area")
    if geojson is None:
        raise ValidationError("Provide an area as 'geojson'.")

    result = create_historical(
        geojson=geojson,
        target_str=body.get("target_date"),
        years=int(body.get("years", 20)),
    )
    return jsonify(result), 200


@bp.get("/rainfall")
def get_rainfall():
    """Precipitation anomaly bars + NDVI–rainfall correlation for a bbox.

    Query: bbox=min_lon,min_lat,max_lon,max_lat & start_date & end_date (optional).
    """
    from .rainfall import compute as rainfall_compute

    _check("default")
    bbox_str = request.args.get("bbox")
    if not bbox_str:
        raise ValidationError("Provide bbox=min_lon,min_lat,max_lon,max_lat.")
    try:
        bbox = [float(x) for x in bbox_str.split(",")]
        assert len(bbox) == 4
    except (ValueError, AssertionError):
        raise ValidationError("bbox must be four numbers: min_lon,min_lat,max_lon,max_lat.")

    start_default, end_default = default_window()
    start = _parse_date_arg(request.args.get("start_date"), start_default)
    end = _parse_date_arg(request.args.get("end_date"), end_default)
    key = f"rain:{bbox_str}:{start}:{end}"
    cached = cache.get(key)
    if cached:
        out = dict(cached); out["cached"] = True
        return jsonify(out), 200
    result = rainfall_compute(bbox, start, end)
    result["cached"] = False
    cache.set(key, result, ttl=config.CACHE_TTL["rainfall"])
    return jsonify(result), 200


@bp.get("/geocode")
def get_geocode():
    """Place search: agricultural-zone shortcuts + Nominatim boundaries."""
    from .geocode import search
    _check("default")
    q = request.args.get("q", "")
    limit = min(int(request.args.get("limit", 8)), 20)
    result = search(q, limit)
    cache.set(f"geo:{q.lower()}:{limit}", result, ttl=config.CACHE_TTL["geocode"])
    return jsonify(result), 200


@bp.post("/convert-shapefile")
def post_convert_shapefile():
    """Convert an uploaded zipped ESRI Shapefile to GeoJSON."""
    from .uploads import convert_shapefile
    _check("default")
    file = request.files.get("file")
    if file is None:
        raise ValidationError("Upload a zipped shapefile as multipart field 'file'.")
    return jsonify(convert_shapefile(file.read())), 200


@bp.post("/validate-geojson")
def post_validate_geojson():
    """Validate an uploaded GeoJSON and return usable metadata."""
    from .uploads import inspect_geojson
    body = request.get_json(silent=True)
    geojson = body.get("geojson") if isinstance(body, dict) else body
    if geojson is None:
        raise ValidationError("Provide a GeoJSON object.")
    return jsonify(inspect_geojson(geojson)), 200


@bp.post("/zones")
def post_zones():
    """Stress-zone vector polygons for a region+composite (Features 2/12).

    Body: { "geojson": <area>, "start_date"?, "end_date"? }
    Returns a GeoJSON FeatureCollection of per-class MultiPolygons.
    """
    from datetime import datetime as _dt

    from . import demo
    from .geometry import geometry_hash, validate_area
    from .tasks import default_window
    from .zones import build_zones
    _check("default")
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        raise ValidationError("Request body must be JSON.")
    geojson = body.get("geojson") or body.get("geometry") or body.get("area")
    if geojson is None:
        raise ValidationError("Provide an area as 'geojson'.")

    _, end_default = default_window()
    end = end_default
    if body.get("end_date"):
        try:
            end = _dt.strptime(body["end_date"], "%Y-%m-%d").date()
        except ValueError:
            raise ValidationError("end_date must be YYYY-MM-DD.")

    meta = validate_area(geojson)
    key = f"zones:{geometry_hash(geojson)}:{end}"
    cached = cache.get(key)
    if cached:
        return jsonify(cached), 200
    grid = demo.generate(meta["bbox"], meta["polygons"], geometry_hash(geojson), end)
    fc = build_zones(grid.ndvi, grid.bbox)
    fc["properties"] = {"composite_end": end.isoformat(), "source": grid.source}
    cache.set(key, fc, ttl=config.CACHE_TTL["ndvi"])
    return jsonify(fc), 200


@bp.post("/trend")
def post_trend():
    """Region-mean NDVI series for a range: 3m | 6m | 12m | 5y (Feature 4)."""
    from .geometry import geometry_hash, validate_area
    from .trend import compute as trend_compute
    _check("default")
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        raise ValidationError("Request body must be JSON.")
    geojson = body.get("geojson") or body.get("geometry") or body.get("area")
    if geojson is None:
        raise ValidationError("Provide an area as 'geojson'.")
    range_key = body.get("range", "6m")

    meta = validate_area(geojson)
    key = f"trend:{geometry_hash(geojson)}:{range_key}"
    cached = cache.get(key)
    if cached:
        out = dict(cached); out["cached"] = True
        return jsonify(out), 200
    result = trend_compute(meta["bbox"], meta["polygons"], geometry_hash(geojson), range_key)
    result["cached"] = False
    cache.set(key, result, ttl=config.CACHE_TTL["ndvi"])
    return jsonify(result), 200


@bp.post("/report")
def post_report():
    """Generate an AI field report from a compiled analysis payload (Feature 13)."""
    from .report import generate as generate_report
    _check("default")
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        raise ValidationError("Request body must be JSON.")
    return jsonify(generate_report(body)), 200


@bp.post("/register-key")
def post_register_key():
    """Register a free API key (email only) for higher rate limits (Feature 19)."""
    from .apikeys import register
    body = request.get_json(silent=True) or {}
    return jsonify(register(body.get("email", ""))), 200


@bp.get("/openapi.json")
def get_openapi():
    from .openapi import spec
    return jsonify(spec()), 200


@bp.get("/docs")
def get_docs():
    from flask import Response
    from .openapi import DOCS_HTML
    return Response(DOCS_HTML, mimetype="text/html")


@bp.get("/defaults")
def get_defaults():
    """Handy for the frontend: default composite window + server capabilities."""
    start, end = default_window()
    return jsonify({
        "default_window": {"start": start.isoformat(), "end": end.isoformat()},
        "products": list(config.VALID_PRODUCTS),
        "stress_zones": [
            {"name": n, "low": lo, "high": hi, "colour": c}
            for n, lo, hi, c in config.STRESS_ZONES
        ],
        "live_satellite": config.HAS_EARTHDATA and not config.DEMO_MODE_DEFAULT,
        "data_source": "NASA MODIS via AppEEARS" if config.HAS_EARTHDATA else "synthetic (demo)",
    })


@bp.get("/health")
def health():
    """Liveness + lightweight diagnostics (used by the keep-alive cron)."""
    return jsonify({
        "status": "ok",
        "version": __version__,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "mode": "demo" if config.DEMO_MODE_DEFAULT else "live",
        "earthdata_configured": config.HAS_EARTHDATA,
        "cache": cache.stats(),
    })
