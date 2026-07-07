import { useTranslation } from "react-i18next";
import { useApp } from "../../state/AppContext";
import { STRESS_ZONES } from "../../lib/ndviColor";
import { WarningCircle } from "@phosphor-icons/react";

export function SummaryPanel() {
  const { t } = useTranslation();
  const { snapshot, region } = useApp();
  const { status, result, error } = snapshot;

  if (status === "error") {
    return (
      <div className="summary panel">
        <div className="summary-error">
          <WarningCircle size={22} color="var(--sev-severe)" weight="fill" />
          <p>{error?.message}</p>
          {error?.hint && <p className="summary-hint">{error.hint}</p>}
        </div>
      </div>
    );
  }
  if (status === "idle" && !region) {
    return (
      <div className="summary panel">
        <p className="summary-empty">{t("summary.pickRegion")}</p>
      </div>
    );
  }
  if (status === "loading" || !result) return <SummarySkeleton />;

  const s = result.stats;
  const sev = s.severity;

  return (
    <div className="summary panel fade-up">
      <div className="summary-head">
        <div className="summary-region">{region?.name}</div>
        <div className="summary-area num">{result.area.area_km2.toLocaleString()} km²</div>
      </div>

      <div className="score-block" style={{ "--sev": sev.colour }}>
        <div className="score-num num">{sev.score}</div>
        <div className="score-side">
          <div className="score-label">{sev.label}</div>
          <div className="score-scale">
            <span style={{ left: `${sev.score}%` }} className="score-marker" />
          </div>
          <div className="score-cap">{t("summary.severity")}</div>
        </div>
      </div>

      <div className="stat-row">
        <Stat label={t("summary.meanNdvi")} value={s.mean?.toFixed(3)} />
        <Stat label={t("summary.median")} value={s.median?.toFixed(3)} />
        <Stat label={t("summary.std")} value={s.std?.toFixed(3)} />
      </div>

      <div className="zones">
        <div className="zones-bar">
          {STRESS_ZONES.map((z) => {
            const pct = s.zones[z.key]?.pct || 0;
            return pct > 0 ? (
              <span key={z.key} style={{ width: `${pct}%`, background: z.color }}
                title={`${z.label}: ${pct}%`} />
            ) : null;
          })}
        </div>
        <ul className="zones-legend">
          {STRESS_ZONES.map((z) => (
            <li key={z.key}>
              <span className="zdot" style={{ background: z.color }} />
              <span className="zlabel">{t(`zones.${z.key}`)}</span>
              <span className="zpct num">{(s.zones[z.key]?.pct || 0).toFixed(1)}%</span>
            </li>
          ))}
        </ul>
      </div>

      {sev.partial && (
        <div className="summary-note">
          Severity is 2-of-3 components until historical baseline loads.
        </div>
      )}
    </div>
  );
}

function Stat({ label, value }) {
  return (
    <div className="stat">
      <div className="stat-val num">{value ?? "—"}</div>
      <div className="stat-lbl">{label}</div>
    </div>
  );
}

function SummarySkeleton() {
  return (
    <div className="summary panel">
      <div className="skeleton" style={{ height: 18, width: "60%", marginBottom: 16 }} />
      <div className="skeleton" style={{ height: 72, marginBottom: 16 }} />
      <div className="skeleton" style={{ height: 40, marginBottom: 16 }} />
      <div className="skeleton" style={{ height: 90 }} />
    </div>
  );
}
