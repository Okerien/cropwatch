/* Single choke-point for every backend call. In dev, requests go to /api/*
 * (Vite proxies to Flask). In prod, VITE_API_URL points at Render.
 */
const BASE = import.meta.env.VITE_API_URL || "/api";

async function req(path, { method = "GET", body, headers, signal } = {}) {
  const res = await fetch(`${BASE}${path}`, {
    method,
    headers: { "Content-Type": "application/json", ...headers },
    body: body ? JSON.stringify(body) : undefined,
    signal,
  });
  const text = await res.text();
  const data = text ? JSON.parse(text) : null;
  if (!res.ok) {
    const err = new Error(data?.error?.message || `Request failed (${res.status})`);
    err.code = data?.error?.code;
    err.hint = data?.error?.hint;
    err.status = res.status;
    throw err;
  }
  return data;
}

export const api = {
  defaults: () => req("/defaults"),
  health: () => req("/health"),

  /** Submit an NDVI snapshot. Returns a task envelope (inline result in demo). */
  ndvi: (geojson, opts = {}) =>
    req("/ndvi", { method: "POST", body: { geojson, ...opts } }),

  ndviStatus: (taskId) => req(`/ndvi/status/${taskId}`),

  /** Poll a task to completion. onProgress(pct, message) is called each tick. */
  async ndviAwait(geojson, opts = {}, onProgress) {
    const first = await this.ndvi(geojson, opts);
    if (first.status === "complete") return first.result;
    if (first.status === "failed") throw new Error(first.message || "Task failed");
    onProgress?.(first.progress ?? 10, first.message);
    let taskId = first.task_id;
    for (let i = 0; i < 90; i++) {
      await new Promise((r) => setTimeout(r, 2000));
      const st = await this.ndviStatus(taskId);
      onProgress?.(st.progress ?? 50, st.message);
      if (st.status === "complete") return st.result;
      if (st.status === "failed") throw new Error(st.message || "Task failed");
    }
    throw new Error("Timed out waiting for satellite data.");
  },

  zones: (geojson) =>
    req("/zones", { method: "POST", body: { geojson } }),

  trend: (geojson, range = "6m") =>
    req("/trend", { method: "POST", body: { geojson, range } }),

  historical: (geojson, opts = {}) =>
    req("/historical", { method: "POST", body: { geojson, ...opts } }),

  rainfall: (bbox, { start_date, end_date } = {}) => {
    const q = new URLSearchParams({ bbox: bbox.join(",") });
    if (start_date) q.set("start_date", start_date);
    if (end_date) q.set("end_date", end_date);
    return req(`/rainfall?${q}`);
  },

  geocode: (query, limit = 8) =>
    req(`/geocode?q=${encodeURIComponent(query)}&limit=${limit}`),

  validateGeojson: (geojson) =>
    req("/validate-geojson", { method: "POST", body: { geojson } }),

  report: (payload) => req("/report", { method: "POST", body: payload }),

  async convertShapefile(file) {
    const form = new FormData();
    form.append("file", file);
    const res = await fetch(`${BASE}/convert-shapefile`, { method: "POST", body: form });
    const data = await res.json();
    if (!res.ok) throw new Error(data?.error?.message || "Shapefile conversion failed");
    return data;
  },
};
