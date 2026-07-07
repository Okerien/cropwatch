import { useTranslation } from "react-i18next";
import { useApp } from "../state/AppContext";
import { Leaf, Eye, Circle, Translate } from "@phosphor-icons/react";

const MODES = ["snapshot", "trend", "historical"];
const LANGS = [{ code: "en", label: "EN" }, { code: "fr", label: "FR" }, { code: "sw", label: "SW" }];

export function TopBar() {
  const { t, i18n } = useTranslation();
  const { mode, setMode, view, setView, palette, setPalette, snapshot } = useApp();
  const composite = snapshot.result?.composite;
  const source = snapshot.result?.source;

  return (
    <header className="topbar">
      <div className="brand">
        <Leaf size={20} weight="fill" color="var(--accent)" />
        <span className="brand-name">CropWatch</span>
        <span className="brand-sub">satellite crop stress</span>
      </div>

      <nav className="mode-switch" role="tablist" aria-label="Analysis mode">
        {MODES.map((m) => (
          <button key={m} role="tab" aria-selected={mode === m}
            className={`mode-btn ${mode === m ? "on" : ""}`}
            onClick={() => setMode(m)}>
            {t(`mode.${m}`)}
          </button>
        ))}
      </nav>

      <div className="topbar-right">
        <button className="seg" onClick={() => setView(view === "absolute" ? "anomaly" : "absolute")}
          title="Toggle absolute NDVI / anomaly view">
          <Eye size={15} weight="bold" />
          {view === "absolute" ? t("view.absolute") : t("view.anomaly")}
        </button>
        <button className={`seg ${palette === "cvd" ? "on" : ""}`}
          onClick={() => setPalette(palette === "cvd" ? "normal" : "cvd")}
          title="Colour-blind safe palette">
          <Circle size={15} weight={palette === "cvd" ? "fill" : "regular"} />
          CVD
        </button>
        <div className="lang-switch" title="Language">
          <Translate size={14} />
          {LANGS.map((l) => (
            <button key={l.code} className={i18n.language?.startsWith(l.code) ? "on" : ""}
              onClick={() => i18n.changeLanguage(l.code)}>{l.label}</button>
          ))}
        </div>
        {composite && (
          <div className="currency" title="Most recent composite">
            <span className="currency-dot" data-source={source} />
            <span className="num">{composite.date_label}</span>
            <span className="currency-age">{composite.age_days}d old</span>
          </div>
        )}
      </div>
    </header>
  );
}
