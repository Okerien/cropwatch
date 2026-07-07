import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { MagnifyingGlass, PencilSimpleLine, Crosshair, UploadSimple } from "@phosphor-icons/react";
import { api } from "../../services/cropwatchApi";
import { useApp } from "../../state/AppContext";
import { RegionSearch } from "./RegionSearch";
import "./areaTools.css";

const TABS = [
  { key: "search", icon: MagnifyingGlass },
  { key: "draw", icon: PencilSimpleLine },
  { key: "coords", icon: Crosshair },
  { key: "upload", icon: UploadSimple },
];

/** All five §3 input methods behind one compact tab row. */
export function AreaTools() {
  const { t } = useTranslation();
  const [tab, setTab] = useState("search");
  return (
    <div>
      <div className="atabs" role="tablist" aria-label="Area input method">
        {TABS.map(({ key, icon: Icon }) => (
          <button key={key} role="tab" aria-selected={tab === key}
            className={`atab ${tab === key ? "on" : ""}`} onClick={() => setTab(key)}>
            <Icon size={13} /> {t(`area.${key}`)}
          </button>
        ))}
      </div>
      {tab === "search" && <RegionSearch />}
      {tab === "draw" && <DrawTools />}
      {tab === "coords" && <CoordEntry />}
      {tab === "upload" && <UploadArea />}
    </div>
  );
}

/* --- Draw (§3.1) ---------------------------------------------------------- */
function DrawTools() {
  const { drawMode, setDrawMode } = useApp();
  return (
    <div className="draw-tools">
      <button className={`btn ${drawMode === "rect" ? "btn-accent" : ""}`}
        onClick={() => setDrawMode(drawMode === "rect" ? null : "rect")}>
        Rectangle
      </button>
      <button className={`btn ${drawMode === "poly" ? "btn-accent" : ""}`}
        onClick={() => setDrawMode(drawMode === "poly" ? null : "poly")}>
        Polygon
      </button>
      <p className="ahint">
        {drawMode === "rect" && "Click and drag on the map to define the box."}
        {drawMode === "poly" && "Click to place vertices; double-click to close. Esc cancels."}
        {!drawMode && "Pick a shape, then draw directly on the map."}
      </p>
    </div>
  );
}

/* --- Coordinates (§3.3) ---------------------------------------------------- */
function circlePolygon(lat, lon, radiusKm, sides = 64) {
  const ring = [];
  const dLat = radiusKm / 111.32;
  const dLon = radiusKm / (111.32 * Math.cos((lat * Math.PI) / 180));
  for (let i = 0; i <= sides; i++) {
    const a = (2 * Math.PI * i) / sides;
    ring.push([lon + dLon * Math.cos(a), lat + dLat * Math.sin(a)]);
  }
  return { type: "Polygon", coordinates: [ring] };
}

function CoordEntry() {
  const { loadRegion } = useApp();
  const [sub, setSub] = useState("point");   // point | bbox
  const [vals, setVals] = useState({ lat: "", lon: "", radius: "25",
                                     w: "", s: "", e: "", n: "" });
  const [err, setErr] = useState(null);
  const set = (k) => (e) => setVals((v) => ({ ...v, [k]: e.target.value }));

  const useMyLocation = () => {
    navigator.geolocation?.getCurrentPosition(
      (pos) => setVals((v) => ({ ...v, lat: pos.coords.latitude.toFixed(4),
                                 lon: pos.coords.longitude.toFixed(4) })),
      () => setErr("Location permission was denied."));
  };

  const submit = () => {
    setErr(null);
    try {
      if (sub === "point") {
        const lat = parseFloat(vals.lat), lon = parseFloat(vals.lon), r = parseFloat(vals.radius);
        if ([lat, lon, r].some(Number.isNaN)) throw new Error("Enter latitude, longitude, and radius as numbers.");
        if (r <= 0 || r > 400) throw new Error("Radius must be between 0 and 400 km.");
        loadRegion(circlePolygon(lat, lon, r),
          `${lat.toFixed(2)}, ${lon.toFixed(2)} · ${r} km`);
      } else {
        const { w, s, e, n } = Object.fromEntries(
          ["w", "s", "e", "n"].map((k) => [k, parseFloat(vals[k])]));
        if ([w, s, e, n].some(Number.isNaN)) throw new Error("Enter all four bounding-box values.");
        if (w >= e || s >= n) throw new Error("West must be < East and South < North.");
        loadRegion({ type: "Polygon",
                     coordinates: [[[w, s], [e, s], [e, n], [w, n], [w, s]]] },
          `BBox ${s.toFixed(1)},${w.toFixed(1)} → ${n.toFixed(1)},${e.toFixed(1)}`);
      }
    } catch (ex) { setErr(ex.message); }
  };

  return (
    <div className="coord-entry">
      <div className="coord-sub">
        <button className={sub === "point" ? "on" : ""} onClick={() => setSub("point")}>Point + radius</button>
        <button className={sub === "bbox" ? "on" : ""} onClick={() => setSub("bbox")}>Bounding box</button>
      </div>

      {sub === "point" ? (
        <div className="coord-grid">
          <input placeholder="Latitude" value={vals.lat} onChange={set("lat")} inputMode="decimal" />
          <input placeholder="Longitude" value={vals.lon} onChange={set("lon")} inputMode="decimal" />
          <input placeholder="Radius km" value={vals.radius} onChange={set("radius")} inputMode="decimal" />
          <button className="coord-loc" onClick={useMyLocation} title="Use current location">
            <Crosshair size={14} />
          </button>
        </div>
      ) : (
        <div className="coord-grid four">
          <input placeholder="West lon" value={vals.w} onChange={set("w")} inputMode="decimal" />
          <input placeholder="South lat" value={vals.s} onChange={set("s")} inputMode="decimal" />
          <input placeholder="East lon" value={vals.e} onChange={set("e")} inputMode="decimal" />
          <input placeholder="North lat" value={vals.n} onChange={set("n")} inputMode="decimal" />
        </div>
      )}

      {err && <p className="aerr">{err}</p>}
      <button className="btn btn-accent ago" onClick={submit}>Use this area</button>
    </div>
  );
}

/* --- Upload (§3.4 / §3.5) --------------------------------------------------- */
function UploadArea() {
  const { loadRegion } = useApp();
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  const [warns, setWarns] = useState([]);
  const fileRef = useRef();

  const handle = async (file) => {
    setBusy(true); setErr(null); setWarns([]);
    try {
      if (file.name.toLowerCase().endsWith(".zip")) {
        const res = await api.convertShapefile(file);
        setWarns(res.warnings || []);
        loadRegion(res.geojson, file.name.replace(/\.zip$/i, ""));
      } else {
        const gj = JSON.parse(await file.text());
        await api.validateGeojson(gj);      // surfaces plain-English errors
        loadRegion(gj, file.name.replace(/\.(geo)?json$/i, ""));
      }
    } catch (ex) { setErr(ex.message); }
    finally { setBusy(false); }
  };

  return (
    <div className="upload-area">
      <button className="upload-drop" disabled={busy}
        onClick={() => fileRef.current?.click()}
        onDragOver={(e) => e.preventDefault()}
        onDrop={(e) => { e.preventDefault(); const f = e.dataTransfer.files?.[0]; if (f) handle(f); }}>
        <UploadSimple size={18} />
        {busy ? "Converting…" : "Drop a GeoJSON or zipped Shapefile, or click to browse"}
      </button>
      <input ref={fileRef} type="file" hidden accept=".geojson,.json,.zip"
        onChange={(e) => { const f = e.target.files?.[0]; if (f) handle(f); e.target.value = ""; }} />
      {err && <p className="aerr">{err}</p>}
      {warns.map((w, i) => <p key={i} className="awarn">{w}</p>)}
    </div>
  );
}
