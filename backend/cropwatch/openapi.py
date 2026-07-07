"""OpenAPI 3.0 description + a self-contained Swagger UI docs page (Feature 19).

The spec is built as a plain dict (no generator dependency) and served at
``/openapi.json``; ``/docs`` returns an HTML page that loads Swagger UI from a CDN
and points it at that spec. Zero extra Python dependencies.
"""
from __future__ import annotations

from . import __version__


def spec() -> dict:
    area_body = {
        "required": True,
        "content": {"application/json": {"schema": {
            "type": "object",
            "properties": {
                "geojson": {"type": "object", "description": "Feature, FeatureCollection, or Geometry (Polygon/MultiPolygon)"},
                "start_date": {"type": "string", "example": "2026-06-16"},
                "end_date": {"type": "string", "example": "2026-06-23"},
                "product": {"type": "string", "enum": ["MOD13Q1", "MYD13Q1"]},
            },
            "required": ["geojson"],
        }}},
    }
    return {
        "openapi": "3.0.3",
        "info": {
            "title": "CropWatch API",
            "version": __version__,
            "description": ("Satellite-derived NDVI crop-stress monitoring over NASA MODIS. "
                            "Anonymous NDVI requests are limited to 10/hour per IP; register a "
                            "free API key (email only) for 100/hour and pass it as "
                            "`Authorization: Bearer <key>`."),
        },
        "servers": [{"url": "/", "description": "This server"}],
        "components": {"securitySchemes": {"ApiKey": {
            "type": "http", "scheme": "bearer",
            "description": "Free API key from POST /register-key"}}},
        "paths": {
            "/ndvi": {"post": {
                "summary": "Submit an NDVI snapshot for an area",
                "description": "Returns NDVI grid + statistics. Completes inline in demo mode; otherwise poll /ndvi/status/{id}.",
                "security": [{"ApiKey": []}, {}],
                "requestBody": area_body,
                "responses": {"200": {"description": "Complete (demo)"},
                              "202": {"description": "Processing — poll status"},
                              "422": {"description": "Validation error"},
                              "429": {"description": "Rate limit exceeded"}}}},
            "/ndvi/status/{task_id}": {"get": {
                "summary": "Poll a submitted NDVI task",
                "parameters": [{"name": "task_id", "in": "path", "required": True,
                                "schema": {"type": "string"}}],
                "responses": {"200": {"description": "Complete/failed"},
                              "202": {"description": "Still processing"},
                              "404": {"description": "Unknown/expired task"}}}},
            "/historical": {"post": {
                "summary": "Z-score anomaly, analogue years, anomaly time series",
                "requestBody": {"content": {"application/json": {"schema": {"type": "object",
                    "properties": {"geojson": {"type": "object"},
                                   "target_date": {"type": "string"},
                                   "years": {"type": "integer", "enum": [5, 10, 20]}}}}}},
                "responses": {"200": {"description": "OK"}, "422": {"description": "Validation error"}}}},
            "/rainfall": {"get": {
                "summary": "Precipitation anomaly + NDVI–rainfall correlation",
                "parameters": [
                    {"name": "bbox", "in": "query", "required": True,
                     "schema": {"type": "string"}, "example": "8.2,11.6,8.9,12.3"},
                    {"name": "start_date", "in": "query", "schema": {"type": "string"}},
                    {"name": "end_date", "in": "query", "schema": {"type": "string"}}],
                "responses": {"200": {"description": "OK"}}}},
            "/geocode": {"get": {
                "summary": "Place search: agri-zone shortcuts + Nominatim",
                "parameters": [{"name": "q", "in": "query", "required": True,
                                "schema": {"type": "string"}}],
                "responses": {"200": {"description": "OK"}}}},
            "/convert-shapefile": {"post": {
                "summary": "Zipped ESRI Shapefile → GeoJSON",
                "requestBody": {"content": {"multipart/form-data": {"schema": {"type": "object",
                    "properties": {"file": {"type": "string", "format": "binary"}}}}}},
                "responses": {"200": {"description": "OK"}, "422": {"description": "Bad shapefile"}}}},
            "/validate-geojson": {"post": {
                "summary": "Validate uploaded GeoJSON",
                "responses": {"200": {"description": "OK"}}}},
            "/report": {"post": {
                "summary": "AI field report (Groq→Gemini→HuggingFace→template)",
                "responses": {"200": {"description": "OK"}}}},
            "/register-key": {"post": {
                "summary": "Register a free API key (email only)",
                "requestBody": {"content": {"application/json": {"schema": {"type": "object",
                    "properties": {"email": {"type": "string"}}, "required": ["email"]}}}},
                "responses": {"200": {"description": "Key issued"}, "422": {"description": "Invalid email"}}}},
            "/defaults": {"get": {"summary": "Server defaults & capabilities",
                                  "responses": {"200": {"description": "OK"}}}},
            "/health": {"get": {"summary": "Liveness + cache diagnostics",
                                "responses": {"200": {"description": "OK"}}}},
        },
    }


DOCS_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>CropWatch API — Docs</title>
  <link rel="stylesheet" href="https://unpkg.com/swagger-ui-dist@5/swagger-ui.css"/>
  <style>body{margin:0}.topbar{display:none}</style>
</head>
<body>
  <div id="swagger-ui"></div>
  <script src="https://unpkg.com/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
  <script>
    window.ui = SwaggerUIBundle({
      url: "/openapi.json",
      dom_id: "#swagger-ui",
      presets: [SwaggerUIBundle.presets.apis],
      layout: "BaseLayout"
    });
  </script>
</body>
</html>"""
