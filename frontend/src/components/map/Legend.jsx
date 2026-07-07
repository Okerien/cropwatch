import { ndviLegend, zLegend } from "../../lib/ndviColor";

/** Always-visible colour scale legend for the active map view. */
export function Legend({ mode, cvd }) {
  const anomaly = mode === "anomaly";
  const stops = anomaly ? zLegend() : ndviLegend(cvd);
  const gradient = `linear-gradient(90deg, ${stops.map((s) => s.hex).join(",")})`;

  return (
    <div className="legend panel">
      <div className="legend-title eyebrow">
        {anomaly ? "Anomaly (z-score)" : "NDVI"}
      </div>
      <div className="legend-bar" style={{ background: gradient }} />
      <div className="legend-ticks num">
        {anomaly
          ? <><span>−2.5</span><span>0</span><span>+2.5</span></>
          : <><span>0.0</span><span>0.5</span><span>1.0</span></>}
      </div>
      <div className="legend-caption">
        {anomaly ? "red = below normal · blue = above" : "red = stressed · green = healthy"}
      </div>
    </div>
  );
}
