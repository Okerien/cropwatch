import { useState } from "react";
import { Warning, X } from "@phosphor-icons/react";
import { useApp } from "../state/AppContext";
import "./alertBanner.css";

/** Feature 10: red banner listing every saved region whose threshold is breached.
 *  Dismissible for the session; re-evaluates on next load while the condition holds. */
export function AlertBanner() {
  const { alerts, loadRegion } = useApp();
  const [dismissed, setDismissed] = useState(
    () => sessionStorage.getItem("cw_alerts_dismissed") === "1");

  if (!alerts.length || dismissed) return null;

  return (
    <div className="alert-banner" role="alert">
      <Warning size={16} weight="fill" />
      <div className="alert-items">
        {alerts.map((a) => (
          <span key={a.id} className="alert-item">
            <strong>{a.name}</strong>
            <span className="num">
              mean NDVI {a.mean.toFixed(3)} {a.mode === "above" ? "≥" : "≤"} {a.threshold}
            </span>
            <button className="alert-go" onClick={() => loadRegion(a.geojson, a.name)}>
              Investigate
            </button>
          </span>
        ))}
      </div>
      <button className="alert-close" aria-label="Dismiss alerts"
        onClick={() => { sessionStorage.setItem("cw_alerts_dismissed", "1"); setDismissed(true); }}>
        <X size={14} />
      </button>
    </div>
  );
}
