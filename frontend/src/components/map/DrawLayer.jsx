import { useEffect, useRef, useState } from "react";
import { Polygon, Rectangle, useMap, useMapEvents } from "react-leaflet";
import { useApp } from "../../state/AppContext";

/* Draw-on-map (§3.1) — native Leaflet handlers, no plugin dependency.
 * Rectangle: click-drag. Polygon: click vertices, double-click to close.
 * Works with the same loadRegion pipeline as every other input method.
 */
export function DrawLayer() {
  const { drawMode, setDrawMode, loadRegion } = useApp();
  if (!drawMode) return null;
  return drawMode === "rect"
    ? <RectDraw onDone={(gj) => { setDrawMode(null); loadRegion(gj, "Drawn rectangle"); }}
                onCancel={() => setDrawMode(null)} />
    : <PolyDraw onDone={(gj) => { setDrawMode(null); loadRegion(gj, "Drawn polygon"); }}
                onCancel={() => setDrawMode(null)} />;
}

function RectDraw({ onDone, onCancel }) {
  const map = useMap();
  const [corner1, setCorner1] = useState(null);
  const [corner2, setCorner2] = useState(null);
  const dragging = useRef(false);

  useEffect(() => {
    map.dragging.disable();
    map.getContainer().style.cursor = "crosshair";
    return () => { map.dragging.enable(); map.getContainer().style.cursor = ""; };
  }, [map]);

  useMapEvents({
    mousedown(e) { dragging.current = true; setCorner1(e.latlng); setCorner2(e.latlng); },
    mousemove(e) { if (dragging.current) setCorner2(e.latlng); },
    mouseup(e) {
      if (!dragging.current || !corner1) return;
      dragging.current = false;
      const c2 = e.latlng;
      if (Math.abs(c2.lat - corner1.lat) < 0.01 || Math.abs(c2.lng - corner1.lng) < 0.01) {
        onCancel(); return;   // degenerate click — treat as cancel
      }
      const w = Math.min(corner1.lng, c2.lng), e_ = Math.max(corner1.lng, c2.lng);
      const s = Math.min(corner1.lat, c2.lat), n = Math.max(corner1.lat, c2.lat);
      onDone({ type: "Polygon",
               coordinates: [[[w, s], [e_, s], [e_, n], [w, n], [w, s]]] });
    },
  });

  if (!corner1 || !corner2) return null;
  return <Rectangle bounds={[corner1, corner2]}
    pathOptions={{ color: "#38d0d8", weight: 1.5, dashArray: "4 3", fillOpacity: 0.08 }} />;
}

function PolyDraw({ onDone, onCancel }) {
  const map = useMap();
  const [pts, setPts] = useState([]);       // [{lat,lng}]
  const [cursor, setCursor] = useState(null);

  const finish = (points) => {
    if (points.length < 3) { onCancel(); return; }
    const ring = points.map((p) => [p.lng, p.lat]);
    ring.push(ring[0]);
    onDone({ type: "Polygon", coordinates: [ring] });
  };

  useEffect(() => {
    map.doubleClickZoom.disable();
    map.getContainer().style.cursor = "crosshair";
    const esc = (e) => e.key === "Escape" && onCancel();
    // Toolbar buttons (rendered outside the Leaflet tree) talk over events —
    // this keeps touch users off double-click, which doesn't exist for them.
    const undo = () => setPts((p) => p.slice(0, -1));
    const fin = () => setPts((p) => { finish(p); return p; });
    window.addEventListener("keydown", esc);
    window.addEventListener("cw-draw-undo", undo);
    window.addEventListener("cw-draw-finish", fin);
    return () => {
      map.doubleClickZoom.enable();
      map.getContainer().style.cursor = "";
      window.removeEventListener("keydown", esc);
      window.removeEventListener("cw-draw-undo", undo);
      window.removeEventListener("cw-draw-finish", fin);
    };
  }, [map, onCancel]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    window.dispatchEvent(new CustomEvent("cw-draw-points", { detail: pts.length }));
  }, [pts.length]);

  useMapEvents({
    click(e) { setPts((p) => [...p, e.latlng]); },
    mousemove(e) { setCursor(e.latlng); },
    dblclick() { finish(pts); },
  });

  const positions = cursor && pts.length ? [...pts, cursor] : pts;
  if (positions.length < 2) return null;
  return <Polygon positions={positions}
    pathOptions={{ color: "#38d0d8", weight: 1.5, dashArray: "4 3", fillOpacity: 0.08 }} />;
}
