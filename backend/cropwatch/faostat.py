"""FAOSTAT crop-yield context for the Analogue Year Finder.

Two responsibilities:
1. Infer a country + a plausible dominant crop from a region's centroid (until
   Phase 8's ESA WorldCover layer provides a data-driven crop type).
2. Return per-year yield *deviations from the long-term average* for that
   country+crop.

The real FAOSTAT API (free, no key) is attempted first with a short timeout;
if it is slow or offline, the caller falls back to deriving a coherent yield
signal from the region's own NDVI anomaly (bad vegetation year → low yield),
clearly labelled as modelled rather than reported.
"""
from __future__ import annotations

import requests

FAOSTAT_BASE = "https://faostatservices.fao.org/api/v1/en/data/QCL"
_YIELD_ELEMENT = "5419"  # hg/ha

# Rough country boxes for the spec's target regions → (country, FAO area code,
# default crop label, FAO item code). Coarse on purpose; refined by WorldCover later.
_COUNTRY_BOXES = [
    # (min_lon, min_lat, max_lon, max_lat, country, area_code, crop, item_code)
    (2.7, 4.0, 14.7, 13.9, "Nigeria", "159", "Maize", "56"),
    (-3.3, 4.7, 1.2, 11.2, "Ghana", "81", "Cocoa, beans", "661"),
    (-8.6, 4.3, -2.5, 10.7, "Côte d'Ivoire", "107", "Cocoa, beans", "661"),
    (33.9, -4.7, 41.9, 5.0, "Kenya", "114", "Maize", "56"),
    (33.0, 3.4, 47.9, 14.9, "Ethiopia", "238", "Maize", "56"),
    (29.3, -11.7, 40.4, -1.0, "Tanzania", "215", "Maize", "56"),
    (16.4, -34.8, 32.9, -22.1, "South Africa", "202", "Maize", "56"),
    (25.2, -22.4, 33.1, -15.6, "Zimbabwe", "181", "Maize", "56"),
    (22.0, -18.1, 33.7, -8.2, "Zambia", "251", "Maize", "56"),
    (-104.1, 36.0, -80.5, 49.4, "United States of America", "231", "Maize", "56"),
    (68.1, 23.6, 89.0, 35.5, "India", "100", "Wheat", "15"),
]

# Curated one-line notes for notable agricultural years (spec Feature 7).
NOTABLE_EVENTS = {
    ("Nigeria", 2012): "Severe flooding along the Niger–Benue displaced farming across the Middle Belt.",
    ("Nigeria", 2015): "Delayed and erratic rains cut cereal output in the north.",
    ("Kenya", 2011): "Horn of Africa drought — one of the worst food-security crises on record.",
    ("Kenya", 2017): "Prolonged drought triggered a national disaster declaration.",
    ("Ethiopia", 2015): "Strong El Niño drove widespread drought and crop failure.",
    ("South Africa", 2016): "Worst drought since 1904 slashed the maize harvest.",
    ("Zimbabwe", 2019): "El Niño drought left much of Mashonaland in deficit.",
    ("Côte d'Ivoire", 2016): "Harmattan-driven dryness cut cocoa output ~11% below forecast.",
    ("United States of America", 2012): "Historic Corn Belt drought — the most severe since the 1930s.",
}


def infer_context(centroid: list[float]) -> dict:
    """Best-guess country + dominant crop for a region centroid."""
    lon, lat = centroid
    for min_lon, min_lat, max_lon, max_lat, country, code, crop, item in _COUNTRY_BOXES:
        if min_lon <= lon <= max_lon and min_lat <= lat <= max_lat:
            return {"country": country, "area_code": code,
                    "crop": crop, "item_code": item, "matched": True}
    return {"country": None, "area_code": None, "crop": "Cropland",
            "item_code": None, "matched": False}


def fetch_yield_deviations(area_code: str, item_code: str,
                           years: list[int]) -> dict[int, float]:
    """Return {year: pct deviation from long-term mean} from FAOSTAT, or {} on failure."""
    if not area_code or not item_code:
        return {}
    try:
        resp = requests.get(FAOSTAT_BASE, params={
            "area": area_code, "item": item_code, "element": _YIELD_ELEMENT,
            "year": ",".join(str(y) for y in years), "output_type": "objects",
        }, timeout=6)
        resp.raise_for_status()
        rows = resp.json().get("data", [])
    except (requests.RequestException, ValueError):
        return {}

    series = {}
    for row in rows:
        try:
            series[int(row["Year"])] = float(row["Value"])
        except (KeyError, ValueError, TypeError):
            continue
    if len(series) < 3:
        return {}
    mean = sum(series.values()) / len(series)
    if mean == 0:
        return {}
    return {y: round(100 * (v - mean) / mean, 1) for y, v in series.items()}


def notable_event(country: str | None, year: int) -> str | None:
    return NOTABLE_EVENTS.get((country, year)) if country else None
