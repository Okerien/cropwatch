/* Export suite (Feature 12) — every format a downstream workflow needs.
 *
 * PNG   → presentation slide (map capture, white-labelled footer strip)
 * PDF   → one-page field report (severity headline, stats, map, AI paragraph)
 * CSV   → analysis in Excel/R/Python (one row per composite)
 * GeoJSON → GIS handoff (region boundary + full stats as properties)
 *
 * All client-side; no backend round-trips beyond data already loaded.
 */
// Heavy libs are dynamically imported on first use — they only matter when an
// export button is clicked, so they stay out of the initial bundle.
const getHtml2canvas = async () => (await import("html2canvas")).default;
const getJsPDF = async () => (await import("jspdf")).jsPDF;

function download(blob, filename) {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  a.click();
  URL.revokeObjectURL(a.href);
}

function stamp(regionName) {
  const safe = (regionName || "region").replace(/[^\w-]+/g, "-");
  return `CropWatch_${safe}_${new Date().toISOString().slice(0, 10)}`;
}

/** Capture the map viewport (base map + NDVI overlay + boundary) as a canvas. */
async function captureMap() {
  const el = document.querySelector(".map-wrap");
  if (!el) throw new Error("Map is not on screen.");
  const html2canvas = await getHtml2canvas();
  return html2canvas(el, {
    useCORS: true, allowTaint: false, scale: 2,
    backgroundColor: "#0a0e14",
    ignoreElements: (node) =>
      node.classList?.contains("timeslider") || node.classList?.contains("map-veil"),
  });
}

/* --------------------------------------------------------------------- */
export async function exportPNG({ regionName, composite, severity }) {
  const mapCanvas = await captureMap();

  // Compose onto a white-backed canvas with a caption bar (spec: PNG always
  // presentation-ready, white background regardless of app theme).
  const pad = 24, bar = 88;
  const out = document.createElement("canvas");
  out.width = mapCanvas.width + pad * 2;
  out.height = mapCanvas.height + pad * 2 + bar;
  const ctx = out.getContext("2d");
  ctx.fillStyle = "#ffffff";
  ctx.fillRect(0, 0, out.width, out.height);
  ctx.drawImage(mapCanvas, pad, pad);

  const baseY = mapCanvas.height + pad + 34;
  ctx.fillStyle = "#111827";
  ctx.font = "600 30px Geist, Arial, sans-serif";
  ctx.fillText(regionName || "CropWatch region", pad, baseY);
  ctx.fillStyle = "#4b5563";
  ctx.font = "24px Geist Mono, monospace";
  const sub = [
    composite?.date_label,
    severity ? `severity ${severity.score}/100 (${severity.label})` : null,
    "NASA MODIS via CropWatch",
  ].filter(Boolean).join("   ·   ");
  ctx.fillText(sub, pad, baseY + 34);

  out.toBlob((blob) => download(blob, `${stamp(regionName)}.png`), "image/png");
}

/* --------------------------------------------------------------------- */
export function exportCSV({ regionName, trendPoints, stats }) {
  const header = "composite_date,mean_ndvi,classification";
  const rows = (trendPoints || []).map(
    (p) => `${p.date},${p.mean_ndvi},${p.classification}`);
  if (!rows.length && stats?.mean != null) {
    rows.push(`${new Date().toISOString().slice(0, 10)},${stats.mean},current`);
  }
  const blob = new Blob([header + "\n" + rows.join("\n") + "\n"], { type: "text/csv" });
  download(blob, `${stamp(regionName)}.csv`);
}

/* --------------------------------------------------------------------- */
export function exportGeoJSON({ regionName, geojson, stats, composite, zoneFeatures }) {
  const geometry = geojson?.type === "Feature" ? geojson.geometry : geojson;
  const zones = stats?.zones || {};
  const boundary = {
    type: "Feature",
    geometry,
    properties: {
      layer: "region_boundary",
      name: regionName,
      composite: composite?.date_label,
      mean_ndvi: stats?.mean,
      median_ndvi: stats?.median,
      std_ndvi: stats?.std,
      severity_score: stats?.severity?.score,
      severity_label: stats?.severity?.label,
      ...Object.fromEntries(
        Object.entries(zones).map(([k, v]) => [`pct_${k}`, v.pct])),
      source: "NASA MODIS via CropWatch",
    },
  };
  // Stress-zone MultiPolygons (Feature 2) follow the boundary, one per class.
  const features = [boundary, ...(zoneFeatures || []).map((f) => ({
    ...f, properties: { layer: "stress_zone", ...f.properties },
  }))];
  const blob = new Blob(
    [JSON.stringify({ type: "FeatureCollection", features }, null, 2)],
    { type: "application/geo+json" });
  download(blob, `${stamp(regionName)}.geojson`);
}

/* --------------------------------------------------------------------- */
export async function exportPDF({ regionName, composite, stats, historical, report }) {
  const severity = stats?.severity;
  const jsPDF = await getJsPDF();
  const doc = new jsPDF({ unit: "mm", format: "a4" });
  const W = 210, M = 16;
  let y = 18;

  // Header
  doc.setFont("helvetica", "bold").setFontSize(18).setTextColor(17, 24, 39);
  doc.text("CropWatch Field Report", M, y);
  doc.setFont("helvetica", "normal").setFontSize(10).setTextColor(107, 114, 128);
  doc.text(new Date().toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric" }),
    W - M, y, { align: "right" });
  y += 8;
  doc.setDrawColor(229, 231, 235).line(M, y, W - M, y);
  y += 9;

  // Region + severity headline
  doc.setFont("helvetica", "bold").setFontSize(13).setTextColor(17, 24, 39);
  doc.text(regionName || "Selected region", M, y);
  doc.setFont("helvetica", "normal").setFontSize(9.5).setTextColor(107, 114, 128);
  doc.text(`Composite: ${composite?.date_label || "n/a"} · NASA MODIS (MOD13Q1, 250 m)`, M, y + 5.5);
  if (severity) {
    doc.setFont("helvetica", "bold").setFontSize(30).setTextColor(180, 83, 9);
    doc.text(String(severity.score), W - M, y + 4, { align: "right" });
    doc.setFontSize(10).setTextColor(107, 114, 128);
    doc.text(severity.label, W - M, y + 10, { align: "right" });
  }
  y += 17;

  // Map capture
  try {
    const mapCanvas = await captureMap();
    const imgW = W - M * 2;
    const imgH = Math.min(95, (mapCanvas.height / mapCanvas.width) * imgW);
    doc.addImage(mapCanvas.toDataURL("image/jpeg", 0.85), "JPEG", M, y, imgW, imgH);
    y += imgH + 8;
  } catch { /* map capture is best-effort */ }

  // Stats row
  if (stats?.mean != null) {
    doc.setFont("helvetica", "bold").setFontSize(10).setTextColor(17, 24, 39);
    doc.text("Statistics", M, y); y += 5;
    doc.setFont("helvetica", "normal").setFontSize(9).setTextColor(55, 65, 81);
    const zones = stats.zones || {};
    const line1 = `Mean NDVI ${stats.mean}   ·   Median ${stats.median}   ·   Std ${stats.std}`;
    const line2 = `Stress areas: severe ${zones.severe?.pct ?? 0}% · moderate ${zones.moderate?.pct ?? 0}% · mild ${zones.mild?.pct ?? 0}% · healthy ${zones.healthy?.pct ?? 0}% · dense ${zones.dense_healthy?.pct ?? 0}%`;
    doc.text(line1, M, y); y += 5;
    doc.text(line2, M, y); y += 8;
  }

  // Historical context
  if (historical?.interpretation) {
    doc.setFont("helvetica", "bold").setFontSize(10).setTextColor(17, 24, 39);
    doc.text("Historical context", M, y); y += 5;
    doc.setFont("helvetica", "normal").setFontSize(9).setTextColor(55, 65, 81);
    const lines = doc.splitTextToSize(historical.interpretation, W - M * 2);
    doc.text(lines, M, y); y += lines.length * 4.4 + 3;
    const ana = (historical.analogue_years || [])
      .map((a) => `${a.year} (${a.match_quality}, yield ${a.yield_deviation_pct > 0 ? "+" : ""}${a.yield_deviation_pct}%)`)
      .join("   ·   ");
    if (ana) { doc.text(`Analogue years: ${ana}`, M, y); y += 8; }
  }

  // AI field report
  if (report) {
    doc.setFont("helvetica", "bold").setFontSize(10).setTextColor(17, 24, 39);
    doc.text("Field report", M, y); y += 5;
    doc.setFont("helvetica", "normal").setFontSize(9).setTextColor(55, 65, 81);
    const lines = doc.splitTextToSize(report, W - M * 2);
    doc.text(lines, M, y); y += lines.length * 4.4 + 4;
  }

  // Footer
  doc.setFontSize(8).setTextColor(156, 163, 175);
  doc.text("Data: NASA MODIS via AppEEARS · CHIRPS · FAOSTAT — generated by CropWatch", M, 290);

  doc.save(`${stamp(regionName)}.pdf`);
}
