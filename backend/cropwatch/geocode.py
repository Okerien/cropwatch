"""Place search + boundary retrieval (spec §3.2).

Two sources, shortcuts first:
1. **Agricultural zone shortcuts** — named farming regions that are not admin
   boundaries but are the vocabulary of crop monitoring ("Nigerian Middle Belt",
   "US Corn Belt", "South African Highveld"). Served as static polygons, instant
   and offline.
2. **Nominatim** (OpenStreetMap) — free geocoder, no key, returns the admin
   boundary polygon. Called with a short timeout and a required User-Agent;
   failures degrade to shortcut-only results rather than erroring.
"""
from __future__ import annotations

import requests

from .errors import ValidationError

_NOMINATIM = "https://nominatim.openstreetmap.org/search"
_HEADERS = {"User-Agent": "CropWatch/0.1 (satellite crop monitor; contact via app)"}


def _rect(min_lon, min_lat, max_lon, max_lat) -> dict:
    return {"type": "Polygon", "coordinates": [[
        [min_lon, min_lat], [max_lon, min_lat], [max_lon, max_lat],
        [min_lon, max_lat], [min_lon, min_lat]]]}


# name -> (geometry, country). Curated approximations of well-known farming zones.
AGRI_ZONES: dict[str, dict] = {
    "Nigerian Middle Belt": {"geometry": _rect(3.5, 7.0, 11.0, 10.5), "country": "Nigeria"},
    "Kano State farming areas": {"geometry": _rect(7.7, 10.5, 9.5, 12.6), "country": "Nigeria"},
    "Benue Valley": {"geometry": _rect(7.8, 6.9, 10.2, 8.4), "country": "Nigeria"},
    "Ghanaian Cocoa Belt": {"geometry": _rect(-3.0, 5.5, 0.0, 7.5), "country": "Ghana"},
    "Ivorian Centre-West": {"geometry": _rect(-7.5, 5.8, -5.0, 7.6), "country": "Côte d'Ivoire"},
    "Ethiopian Highlands": {"geometry": _rect(36.5, 7.0, 40.5, 12.5), "country": "Ethiopia"},
    "Rift Valley (Kenya)": {"geometry": _rect(35.5, -1.0, 36.6, 1.5), "country": "Kenya"},
    "Kenyan Grain Belt": {"geometry": _rect(34.8, -0.8, 36.2, 1.2), "country": "Kenya"},
    "Tanzanian Southern Highlands": {"geometry": _rect(33.0, -9.5, 36.0, -7.5), "country": "Tanzania"},
    "South African Highveld": {"geometry": _rect(25.5, -28.5, 30.5, -25.5), "country": "South Africa"},
    "Zambian Copperbelt farming areas": {"geometry": _rect(27.0, -13.5, 29.5, -12.0), "country": "Zambia"},
    "Zimbabwe Mashonaland": {"geometry": _rect(29.5, -18.5, 33.0, -16.0), "country": "Zimbabwe"},
    "US Corn Belt": {"geometry": _rect(-98.0, 38.5, -82.0, 45.0), "country": "United States"},
    "US Great Plains Wheat Region": {"geometry": _rect(-102.0, 33.0, -96.0, 43.0), "country": "United States"},
    "California Central Valley": {"geometry": _rect(-122.0, 35.0, -118.5, 40.0), "country": "United States"},
    "Punjab (India)": {"geometry": _rect(73.9, 29.5, 76.9, 32.5), "country": "India"},
    "Punjab (Pakistan)": {"geometry": _rect(71.0, 29.0, 75.4, 33.5), "country": "Pakistan"},
    "Ganges Plain": {"geometry": _rect(77.0, 24.5, 88.0, 30.0), "country": "India"},
    "Deccan Plateau": {"geometry": _rect(74.0, 15.0, 80.0, 20.0), "country": "India"},
}


def _match_shortcuts(query: str) -> list[dict]:
    q = query.strip().lower()
    out = []
    for name, meta in AGRI_ZONES.items():
        if q in name.lower():
            out.append({
                "name": name, "display_name": f"{name} · {meta['country']}",
                "type": "agri_zone", "country": meta["country"],
                "admin_level": "agricultural zone", "geometry": meta["geometry"],
                "source": "shortcut",
            })
    return out


def _nominatim(query: str, limit: int) -> list[dict]:
    try:
        resp = requests.get(_NOMINATIM, params={
            "q": query, "format": "jsonv2", "polygon_geojson": 1,
            "addressdetails": 1, "limit": limit,
        }, headers=_HEADERS, timeout=6)
        resp.raise_for_status()
        results = resp.json()
    except (requests.RequestException, ValueError):
        return []

    out = []
    for r in results:
        geom = r.get("geojson")
        if geom and geom.get("type") not in {"Polygon", "MultiPolygon"}:
            geom = None  # a point/line boundary isn't usable as an area
        bb = r.get("boundingbox")
        out.append({
            "name": r.get("name") or r.get("display_name", "").split(",")[0],
            "display_name": r.get("display_name"),
            "type": "place",
            "country": (r.get("address") or {}).get("country"),
            "admin_level": r.get("addresstype") or r.get("type"),
            "bbox": [float(bb[2]), float(bb[0]), float(bb[3]), float(bb[1])] if bb else None,
            "geometry": geom,
            "source": "nominatim",
        })
    return out


def search(query: str, limit: int = 8) -> dict:
    if not query or len(query.strip()) < 2:
        raise ValidationError("Search query must be at least 2 characters.")
    shortcuts = _match_shortcuts(query)
    remaining = max(0, limit - len(shortcuts))
    places = _nominatim(query, remaining) if remaining else []
    return {"query": query, "suggestions": (shortcuts + places)[:limit],
            "shortcut_count": len(shortcuts)}
