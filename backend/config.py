"""Central configuration and scientific constants for CropWatch.

Everything that a future maintainer might want to tune — cache TTLs, MODIS
scaling, stress thresholds, region size limits — lives here so it is never
buried inside request handlers.
"""
from __future__ import annotations

import os
from dotenv import load_dotenv

load_dotenv()


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


class Config:
    # --- Runtime -----------------------------------------------------------
    ENV = os.getenv("FLASK_ENV", "development")
    DEBUG = _env_bool("FLASK_DEBUG", ENV != "production")

    # --- NASA Earthdata / AppEEARS ----------------------------------------
    EARTHDATA_USERNAME = os.getenv("EARTHDATA_USERNAME", "")
    EARTHDATA_PASSWORD = os.getenv("EARTHDATA_PASSWORD", "")
    APPEEARS_BASE = os.getenv("APPEEARS_BASE", "https://appeears.earthdatacloud.nasa.gov/api")

    # If no NASA credentials are configured, the backend automatically serves
    # scientifically-plausible synthetic data so the whole app is runnable and
    # demoable end-to-end. A request can also force demo mode with ?demo=true.
    HAS_EARTHDATA = bool(EARTHDATA_USERNAME and EARTHDATA_PASSWORD)
    DEMO_MODE_DEFAULT = _env_bool("CROPWATCH_DEMO", not HAS_EARTHDATA)

    # --- AI report generation (three-tier free fallback chain) ------------
    GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
    GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")
    HF_API_KEY = os.getenv("HF_API_KEY", "")
    HAS_ANY_AI = bool(GROQ_API_KEY or GOOGLE_API_KEY or HF_API_KEY)
    REPORT_LANGUAGES = ("en", "fr", "sw")
    REPORT_AUDIENCES = ("Farmer", "Trader", "NGO/Government", "Researcher")

    # --- API keys / rate limiting -----------------------------------------
    API_KEY_DB = os.getenv("API_KEY_DB", os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "data", "keys.sqlite"))
    RATE_LIMITS = {              # (max_requests, window_seconds)
        "ndvi_anon": (10, 3600),
        "ndvi_key": (100, 3600),
        "default_anon": (60, 3600),
        "default_key": (1000, 3600),
    }

    # --- Cache -------------------------------------------------------------
    CACHE_MAX_BYTES = int(os.getenv("CACHE_MAX_BYTES", 500 * 1024 * 1024))  # 500 MB
    CACHE_TTL = {
        "ndvi": 24 * 3600,       # POST /ndvi
        "historical": 7 * 24 * 3600,
        "rainfall": 6 * 3600,
        "geocode": 24 * 3600,
        "report": 60 * 60,
    }

    # --- Region validation -------------------------------------------------
    # MODIS covers 90N..60S. Reject requests outside that band.
    LAT_MIN, LAT_MAX = -60.0, 90.0
    LON_MIN, LON_MAX = -180.0, 180.0
    MAX_AREA_KM2 = 500_000        # AppEEARS single-task practical ceiling
    MIN_AREA_KM2 = 0.05

    # --- MODIS MOD13Q1 / MYD13Q1 ------------------------------------------
    MODIS_SCALE = 1e-4            # raw int -> NDVI float
    MODIS_VALID_RANGE = (-2000, 10000)
    NDVI_NODATA_BELOW = -0.2      # below this = water/snow/cloud -> transparent
    COMPOSITE_DAYS = 8           # combined Terra+Aqua cadence
    VALID_PRODUCTS = ("MOD13Q1", "MYD13Q1")

    # Native pixel spacing (~250 m). Demo grid is capped in size for payload
    # sanity but respects real-world spacing for small regions.
    NATIVE_RES_DEG = 250 / 111_320.0   # ~0.002246 deg
    MAX_GRID_CELLS = 160               # per side; caps payload at 160x160

    # --- Stress classification (NASA LPDAAC convention) -------------------
    # (name, low_inclusive, high_exclusive, hex_colour)
    STRESS_ZONES = [
        ("severe",        0.00, 0.20, "#8B0000"),
        ("moderate",      0.20, 0.40, "#E8870A"),
        ("mild",          0.40, 0.50, "#F5C842"),
        ("healthy",       0.50, 0.70, "#4CAF50"),
        ("dense_healthy", 0.70, 1.01, "#1A5C38"),
    ]

    # Severity score component weights (Feature 11).
    SEVERITY_WEIGHTS = {"ndvi": 0.35, "stressed_area": 0.35, "anomaly": 0.30}


config = Config()
