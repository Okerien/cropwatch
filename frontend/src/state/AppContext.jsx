/* Global app state — React Context + useReducer (no Redux, per spec).
 *
 * Holds the active region, the NDVI snapshot result, the current analysis mode
 * and map view, and display settings. Async orchestration (loading a region →
 * fetching NDVI with progress) lives in the `loadRegion` action so components
 * stay declarative.
 */
import { createContext, useContext, useReducer, useCallback, useRef } from "react";
import { api } from "../services/cropwatchApi";
import * as wl from "../lib/watchlist";

const AppCtx = createContext(null);
export const useApp = () => useContext(AppCtx);

const initial = {
  region: null,            // { geojson, name, meta }
  snapshot: { status: "idle", progress: 0, message: "", result: null, error: null },
  historical: { status: "idle", result: null, error: null },
  mode: "snapshot",        // snapshot | trend | historical
  view: "absolute",        // absolute | anomaly
  palette: "normal",       // normal | cvd
  inspect: null,           // clicked pixel detail
  drawMode: null,          // null | "rect" | "poly"
  watchlist: wl.loadRegions(),
  regionStatus: {},        // id -> { score, label, colour, mean } (background-fetched)
  alerts: [],              // evaluated threshold breaches
};

function reducer(s, a) {
  switch (a.type) {
    case "REGION_SET":
      return { ...s, region: a.region, inspect: null,
               snapshot: { status: "loading", progress: 5, message: "Requesting satellite data…", result: null, error: null },
               historical: { status: "idle", result: null, error: null } };
    case "HIST_LOADING":
      return { ...s, historical: { status: "loading", result: null, error: null } };
    case "HIST_OK":
      return { ...s, historical: { status: "ready", result: a.result, error: null } };
    case "HIST_ERR":
      return { ...s, historical: { status: "error", result: null, error: a.error } };
    case "SNAP_PROGRESS":
      return { ...s, snapshot: { ...s.snapshot, status: "loading", progress: a.progress, message: a.message } };
    case "SNAP_OK":
      return { ...s, snapshot: { status: "ready", progress: 100, message: "", result: a.result, error: null } };
    case "SNAP_ERR":
      return { ...s, snapshot: { status: "error", progress: 0, message: "", result: null, error: a.error } };
    case "WATCHLIST": return { ...s, watchlist: a.list };
    case "REGION_STATUS":
      return { ...s, regionStatus: { ...s.regionStatus, [a.id]: a.status } };
    case "ALERTS": return { ...s, alerts: a.alerts };
    case "MODE": return { ...s, mode: a.mode };
    case "VIEW": return { ...s, view: a.view };
    case "PALETTE": return { ...s, palette: a.palette };
    case "INSPECT": return { ...s, inspect: a.inspect };
    case "DRAW_MODE": return { ...s, drawMode: a.drawMode };
    default: return s;
  }
}

export function AppProvider({ children }) {
  const [state, dispatch] = useReducer(reducer, initial);
  const reqId = useRef(0);

  const loadRegion = useCallback(async (geojson, name) => {
    const id = ++reqId.current;
    dispatch({ type: "REGION_SET", region: { geojson, name } });
    try {
      const result = await api.ndviAwait(geojson, {}, (progress, message) => {
        if (id === reqId.current) dispatch({ type: "SNAP_PROGRESS", progress, message });
      });
      if (id === reqId.current) dispatch({ type: "SNAP_OK", result });
    } catch (err) {
      if (id === reqId.current)
        dispatch({ type: "SNAP_ERR", error: { message: err.message, hint: err.hint } });
    }
  }, []);

  const loadHistorical = useCallback(async (geojson, years = 20) => {
    dispatch({ type: "HIST_LOADING" });
    try {
      const result = await api.historical(geojson, { years });
      dispatch({ type: "HIST_OK", result });
    } catch (err) {
      dispatch({ type: "HIST_ERR", error: { message: err.message, hint: err.hint } });
    }
  }, []);

  // --- Watchlist actions --------------------------------------------------
  const saveRegion = useCallback((name, geojson, note = "") => {
    const { list, region } = wl.addRegion({ name, geojson, note });
    dispatch({ type: "WATCHLIST", list });
    return region;
  }, []);

  const patchRegion = useCallback((id, patch) => {
    dispatch({ type: "WATCHLIST", list: wl.updateRegion(id, patch) });
  }, []);

  const deleteRegion = useCallback((id) => {
    dispatch({ type: "WATCHLIST", list: wl.removeRegion(id) });
  }, []);

  /** Background pass: fetch current severity for each saved region, then
   *  evaluate alert thresholds (Feature 10). Server cache makes this cheap. */
  const refreshWatchlistStatus = useCallback(async (regions) => {
    const alerts = [];
    await Promise.allSettled(regions.map(async (r) => {
      try {
        const res = await api.ndviAwait(r.geojson);
        const sev = res.stats.severity;
        const mean = res.stats.mean;
        dispatch({ type: "REGION_STATUS", id: r.id,
                   status: { score: sev.score, label: sev.label, colour: sev.colour, mean } });
        if (r.threshold != null && mean != null) {
          const breached = r.thresholdMode === "above" ? mean >= r.threshold : mean <= r.threshold;
          if (breached) {
            alerts.push({ id: r.id, name: r.name, mean, threshold: r.threshold,
                          mode: r.thresholdMode, geojson: r.geojson });
          }
        }
      } catch { /* leave status unknown */ }
    }));
    dispatch({ type: "ALERTS", alerts });
  }, []);

  const value = {
    ...state,
    dispatch,
    loadRegion,
    loadHistorical,
    saveRegion,
    patchRegion,
    deleteRegion,
    refreshWatchlistStatus,
    setMode: (mode) => dispatch({ type: "MODE", mode }),
    setView: (view) => dispatch({ type: "VIEW", view }),
    setPalette: (palette) => dispatch({ type: "PALETTE", palette }),
    setInspect: (inspect) => dispatch({ type: "INSPECT", inspect }),
    setDrawMode: (drawMode) => dispatch({ type: "DRAW_MODE", drawMode }),
  };
  return <AppCtx.Provider value={value}>{children}</AppCtx.Provider>;
}
