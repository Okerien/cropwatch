/* Watchlist persistence (Features 9, 10, 18) — browser localStorage, no account.
 *
 * Each region: { id, name, note, tags[], starred, threshold, thresholdMode,
 *                geojson, createdAt }
 * `threshold` is a mean-NDVI level; `thresholdMode` "below" (stress alert) or
 * "above" (waterlogging / recovery alert). Export/import round-trips the whole
 * workspace as a GeoJSON FeatureCollection so it opens in QGIS/ArcGIS too.
 */
const KEY = "cropwatch_regions";

export function loadRegions() {
  try {
    const raw = localStorage.getItem(KEY);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

function persist(list) {
  localStorage.setItem(KEY, JSON.stringify(list));
  return list;
}

export function addRegion({ name, geojson, note = "" }) {
  const list = loadRegions();
  const region = {
    id: `r_${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`,
    name, note, tags: [], starred: false,
    threshold: null, thresholdMode: "below",
    geojson,
    createdAt: new Date().toISOString(),
  };
  return { list: persist([region, ...list]), region };
}

export function updateRegion(id, patch) {
  return persist(loadRegions().map((r) => (r.id === id ? { ...r, ...patch } : r)));
}

export function removeRegion(id) {
  return persist(loadRegions().filter((r) => r.id !== id));
}

export function exportWorkspace() {
  const fc = {
    type: "FeatureCollection",
    features: loadRegions().map((r) => ({
      type: "Feature",
      geometry: r.geojson.type === "Feature" ? r.geojson.geometry : r.geojson,
      properties: {
        name: r.name, note: r.note, tags: r.tags,
        threshold: r.threshold, created: r.createdAt, app: "CropWatch",
      },
    })),
  };
  const blob = new Blob([JSON.stringify(fc, null, 2)], { type: "application/geo+json" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `CropWatch_regions_${new Date().toISOString().slice(0, 10)}.geojson`;
  a.click();
  URL.revokeObjectURL(a.href);
}

export function importWorkspace(fileText) {
  const fc = JSON.parse(fileText);
  if (fc?.type !== "FeatureCollection") throw new Error("Not a GeoJSON FeatureCollection.");
  const existing = loadRegions();
  const imported = fc.features.map((f, i) => ({
    id: `r_${Date.now().toString(36)}_${i}`,
    name: f.properties?.name || `Imported ${i + 1}`,
    note: f.properties?.note || "",
    tags: f.properties?.tags || [],
    starred: false,
    threshold: f.properties?.threshold ?? null,
    thresholdMode: "below",
    geojson: f.geometry,
    createdAt: new Date().toISOString(),
  }));
  return persist([...imported, ...existing]);
}
