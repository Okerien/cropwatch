import { useEffect, useState, useMemo } from "react";
import {
  ResponsiveContainer, ComposedChart, LineChart, Line, BarChart, Bar,
  XAxis, YAxis, CartesianGrid, Tooltip, ReferenceLine, Cell,
} from "recharts";
import { api } from "../../services/cropwatchApi";
import { useApp } from "../../state/AppContext";
import { classifyNDVI } from "../../lib/ndviColor";
import { AXIS, GRID, THRESHOLDS, fmtDate } from "./chartTheme";
import "./charts.css";

const RANGES = [
  { key: "3m", label: "3 mo" }, { key: "6m", label: "6 mo" },
  { key: "12m", label: "12 mo" }, { key: "5y", label: "5 yr" },
];

/* 12-colour accessible palette for multi-region comparison lines. */
const COMPARE_COLORS = [
  "#38d0d8", "#f5c842", "#e8730a", "#a8d26b", "#c084fc", "#60a5fa",
  "#f472b6", "#34d399", "#facc15", "#fb7185", "#93c5fd", "#fdba74",
];

export function TrendPanel() {
  const { region, historical, loadHistorical, watchlist } = useApp();
  const [range, setRange] = useState("6m");
  const [trend, setTrend] = useState({ status: "idle", data: null });
  const [rain, setRain] = useState({ status: "idle", data: null });
  const [compare, setCompare] = useState({});   // name -> points

  const starred = watchlist.filter((r) => r.starred).slice(0, 10);

  // Fetch starred regions' series for overlay (Feature 9 multi-region compare).
  useEffect(() => {
    let live = true;
    if (!starred.length) { setCompare({}); return; }
    (async () => {
      const out = {};
      await Promise.allSettled(starred.map(async (r) => {
        try { out[r.name] = (await api.trend(r.geojson, range)).points; } catch { /* skip */ }
      }));
      if (live) setCompare(out);
    })();
    return () => { live = false; };
  }, [range, starred.map((r) => r.id).join(",")]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!region?.geojson) return;
    let live = true;
    setTrend({ status: "loading", data: null });
    setRain({ status: "loading", data: null });

    api.trend(region.geojson, range)
      .then((t) => {
        if (!live) return;
        setTrend({ status: "ready", data: t });
        // Rainfall for the same window; bbox via geometry validation metadata.
        return api.validateGeojson(region.geojson).then((v) =>
          api.rainfall(v.bbox, { start_date: t.start, end_date: t.end })
            .then((r) => live && setRain({ status: "ready", data: r })));
      })
      .catch(() => {
        if (!live) return;
        setTrend((s) => (s.data ? s : { status: "error", data: null }));
        setRain({ status: "error", data: null });
      });

    if (historical.status === "idle") loadHistorical(region.geojson);
    return () => { live = false; };
  }, [region, range]); // eslint-disable-line react-hooks/exhaustive-deps

  const zSeries = historical.result?.anomaly_time_series?.points || [];

  return (
    <div className="trend-panel panel fade-up">
      <div className="trend-head">
        <span className="eyebrow">NDVI trend · {region?.name}</span>
        <div className="range-switch">
          {RANGES.map((r) => (
            <button key={r.key} className={`range-btn ${range === r.key ? "on" : ""}`}
              onClick={() => setRange(r.key)}>{r.label}</button>
          ))}
        </div>
      </div>

      {Object.keys(compare).length > 0 && (
        <div className="compare-chips">
          <span className="compare-chip" style={{ "--c": "#38d0d8" }}>{region?.name} (active)</span>
          {Object.keys(compare).filter((n) => n !== region?.name).map((n, i) => (
            <span key={n} className="compare-chip"
              style={{ "--c": COMPARE_COLORS[(i + 1) % COMPARE_COLORS.length] }}>{n}</span>
          ))}
        </div>
      )}

      <div className="charts-scroll">
        <NdviChart trend={trend} range={range} compare={compare} activeName={region?.name} />
        <RainChart rain={rain} />
        {zSeries.length > 0 && <ZChart points={zSeries} />}
      </div>

      {rain.data?.correlation && (
        <div className="corr-line">
          <span className="corr-value num">{rain.data.correlation.display}</span>
          {rain.data.correlation.note && (
            <span className="corr-note">{rain.data.correlation.note}</span>
          )}
        </div>
      )}
    </div>
  );
}

/* --- NDVI spline with stress thresholds + multi-region overlay ----------- */
function NdviChart({ trend, range, compare = {}, activeName }) {
  const points = trend.data?.points || [];
  // Merge active + compared series into one dataset keyed by composite date.
  const data = useMemo(() => {
    const byDate = new Map();
    points.forEach((p) => byDate.set(p.date, { date: p.date, mean_ndvi: p.mean_ndvi }));
    Object.entries(compare).forEach(([name, pts]) => {
      if (name === activeName) return;
      (pts || []).forEach((p) => {
        const row = byDate.get(p.date) || { date: p.date };
        row[name] = p.mean_ndvi;
        byDate.set(p.date, row);
      });
    });
    return [...byDate.values()].sort((a, b) => a.date.localeCompare(b.date));
  }, [points, compare, activeName]);

  if (trend.status === "loading") return <div className="skeleton chart-skel" />;
  if (!data.length) return null;
  const compareNames = Object.keys(compare).filter((n) => n !== activeName);

  return (
    <div className="chart-block">
      <ResponsiveContainer width="100%" height={190}>
        <ComposedChart data={data} margin={{ top: 8, right: 12, left: -18, bottom: 0 }}>
          <CartesianGrid {...GRID} />
          <XAxis dataKey="date" {...AXIS} tickFormatter={(v) => fmtDate(v, range)}
            interval="preserveStartEnd" minTickGap={42} />
          <YAxis domain={[0, 1]} ticks={[0, 0.2, 0.4, 0.5, 0.7, 1]} {...AXIS} width={46} />
          {THRESHOLDS.map((t) => (
            <ReferenceLine key={t.y} y={t.y} stroke={t.color} strokeOpacity={0.35}
              strokeDasharray="4 4" />
          ))}
          <Tooltip content={<NdviTooltip />} cursor={{ stroke: "#38d0d8", strokeOpacity: 0.4 }} />
          <Line type="monotone" dataKey="mean_ndvi" name={activeName || "Active"}
            stroke="#38d0d8" strokeWidth={2}
            dot={false} activeDot={{ r: 4, fill: "#6ee7ee", strokeWidth: 0 }}
            isAnimationActive={false} />
          {compareNames.map((n, i) => (
            <Line key={n} type="monotone" dataKey={n} name={n}
              stroke={COMPARE_COLORS[(i + 1) % COMPARE_COLORS.length]}
              strokeWidth={1.5} dot={false} isAnimationActive={false} connectNulls />
          ))}
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}

function NdviTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="cw-tip">
      <div className="cw-tip-date">{new Date(label).toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric" })}</div>
      {payload.filter((p) => p.value != null).map((p) => {
        const zone = classifyNDVI(p.value);
        return (
          <div key={p.dataKey} className="cw-tip-main">
            <span className="cw-tip-swatch" style={{ background: p.stroke || zone?.color }} />
            <span className="num">{p.value.toFixed(3)}</span>
            <span className="cw-tip-zone">
              {payload.length > 1 ? p.name : zone?.label}
            </span>
          </div>
        );
      })}
    </div>
  );
}

/* --- Rainfall anomaly bars ----------------------------------------------- */
function RainChart({ rain }) {
  const bars = rain.data?.bars || [];
  if (rain.status === "loading") return <div className="skeleton chart-skel-sm" />;
  if (!bars.length) return null;

  return (
    <div className="chart-block">
      <div className="chart-sub eyebrow">Rainfall vs long-term average</div>
      <ResponsiveContainer width="100%" height={120}>
        <BarChart data={bars} margin={{ top: 4, right: 12, left: -18, bottom: 0 }}>
          <CartesianGrid {...GRID} />
          <XAxis dataKey="period" {...AXIS} interval="preserveStartEnd" minTickGap={48} />
          <YAxis {...AXIS} width={46} tickFormatter={(v) => `${v}%`} />
          <ReferenceLine y={100} stroke="#7d8b9c" strokeWidth={1}
            label={{ value: "avg", fill: "#566372", fontSize: 9, position: "right" }} />
          <ReferenceLine y={75} stroke="#e5484d" strokeOpacity={0.5} strokeDasharray="4 4" />
          <Tooltip content={<RainTooltip />} cursor={{ fill: "rgba(56,208,216,0.06)" }} />
          <Bar dataKey="anomaly_pct" isAnimationActive={false} radius={[2, 2, 0, 0]}>
            {bars.map((b, i) => (
              <Cell key={i} fill={b.deficit ? "#B34A42" : "#3E7CB1"} fillOpacity={0.85} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

function RainTooltip({ active, payload }) {
  if (!active || !payload?.length) return null;
  const b = payload[0].payload;
  return (
    <div className="cw-tip">
      <div className="cw-tip-date">{b.period}</div>
      <div className="cw-tip-main">
        <span className="num">{b.anomaly_pct}%</span>
        <span className="cw-tip-zone">{b.deficit ? "below average" : "above average"}</span>
      </div>
      <div className="cw-tip-meta num">{b.rainfall_mm} mm · avg {b.climatology_mm} mm</div>
    </div>
  );
}

/* --- Z-score anomaly series ---------------------------------------------- */
function ZChart({ points }) {
  const data = useMemo(
    () => points.map((p) => ({ ...p, z: p.mean_z })), [points]);
  return (
    <div className="chart-block">
      <div className="chart-sub eyebrow">Anomaly trend (z-score)</div>
      <ResponsiveContainer width="100%" height={120}>
        <LineChart data={data} margin={{ top: 4, right: 12, left: -18, bottom: 0 }}>
          <CartesianGrid {...GRID} />
          <XAxis dataKey="date" {...AXIS} tickFormatter={(v) => fmtDate(v)}
            interval="preserveStartEnd" minTickGap={42} />
          <YAxis domain={[-3, 3]} ticks={[-2, -1, 0, 1, 2]} {...AXIS} width={46} />
          <ReferenceLine y={0} stroke="#b6c2d0" strokeWidth={1} />
          <ReferenceLine y={-1} stroke="#E8870A" strokeOpacity={0.4} strokeDasharray="4 4" />
          <ReferenceLine y={-2} stroke="#e5484d" strokeOpacity={0.4} strokeDasharray="4 4" />
          <Tooltip content={<ZTooltip />} cursor={{ stroke: "#38d0d8", strokeOpacity: 0.4 }} />
          <Line type="monotone" dataKey="z" stroke="#e8870a" strokeWidth={2}
            dot={false} activeDot={{ r: 4 }} isAnimationActive={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

function ZTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  const v = payload[0].value;
  return (
    <div className="cw-tip">
      <div className="cw-tip-date">{fmtDate(label)}</div>
      <div className="cw-tip-main">
        <span className="num">{v > 0 ? "+" : ""}{v?.toFixed(2)}σ</span>
        <span className="cw-tip-zone">{v <= -2 ? "severe anomaly" : v <= -1 ? "moderate anomaly" : v < 1 ? "near normal" : "above normal"}</span>
      </div>
    </div>
  );
}
