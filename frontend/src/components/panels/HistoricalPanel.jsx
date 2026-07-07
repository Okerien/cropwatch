import { useEffect } from "react";
import { useApp } from "../../state/AppContext";
import { ClockCounterClockwise } from "@phosphor-icons/react";
import "./historical.css";

/** Historical Comparison mode: interpretation, z-distribution, analogue years. */
export function HistoricalPanel() {
  const { region, historical, loadHistorical, setView } = useApp();

  useEffect(() => {
    // Entering this mode: switch the map to anomaly and ensure data is loaded.
    setView("anomaly");
    if (region?.geojson && historical.status === "idle") loadHistorical(region.geojson);
    return () => setView("absolute");
  }, [region]); // eslint-disable-line react-hooks/exhaustive-deps

  if (historical.status === "loading" || historical.status === "idle") {
    return (
      <div className="hist panel">
        <div className="skeleton" style={{ height: 60, marginBottom: 12 }} />
        <div className="skeleton" style={{ height: 120, marginBottom: 12 }} />
        <div className="skeleton" style={{ height: 140 }} />
      </div>
    );
  }
  if (historical.status === "error") {
    return <div className="hist panel"><p className="hist-err">{historical.error?.message}</p></div>;
  }

  const h = historical.result;
  const dist = h.z_distribution || {};

  return (
    <div className="hist panel fade-up">
      <div className="hist-head">
        <ClockCounterClockwise size={16} color="var(--accent)" />
        <span>vs {h.comparison_years}-year baseline ({h.baseline_range?.[0]}–{h.baseline_range?.[1]})</span>
      </div>

      <div className="hist-z">
        <span className="hist-z-num num">{h.mean_z > 0 ? "+" : ""}{h.mean_z}σ</span>
        <p className="hist-interp">{h.interpretation}</p>
      </div>

      <div className="hist-dist">
        <div className="hist-dist-bar">
          {Object.entries(dist).map(([k, v]) => (
            v.pct > 0 && <span key={k} style={{ width: `${v.pct}%`, background: v.colour }} title={`${k}: ${v.pct}%`} />
          ))}
        </div>
        <div className="hist-dist-cap">
          <span>← worse than normal</span><span>better →</span>
        </div>
      </div>

      <div className="hist-analogues">
        <div className="eyebrow" style={{ marginBottom: 8 }}>Most similar past years</div>
        <table className="ana-table">
          <thead>
            <tr><th>Year</th><th>Match</th><th>Z</th><th>Yield</th><th>Season</th></tr>
          </thead>
          <tbody>
            {(h.analogue_years || []).map((a) => (
              <tr key={a.year}>
                <td className="num ana-year">{a.year}</td>
                <td><span className={`match-chip ${a.match_quality?.toLowerCase()}`}>{a.match_quality}</span></td>
                <td className="num">{a.mean_z > 0 ? "+" : ""}{a.mean_z}</td>
                <td className="num" style={{ color: a.yield_deviation_pct < 0 ? "var(--sev-significant)" : "var(--sev-good)" }}>
                  {a.yield_deviation_pct != null ? `${a.yield_deviation_pct > 0 ? "+" : ""}${a.yield_deviation_pct}%` : "–"}
                </td>
                <td><Sparkline points={a.season_sparkline} /></td>
              </tr>
            ))}
          </tbody>
        </table>
        {h.crop_context?.crop && (
          <div className="hist-crop">Yields: {h.crop_context.crop} · {h.crop_context.country || "country level"} (FAOSTAT)</div>
        )}
      </div>
    </div>
  );
}

function Sparkline({ points }) {
  if (!points?.length) return <span className="spark-none">–</span>;
  const w = 64, hgt = 20;
  const min = Math.min(...points), max = Math.max(...points);
  const span = max - min || 1;
  const d = points.map((v, i) =>
    `${i === 0 ? "M" : "L"}${(i / (points.length - 1)) * w},${hgt - ((v - min) / span) * hgt}`
  ).join(" ");
  return (
    <svg width={w} height={hgt} className="spark">
      <path d={d} fill="none" stroke="var(--accent)" strokeWidth="1.5" />
    </svg>
  );
}
