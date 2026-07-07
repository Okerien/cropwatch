import { useState } from "react";
import { Image, FilePdf, FileCsv, Polygon } from "@phosphor-icons/react";
import { api } from "../../services/cropwatchApi";
import { useApp } from "../../state/AppContext";
import { exportPNG, exportPDF, exportCSV, exportGeoJSON } from "../../lib/exports";
import "./exportBar.css";

/** Feature 12: four export formats, each one click, all client-side. */
export function ExportBar({ reportText }) {
  const { region, snapshot, historical } = useApp();
  const [busy, setBusy] = useState(null);
  const result = snapshot.result;
  if (snapshot.status !== "ready" || !result) return null;

  const ctx = {
    regionName: region?.name,
    geojson: region?.geojson,
    composite: result.composite,
    stats: result.stats,
    severity: result.stats?.severity,
    historical: historical.result,
    report: reportText,
  };

  const run = async (kind, fn) => {
    setBusy(kind);
    try { await fn(); } catch (err) { alert(err.message); } finally { setBusy(null); }
  };

  const buttons = [
    { kind: "png", icon: <Image size={14} />, label: "PNG",
      fn: () => exportPNG(ctx), title: "Map image for slides" },
    { kind: "pdf", icon: <FilePdf size={14} />, label: "PDF",
      fn: () => exportPDF(ctx), title: "One-page field report" },
    { kind: "csv", icon: <FileCsv size={14} />, label: "CSV",
      fn: async () => {
        const t = await api.trend(region.geojson, "12m");
        exportCSV({ ...ctx, trendPoints: t.points });
      }, title: "12-month composite series" },
    { kind: "geojson", icon: <Polygon size={14} />, label: "GeoJSON",
      fn: async () => {
        let zoneFeatures = [];
        try { zoneFeatures = (await api.zones(region.geojson)).features; } catch { /* boundary-only */ }
        exportGeoJSON({ ...ctx, zoneFeatures });
      }, title: "Stress zones + boundary for GIS" },
  ];

  return (
    <div className="export-bar">
      {buttons.map((b) => (
        <button key={b.kind} className="export-btn" title={b.title}
          disabled={busy !== null} onClick={() => run(b.kind, b.fn)}>
          {b.icon} {busy === b.kind ? "…" : b.label}
        </button>
      ))}
    </div>
  );
}
