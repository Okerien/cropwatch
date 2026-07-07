# CropWatch

**Satellite crop stress & vegetation health monitor** — free NASA MODIS NDVI data
behind an interface anyone can use. Flask backend (Render) + React frontend
(Vercel). Total monthly cost: **$0**.

![status](https://img.shields.io/badge/backend-42%20tests%20passing-brightgreen)

## What it does

- **Snapshot** — pixel-level NDVI heatmap for any area on Earth (draw, search,
  coordinates, GeoJSON or Shapefile upload), with a 0–100 crop-stress severity
  score, zone statistics, and an animated 8-day time-lapse slider.
- **Trend** — NDVI over 3 months to 5 years with stress thresholds, rainfall
  anomaly bars (CHIRPS), the rainfall–NDVI correlation diagnostic, and
  multi-region comparison from the watchlist.
- **Historical** — z-score anomaly map vs a 5/10/20-year baseline, plain-English
  interpretation, and the Analogue Year Finder with FAOSTAT yield outcomes.
- **Watchlist** — saved regions with live severity dots, alert thresholds
  (in-browser banner), notes and tags. Exports: PNG / one-page PDF field report /
  CSV / GeoJSON. AI field reports (Groq → Gemini → template fallback) in
  English, French, and Swahili.

## Run locally (zero setup)

```bash
# backend — runs in demo mode with no credentials at all
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
PORT=5050 python app.py

# frontend
cd ../frontend
npm install
npm run dev          # http://localhost:5173 (proxies /api → :5050)
```

With no NASA credentials the backend serves a **synthetic-but-plausible demo
engine** (deterministic, regionally and seasonally calibrated, labelled
`source: "demo"` everywhere). Add credentials to go live:

```bash
# backend/.env
EARTHDATA_USERNAME=...        # free at urs.earthdata.nasa.gov
EARTHDATA_PASSWORD=...
GROQ_API_KEY=...              # optional — live AI field reports
GOOGLE_API_KEY=...            # optional — Gemini fallback tier
```

## Deploy (free tiers)

1. **Render** (backend): new Web Service → root `backend/` →
   `pip install -r requirements.txt` → `gunicorn app:app --workers 1 --threads 8`.
   `render.yaml` is included. Add the env vars above.
2. **Vercel** (frontend): import repo → root `frontend/`. `vercel.json` proxies
   `/api/*` to the Render URL — update the hostname if yours differs.
3. **Keep-alive**: point a free cron (cron-job.org) at `GET /health` every 10
   minutes so the Render free tier never cold-starts.

## API

Interactive docs at `/docs` on the backend (OpenAPI 3.0). Anonymous NDVI
requests: 10/hour. Free API key (email only) via `POST /register-key` raises
that to 100/hour — pass it as `Authorization: Bearer <key>`.

## Data sources

NASA MODIS MOD13Q1/MYD13Q1 (250 m, 8-day) · CHIRPS rainfall · FAOSTAT yields ·
ESA WorldCover · Nominatim/OSM geocoding. Full provenance, limitations, and
citations are in the in-app Data Provenance panel.
