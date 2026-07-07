"""Phase 1 regression tests — geometry, stats, demo engine, and the API.

Run:  .venv/bin/python -m pytest -q   (from backend/)
"""
from datetime import date

import numpy as np
import pytest

from cropwatch import demo
from cropwatch.errors import ValidationError
from cropwatch.geometry import area_km2, geometry_hash, validate_area
from cropwatch.stats import severity_score, summarize

KANO = {"type": "Polygon", "coordinates": [[[8.2, 11.6], [8.9, 11.6],
                                            [8.9, 12.3], [8.2, 12.3], [8.2, 11.6]]]}


# --- geometry -------------------------------------------------------------
def test_validate_area_ok():
    meta = validate_area(KANO)
    assert meta["area_km2"] > 0
    assert len(meta["bbox"]) == 4
    assert meta["bbox"][0] < meta["bbox"][2]


def test_reject_point():
    with pytest.raises(ValidationError):
        validate_area({"type": "Point", "coordinates": [8, 11]})


def test_reject_out_of_coverage():
    poly = {"type": "Polygon", "coordinates": [[[8, -75], [9, -75], [9, -74],
                                               [8, -74], [8, -75]]]}
    with pytest.raises(ValidationError):
        validate_area(poly)


def test_reject_too_large():
    poly = {"type": "Polygon", "coordinates": [[[-40, -10], [40, -10], [40, 40],
                                               [-40, 40], [-40, -10]]]}
    with pytest.raises(ValidationError):
        validate_area(poly)


def test_area_is_reasonable():
    # ~0.7deg x 0.7deg near 12N is a few thousand km^2, not millions.
    assert 3000 < area_km2(validate_area(KANO)["polygons"]) < 9000


# --- stats + severity -----------------------------------------------------
def test_zones_and_severity_partial():
    ndvi = np.full((10, 10), 0.15)  # all severe
    s = summarize(ndvi)
    assert s["zones"]["severe"]["pct"] == 100.0
    assert s["severity"]["partial"] is True
    assert s["severity"]["score"] < 25


def test_severity_monotonic():
    low = severity_score(0.2, 80.0)["score"]
    high = severity_score(0.8, 5.0)["score"]
    assert high > low


def test_severity_uses_anomaly_when_present():
    with_z = severity_score(0.5, 30.0, mean_z=-2.5)
    assert with_z["partial"] is False
    assert with_z["components"]["anomaly"] is not None


def test_nodata_masked():
    ndvi = np.array([[0.6, -0.9], [np.nan, 0.5]])  # -0.9 and nan are no-data
    s = summarize(ndvi)
    assert s["valid_pixels"] == 2
    assert s["water_pixels"] == 2


# --- demo engine ----------------------------------------------------------
def _demo_mean(poly, when):
    meta = validate_area(poly)
    grid = demo.generate(meta["bbox"], meta["polygons"], geometry_hash(poly), when)
    return summarize(grid.ndvi)["mean"]


def test_demo_deterministic():
    a = _demo_mean(KANO, date(2026, 6, 23))
    b = _demo_mean(KANO, date(2026, 6, 23))
    assert a == b


def test_demo_regional_gradient():
    sahara = {"type": "Polygon", "coordinates": [[[6, 23], [7, 23], [7, 24], [6, 24], [6, 23]]]}
    congo = {"type": "Polygon", "coordinates": [[[20, -0.5], [21, -0.5], [21, 0.5], [20, 0.5], [20, -0.5]]]}
    assert _demo_mean(sahara, date(2026, 6, 23)) < _demo_mean(congo, date(2026, 6, 23))


def test_demo_seasonality_north():
    corn = {"type": "Polygon", "coordinates": [[[-94, 40.5], [-93, 40.5], [-93, 41.5], [-94, 41.5], [-94, 40.5]]]}
    assert _demo_mean(corn, date(2026, 1, 15)) < _demo_mean(corn, date(2026, 7, 15))


def test_demo_grid_shape_matches_payload():
    meta = validate_area(KANO)
    grid = demo.generate(meta["bbox"], meta["polygons"], geometry_hash(KANO), date(2026, 6, 23))
    payload = grid.to_payload()
    assert len(payload["ndvi"]) == payload["grid"]["rows"] * payload["grid"]["cols"]


# --- API smoke ------------------------------------------------------------
@pytest.fixture()
def client():
    from app import app
    app.testing = True
    return app.test_client()


@pytest.fixture(autouse=True)
def _reset_rate_limit(tmp_path):
    """Clear the limiter, pin real limits, isolate the API-key DB per test.

    Also blanks any real AI keys from .env so report tests exercise the
    deterministic template path — the suite must never depend on network.
    """
    from config import config as _cfg
    from cropwatch import ratelimit
    ratelimit._hits.clear()
    saved_mult = ratelimit.DEMO_MULTIPLIER
    saved_ai = (_cfg.GROQ_API_KEY, _cfg.GOOGLE_API_KEY, _cfg.HF_API_KEY, _cfg.HAS_ANY_AI)
    ratelimit.DEMO_MULTIPLIER = 1        # tests assert the documented limits
    _cfg.GROQ_API_KEY = _cfg.GOOGLE_API_KEY = _cfg.HF_API_KEY = ""
    _cfg.HAS_ANY_AI = False
    _cfg.API_KEY_DB = str(tmp_path / "keys.sqlite")
    yield
    ratelimit.DEMO_MULTIPLIER = saved_mult
    (_cfg.GROQ_API_KEY, _cfg.GOOGLE_API_KEY, _cfg.HF_API_KEY, _cfg.HAS_ANY_AI) = saved_ai
    ratelimit._hits.clear()


def test_health(client):
    assert client.get("/health").get_json()["status"] == "ok"


def test_post_ndvi_completes_in_demo(client):
    resp = client.post("/ndvi", json={"geojson": KANO})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["status"] == "complete"
    assert body["source"] == "demo"
    assert body["result"]["stats"]["severity"]["score"] >= 0


def test_status_roundtrip(client):
    tid = client.post("/ndvi", json={"geojson": KANO}).get_json()["task_id"]
    st = client.get(f"/ndvi/status/{tid}")
    assert st.status_code == 200
    assert st.get_json()["status"] == "complete"


def test_dedupe_same_request_cached(client):
    client.post("/ndvi", json={"geojson": KANO})
    second = client.post("/ndvi", json={"geojson": KANO}).get_json()
    assert second["cached"] is True


# --- Phase 2: historical anomaly ------------------------------------------
def test_historical_shape(client):
    r = client.post("/historical", json={"geojson": KANO, "years": 20})
    assert r.status_code == 200
    body = r.get_json()
    assert body["grid"]["rows"] * body["grid"]["cols"] == len(body["zscore"])
    assert -5 < body["mean_z"] < 5
    assert body["severity"]["partial"] is False  # anomaly component now present
    assert len(body["analogue_years"]) == 3
    assert body["baseline_range"][0] < body["baseline_range"][1]


def test_historical_rejects_bad_years(client):
    r = client.post("/historical", json={"geojson": KANO, "years": 7})
    assert r.status_code == 422


def test_historical_analogues_sorted_by_correlation(client):
    a = client.post("/historical", json={"geojson": KANO, "years": 10}).get_json()
    corrs = [x["correlation"] for x in a["analogue_years"]]
    assert corrs == sorted(corrs, reverse=True)


def test_historical_cached_second_call(client):
    client.post("/historical", json={"geojson": KANO, "years": 20})
    second = client.post("/historical", json={"geojson": KANO, "years": 20}).get_json()
    assert second["cached"] is True


def test_historical_anomaly_series(client):
    a = client.post("/historical", json={"geojson": KANO, "years": 20}).get_json()
    ts = a["anomaly_time_series"]
    assert len(ts["points"]) == 12
    assert "trend_summary" in ts


def test_zscore_engine_direct():
    from datetime import date as _date

    from cropwatch import historical
    meta = validate_area(KANO)
    out = historical.compute(meta["bbox"], meta["polygons"],
                             geometry_hash(KANO), _date(2026, 6, 23), 20, meta)
    # Baseline uses 20 prior years; z field aligns with grid.
    assert out["baseline_years_used"] >= 3
    zv = [v for v in out["zscore"] if v is not None]
    assert len(zv) > 100


# --- Phase 3: rainfall, geocode, uploads ----------------------------------
def test_rainfall_shape_and_correlation(client):
    r = client.get("/rainfall?bbox=8.2,11.6,8.9,12.3&start_date=2025-06-01&end_date=2026-06-23")
    assert r.status_code == 200
    body = r.get_json()
    assert body["aggregation"] == "monthly"
    assert len(body["bars"]) > 6
    assert all("anomaly_pct" in b for b in body["bars"])
    assert -1.0 <= (body["correlation"]["coefficient"] or 0) <= 1.0


def test_rainfall_bad_bbox(client):
    assert client.get("/rainfall?bbox=1,2,3").status_code == 422


def test_geocode_shortcut_offline(client):
    body = client.get("/geocode?q=highveld").get_json()
    assert body["shortcut_count"] >= 1
    top = body["suggestions"][0]
    assert top["type"] == "agri_zone"
    assert top["geometry"]["type"] == "Polygon"


def test_geocode_too_short(client):
    assert client.get("/geocode?q=a").status_code == 422


def test_validate_geojson_featurecollection(client):
    fc = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"name": "A"},
         "geometry": {"type": "Polygon", "coordinates": [[[8.2, 11.6], [8.5, 11.6],
                     [8.5, 11.9], [8.2, 11.9], [8.2, 11.6]]]}}]}
    body = client.post("/validate-geojson", json={"geojson": fc}).get_json()
    assert body["valid"] is True
    assert body["features"][0]["name"] == "A"


def test_convert_shapefile_roundtrip(client):
    import io
    import zipfile

    import shapefile
    mem = {ext: io.BytesIO() for ext in ("shp", "dbf", "shx")}
    w = shapefile.Writer(shp=mem["shp"], dbf=mem["dbf"], shx=mem["shx"])
    w.field("NAME", "C")
    w.poly([[[8.2, 11.6], [8.5, 11.6], [8.5, 11.9], [8.2, 11.9], [8.2, 11.6]]])
    w.record("Plot 1")
    w.close()
    z = io.BytesIO()
    with zipfile.ZipFile(z, "w") as zf:
        for ext, b in mem.items():
            zf.writestr(f"f.{ext}", b.getvalue())
    data = {"file": (io.BytesIO(z.getvalue()), "f.zip")}
    r = client.post("/convert-shapefile", data=data, content_type="multipart/form-data")
    assert r.status_code == 200
    body = r.get_json()
    assert body["feature_count"] == 1
    assert body["attribute_fields"] == ["NAME"]


def test_convert_shapefile_missing_shp(client):
    import io
    import zipfile
    z = io.BytesIO()
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("x.txt", "hi")
    data = {"file": (io.BytesIO(z.getvalue()), "bad.zip")}
    r = client.post("/convert-shapefile", data=data, content_type="multipart/form-data")
    assert r.status_code == 422


# --- Trend series ----------------------------------------------------------
def test_trend_6m(client):
    body = client.post("/trend", json={"geojson": KANO, "range": "6m"}).get_json()
    assert body["range"] == "6m"
    assert 20 <= len(body["points"]) <= 25          # ~183/8 composites
    p = body["points"][0]
    assert 0 <= p["mean_ndvi"] <= 1 and "classification" in p
    assert body["summary"]["latest"] is not None


def test_trend_bad_range(client):
    assert client.post("/trend", json={"geojson": KANO, "range": "2w"}).status_code == 422


def test_trend_deterministic_and_cached(client):
    a = client.post("/trend", json={"geojson": KANO, "range": "3m"}).get_json()
    b = client.post("/trend", json={"geojson": KANO, "range": "3m"}).get_json()
    assert a["points"] == b["points"]
    assert b["cached"] is True


# --- AppEEARS helpers (live path; network parts not unit-tested) -----------
def test_appeears_doy_filename_parse():
    from datetime import date as _date

    from cropwatch.appeears import _doy_date
    # DOY 161 of 2026 = 10 June 2026 (2026 is not a leap year).
    assert _doy_date("MOD13Q1.061__250m_16_days_NDVI_doy2026161_aid0001.tif") == _date(2026, 6, 10)
    assert _doy_date("no-doy-here.tif") is None


def test_appeears_widens_window(monkeypatch):
    from datetime import date as _date

    from cropwatch import appeears
    captured = {}

    class _Resp:
        def raise_for_status(self): pass
        def json(self): return {"task_id": "t123"}

    monkeypatch.setattr(appeears, "_auth_headers", lambda: {})
    def _fake_post(url, json=None, **kw):
        captured["dates"] = json["params"]["dates"][0]
        return _Resp()
    monkeypatch.setattr(appeears.requests, "post", _fake_post)

    # An 8-day request must be widened to >= LIVE_WINDOW_DAYS so a 16-day
    # composite is guaranteed to fall inside.
    appeears.submit_task({}, _date(2026, 6, 20), _date(2026, 6, 27), "MOD13Q1")
    start = captured["dates"]["startDate"]  # MM-DD-YYYY
    assert start == "05-26-2026"            # 2026-06-27 minus 32 days


# --- Stress-zone polygons ---------------------------------------------------
def test_zones_geojson(client):
    body = client.post("/zones", json={"geojson": KANO}).get_json()
    assert body["type"] == "FeatureCollection"
    assert len(body["features"]) >= 1
    f = body["features"][0]
    assert f["geometry"]["type"] == "MultiPolygon"
    props = f["properties"]
    assert props["stress_class"] in {"severe", "moderate", "mild", "healthy", "dense_healthy"}
    assert props["area_km2"] > 0 and props["pixel_count"] > 0


def test_zones_areas_sum_to_region(client):
    body = client.post("/zones", json={"geojson": KANO}).get_json()
    total = sum(f["properties"]["area_km2"] for f in body["features"])
    # Kano test rect is ~5,900 km²; pixel-grid total should be within 10%.
    assert 5000 < total < 6800


def test_zone_rect_decomposition_exact():
    import numpy as np

    from cropwatch.zones import _class_index, _runs_to_rects
    ndvi = np.array([[0.1, 0.1, 0.6], [0.1, 0.1, 0.6], [np.nan, 0.6, 0.6]])
    idx = _class_index(ndvi)
    rects = _runs_to_rects(idx)
    # severe (class 0): one 2x2 rectangle; pixels covered must equal grid truth.
    sev_px = sum((r1 - r0) * (c1 - c0) for r0, r1, c0, c1 in rects.get(0, []))
    assert sev_px == 4
    healthy_px = sum((r1 - r0) * (c1 - c0) for r0, r1, c0, c1 in rects.get(3, []))
    assert healthy_px == 4   # column of two + bottom run of two


# --- Phase 4: AI report (template fallback) -------------------------------
REPORT_PAYLOAD = {
    "region_name": "Kano North", "country": "Nigeria", "date_label": "16–23 Jun 2026",
    "mean_ndvi": 0.33, "severity": {"score": 30, "label": "Significant stress"},
    "mean_z": -1.9, "rainfall_anomaly_pct": 41,
    "analogue_years": [{"year": 2012, "yield_deviation_pct": -28},
                       {"year": 2019, "yield_deviation_pct": -22}],
    "audience": "Farmer", "language": "en",
}


def test_report_template_two_paragraphs(client):
    body = client.post("/report", json=REPORT_PAYLOAD).get_json()
    assert body["source"] == "template"          # no AI keys in test env
    assert len(body["paragraphs"]) == 2
    assert "Kano North" in body["report"]
    assert body["editable"] is True


def test_report_language_and_audience_validation(client):
    payload = dict(REPORT_PAYLOAD, language="xx", audience="Nobody")
    body = client.post("/report", json=payload).get_json()
    assert body["language"] == "en"              # invalid falls back
    assert body["audience"] == "Farmer"


def test_report_french(client):
    body = client.post("/report", json=dict(REPORT_PAYLOAD, language="fr")).get_json()
    assert body["language"] == "fr"
    assert len(body["paragraphs"]) == 2


# --- Phase 5: keys, rate limiting, docs -----------------------------------
def test_register_key_and_validate(client):
    body = client.post("/register-key", json={"email": "musa@example.com"}).get_json()
    assert body["api_key"].startswith("cw_")
    from cropwatch import apikeys
    assert apikeys.is_valid(body["api_key"]) is True
    assert apikeys.is_valid("cw_nope") is False


def test_register_key_bad_email(client):
    assert client.post("/register-key", json={"email": "notanemail"}).status_code == 422


def test_rate_limit_ndvi_anonymous(client):
    # 10/hr anon NDVI: 10 succeed, 11th is 429.
    codes = [client.post("/ndvi", json={"geojson": KANO}).status_code for _ in range(11)]
    assert codes[:10] == [200] * 10
    assert codes[10] == 429


def test_rate_limit_headers_present(client):
    r = client.post("/ndvi", json={"geojson": KANO})
    assert "X-RateLimit-Limit" in r.headers
    assert int(r.headers["X-RateLimit-Remaining"]) >= 0


def test_openapi_and_docs(client):
    spec = client.get("/openapi.json").get_json()
    assert spec["openapi"].startswith("3.")
    assert "/ndvi" in spec["paths"]
    docs = client.get("/docs")
    assert docs.status_code == 200
    assert b"swagger" in docs.data.lower()


def test_api_key_raises_ndvi_limit(client):
    key = client.post("/register-key", json={"email": "trader@example.com"}).get_json()["api_key"]
    headers = {"Authorization": f"Bearer {key}"}
    # 11 requests that would 429 anonymously should all pass with a key (limit 100).
    codes = [client.post("/ndvi", json={"geojson": KANO}, headers=headers).status_code
             for _ in range(11)]
    assert all(c == 200 for c in codes)
