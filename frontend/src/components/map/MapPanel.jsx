import { useMemo, useEffect, useState, useCallback } from "react";
import { MapContainer, TileLayer, ImageOverlay, GeoJSON, useMap, useMapEvents } from "react-leaflet";
import { useApp } from "../../state/AppContext";
import { gridToImage, sampleGrid } from "../../lib/heatmap";
import { classifyNDVI } from "../../lib/ndviColor";
import { Legend } from "./Legend";
import { InspectPopup } from "./InspectPopup";
import { TimeSlider } from "./TimeSlider";
import { DrawLayer } from "./DrawLayer";
import { DrawToolbar } from "./DrawToolbar";
import "./map.css";

const BASEMAPS = {
  dark: {
    url: "https://{s}.basemaps.cartocdn.com/dark_nolabels/{z}/{x}/{y}{r}.png",
    attr: "&copy; OpenStreetMap &copy; CARTO",
  },
  satellite: {
    url: "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    attr: "Esri World Imagery",
  },
};

function FitToRegion({ bounds }) {
  const map = useMap();
  useEffect(() => {
    if (bounds) map.fitBounds(bounds, { padding: [40, 40], animate: true });
  }, [bounds, map]);
  return null;
}

function ClickInspect({ grid, values }) {
  const { setInspect } = useApp();
  useMapEvents({
    click(e) {
      if (!grid) return;
      const v = sampleGrid(grid, values, e.latlng.lat, e.latlng.lng);
      if (v == null) { setInspect(null); return; }
      setInspect({
        lat: e.latlng.lat, lon: e.latlng.lng, ndvi: v, zone: classifyNDVI(v),
      });
    },
  });
  return null;
}

export function MapPanel({ basemap = "dark" }) {
  const { region, snapshot, historical, view, palette, inspect, loadHistorical, mode } = useApp();
  const [frame, setFrame] = useState(null);   // time-slider override
  const onFrame = useCallback((f) => setFrame(f), []);
  const result = frame || snapshot.result;
  const anomaly = view === "anomaly";

  // A new region invalidates any scrubbed frame.
  useEffect(() => { setFrame(null); }, [region]);

  // Anomaly view needs the /historical z-score grid — fetch on first toggle.
  useEffect(() => {
    if (anomaly && region?.geojson && historical.status === "idle") {
      loadHistorical(region.geojson);
    }
  }, [anomaly, region, historical.status, loadHistorical]);

  const heat = useMemo(() => {
    if (anomaly) {
      const h = historical.result;
      if (!h?.grid || !h?.zscore) return null;
      return gridToImage(h.grid, h.zscore, { mode: "anomaly" });
    }
    if (!result?.grid || !result?.ndvi) return null;
    return gridToImage(result.grid, result.ndvi, {
      mode: "absolute", cvd: palette === "cvd",
    });
  }, [anomaly, historical.result, result, palette]);

  const regionBounds = useMemo(() => {
    if (!result?.area?.bbox) return null;
    const [w, s, e, n] = result.area.bbox;
    return [[s, w], [n, e]];
  }, [result]);

  const base = BASEMAPS[basemap] || BASEMAPS.dark;

  return (
    <div className="map-wrap">
      <MapContainer
        center={[9, 8]} zoom={5} zoomControl={false}
        preferCanvas attributionControl
        className="leaflet-root"
      >
        <TileLayer url={base.url} attribution={base.attr} />

        {heat && (
          <ImageOverlay
            url={heat.url} bounds={heat.bounds} opacity={0.82}
            className="ndvi-overlay" zIndex={300}
          />
        )}

        {region?.geojson && (
          <GeoJSON
            key={JSON.stringify(region.geojson).slice(0, 60)}
            data={region.geojson}
            style={{ color: "#38d0d8", weight: 1.5, fill: false, dashArray: "4 3" }}
          />
        )}

        {regionBounds && <FitToRegion bounds={regionBounds} />}
        <DrawLayer />
        <ClickInspect grid={result?.grid} values={result?.ndvi} />
        {inspect && <InspectPopup inspect={inspect} composite={result?.composite} />}
      </MapContainer>

      <Legend mode={view} cvd={palette === "cvd"} />
      <DrawToolbar />
      {mode === "snapshot" && !anomaly && <TimeSlider onFrame={onFrame} />}
      {snapshot.status === "loading" && <LoadingVeil snapshot={snapshot} />}
      {anomaly && historical.status === "loading" && (
        <LoadingVeil snapshot={{ message: "Computing 20-year baseline…", progress: 60 }} />
      )}
    </div>
  );
}

function LoadingVeil({ snapshot }) {
  return (
    <div className="map-veil">
      <div className="map-veil-card panel fade-up">
        <div className="veil-spinner" />
        <div className="veil-msg">{snapshot.message || "Loading…"}</div>
        <div className="veil-bar"><span style={{ width: `${snapshot.progress}%` }} /></div>
      </div>
    </div>
  );
}
