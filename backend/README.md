# CropWatch Backend

Flask API serving NASA MODIS NDVI data (via AppEEARS) with server-side statistics.
Deploys free on Render.com. **Runs with zero setup in demo mode** — no NASA
account needed to develop or demo the whole app.

## Endpoints

| Endpoint | Method | Purpose |
|---|---|---|
| `POST /ndvi` | POST | Submit a GeoJSON area → NDVI grid + full statistics |
| `GET /ndvi/status/<task_id>` | GET | Poll a submitted task (progress → result) |
| `POST /historical` | POST | Z-score anomaly map, analogue years, anomaly time series |
| `GET /rainfall` | GET | Precip anomaly bars + NDVI–rainfall correlation |
| `GET /geocode` | GET | Place search: agri-zone shortcuts + Nominatim boundaries |
| `POST /convert-shapefile` | POST | Zipped ESRI Shapefile → GeoJSON (multipart) |
| `POST /validate-geojson` | POST | Validate uploaded GeoJSON, return metadata |
| `POST /report` | POST | AI field report (Groq→Gemini→HuggingFace→template) |
| `POST /register-key` | POST | Free API key (email only) for higher rate limits |
| `GET /openapi.json` · `GET /docs` | GET | OpenAPI 3.0 spec + Swagger UI page |
| `GET /defaults` | GET | Default composite window, products, stress zones, mode |
| `GET /health` | GET | Liveness + cache diagnostics (keep-alive target) |

Rate limits: 10 NDVI req/hr per IP anonymous (100 with a key), 60/hr other
endpoints (1000 with a key). Keys are `Authorization: Bearer <key>`.

- **Phase 1** — NDVI core (`/ndvi`, `/ndvi/status`)
- **Phase 2** — Historical anomaly (`/historical`): pixel-wise z-scores vs a
  per-pixel 5/10/20-year baseline, anomaly distribution, plain-English
  interpretation, the **Analogue Year Finder** (Pearson spatial correlation
  against every year back to 2001 → top 3, each with FAOSTAT yield deviation and
  a growing-season sparkline), and the **anomaly time series** with a fitted
  trend. Cold ~2s in demo, cached ~60ms.
- **Phase 3** — Supporting endpoints: `/rainfall` (CHIRPS-style precip anomaly
  bars + NDVI–rainfall Pearson correlation with the weak-correlation "not
  rain-driven" diagnostic), `/geocode` (agri-zone shortcuts + Nominatim), and
  shapefile/GeoJSON upload conversion (pyshp; optional pyproj reprojection).

### Demo mode (default with no credentials)
If `EARTHDATA_USERNAME`/`EARTHDATA_PASSWORD` are unset, the backend serves a
**synthetic NDVI engine**: deterministic per region+date, spatially coherent
(multi-octave value noise), and calibrated so arid zones read drier than humid
tropics and the growing season greens up and browns down at the right time of
year. Everything is labelled `"source": "demo"`. Set NASA credentials to switch
to live MODIS automatically. Force demo with `?demo=true` or `CROPWATCH_DEMO=true`.

## Run locally
```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python app.py                 # http://localhost:5000  (PORT=5050 to change)
```

## Test
```bash
python -m pytest -q            # 39 tests (Phases 1–5)
```

## Try it
```bash
curl -X POST http://localhost:5000/ndvi -H "Content-Type: application/json" -d '{
  "geojson": {"type":"Polygon","coordinates":[[[8.2,11.6],[8.9,11.6],[8.9,12.3],[8.2,12.3],[8.2,11.6]]]}
}'
```

## Response shape (`POST /ndvi`, complete)
```jsonc
{
  "task_id": "...", "status": "complete", "source": "demo", "cached": false,
  "result": {
    "composite": { "start", "end", "product", "date_label", "age_days" },
    "area": { "bbox", "area_km2", "centroid" },
    "grid": { "rows", "cols", "bbox", "cellsize_deg", "row_order": "north_to_south" },
    "ndvi": [ /* row-major floats, null = no-data */ ],
    "stats": {
      "mean","median","std","min","max","p10","p90",
      "valid_pixels","water_pixels","coverage_pct",
      "zones": { "severe","moderate","mild","healthy","dense_healthy" },
      "stressed_area_pct",
      "severity": { "score", "label", "colour", "partial", "components" }
    }
  }
}
```

### Design notes
- **Compact payload**: the NDVI raster is sent as a flat row-major array + grid
  geotransform, not `{lat,lon,ndvi}` per pixel — ~3× smaller; the frontend
  reconstructs positions from the bbox in one pass.
- **Server-side stats**: mean/median/std, 5-zone classification, and the 0–100
  severity score (Feature 11) are computed once here so every panel, card, and
  export reads identical numbers.
- **Severity `partial: true`** in Phase 1: the historical z-score component
  (30%) arrives with `POST /historical` in Phase 2; until then the two available
  components are renormalised and the score is flagged partial.
- **Task dedupe**: task IDs hash (geometry + window + product), so identical
  requests share one NASA task and one cache entry.
- **Single gunicorn worker, many threads**: the in-memory cache and AppEEARS
  polling threads are in-process and must be shared (see `render.yaml`).

## Architecture
```
app.py                 Flask factory, CORS, error handlers
config.py              env + scientific constants (thresholds, TTLs, MODIS scale)
cropwatch/
  routes.py            HTTP controllers
  tasks.py             async orchestration (demo inline / AppEEARS background thread)
  appeears.py          NASA AppEEARS client (auth, submit, poll, parse)
  demo.py              synthetic NDVI engine (snapshots + multi-year stacks)
  historical.py        z-scores, anomaly series, analogue year finder
  faostat.py           country/crop inference + yield deviations (API + fallback)
  rainfall.py          CHIRPS-style precip anomaly + NDVI-rainfall correlation
  geocode.py           Nominatim + agricultural zone shortcuts
  uploads.py           shapefile->GeoJSON + GeoJSON validation
  report.py            AI field report (3-tier chain + template fallback)
  apikeys.py           SQLite-backed free API-key registration
  ratelimit.py         in-memory sliding-window limiter
  openapi.py           OpenAPI 3.0 spec + Swagger UI page
  grid.py              NDVIGrid model + compact serialisation
  stats.py             statistics + severity score
  geometry.py          GeoJSON validation, area, point-in-polygon
  cache.py             thread-safe LRU + TTL cache
  errors.py            plain-English error types
```
