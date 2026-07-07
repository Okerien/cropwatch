import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Stack, X, CaretUp, CaretDown } from "@phosphor-icons/react";
import { TopBar } from "./components/TopBar";
import { MapPanel } from "./components/map/MapPanel";
import { AreaTools } from "./components/controls/AreaTools";
import { SummaryPanel } from "./components/panels/SummaryPanel";
import { HistoricalPanel } from "./components/panels/HistoricalPanel";
import { WatchlistPanel } from "./components/panels/WatchlistPanel";
import { ReportPanel } from "./components/panels/ReportPanel";
import { ExportBar } from "./components/panels/ExportBar";
import { AlertBanner } from "./components/AlertBanner";
import { ProvenancePanel } from "./components/ProvenancePanel";
import { TrendPanel } from "./components/charts/TrendPanel";
import { useApp } from "./state/AppContext";
import "./App.css";

function useIsMobile() {
  const [mobile, setMobile] = useState(
    () => window.matchMedia("(max-width: 820px)").matches);
  useEffect(() => {
    const mq = window.matchMedia("(max-width: 820px)");
    const fn = (e) => setMobile(e.matches);
    mq.addEventListener("change", fn);
    return () => mq.removeEventListener("change", fn);
  }, []);
  return mobile;
}

export default function App() {
  const { t } = useTranslation();
  const { loadRegion, region, mode, snapshot } = useApp();
  const [reportText, setReportText] = useState("");
  const isMobile = useIsMobile();
  const [sheetOpen, setSheetOpen] = useState(false);    // area tools + watchlist
  const [drawerOpen, setDrawerOpen] = useState(false);  // summary drawer

  // A new region invalidates the drafted report; close the mobile sheet too.
  useEffect(() => { setReportText(""); setSheetOpen(false); }, [region?.name]);

  // First impression: land on a real region so the map is alive immediately.
  useEffect(() => {
    if (!region) {
      loadRegion(
        { type: "Polygon", coordinates: [[[8.2, 11.6], [8.9, 11.6], [8.9, 12.3], [8.2, 12.3], [8.2, 11.6]]] },
        "Kano, Nigeria"
      );
    }
  }, [loadRegion, region]);

  const rightRail = (
    <>
      {mode === "historical" ? <HistoricalPanel /> : <SummaryPanel />}
      <ExportBar reportText={reportText} />
      <ReportPanel reportText={reportText} setReportText={setReportText} />
    </>
  );
  const leftRail = (
    <>
      <div className="rail-card panel">
        <div className="rail-title eyebrow">{t("area.title")}</div>
        <AreaTools />
      </div>
      <WatchlistPanel />
    </>
  );

  const sev = snapshot.result?.stats?.severity;

  return (
    <div className="app">
      <TopBar />
      <AlertBanner />
      <div className="stage">
        <MapPanel />

        {!isMobile && <aside className="rail rail-left">{leftRail}</aside>}
        {!isMobile && <aside className="rail rail-right">{rightRail}</aside>}
        {mode === "trend" && <TrendPanel />}
        <ProvenancePanel />

        {isMobile && (
          <>
            <button className="m-fab" aria-label="Regions & search"
              onClick={() => setSheetOpen(true)}>
              <Stack size={20} weight="fill" />
            </button>

            {sheetOpen && (
              <div className="m-sheet-veil" onClick={() => setSheetOpen(false)}>
                <div className="m-sheet fade-up" onClick={(e) => e.stopPropagation()}>
                  <button className="m-sheet-close" aria-label="Close"
                    onClick={() => setSheetOpen(false)}><X size={16} /></button>
                  {leftRail}
                </div>
              </div>
            )}

            <div className={`m-drawer ${drawerOpen ? "open" : ""}`}>
              <button className="m-drawer-handle" aria-expanded={drawerOpen}
                onClick={() => setDrawerOpen(!drawerOpen)}>
                {sev && <span className="m-drawer-score num" style={{ color: sev.colour }}>{sev.score}</span>}
                <span className="m-drawer-name">{region?.name || "CropWatch"}</span>
                {drawerOpen ? <CaretDown size={16} /> : <CaretUp size={16} />}
              </button>
              {drawerOpen && <div className="m-drawer-body">{rightRail}</div>}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
