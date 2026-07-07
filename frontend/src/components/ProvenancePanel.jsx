import { useState } from "react";
import { Info, X, Copy } from "@phosphor-icons/react";
import { useApp } from "../state/AppContext";
import "./provenance.css";

const DATASETS = [
  {
    name: "MODIS MOD13Q1 / MYD13Q1 — Vegetation Indices",
    institution: "NASA LP DAAC (Terra & Aqua)",
    url: "https://doi.org/10.5067/MODIS/MOD13Q1.061",
    resolution: "250 m", cadence: "8-day composite", range: "2000–present",
    note: "NDVI compositing selects the best observation in each 8-day window to reduce cloud contamination, but persistent wet-season cloud can still depress values. Values near 0 may be bare soil OR sparse vegetation — verify in the field before reading as crop failure. Each 250 m pixel is a mixed measurement over heterogeneous ground.",
    citation: "Didan, K. (2015). MOD13Q1 MODIS/Terra Vegetation Indices 16-Day L3 Global 250m SIN Grid V061. NASA EOSDIS Land Processes DAAC.",
  },
  {
    name: "CHIRPS — Rainfall",
    institution: "UCSB Climate Hazards Group & USGS EROS",
    url: "https://www.chc.ucsb.edu/data/chirps",
    resolution: "0.05° (~5.5 km)", cadence: "daily → aggregated", range: "1981–present",
    note: "Blends satellite estimates with ground-station data. Anomaly is expressed as a percentage of the 1981–present calendar-period average.",
    citation: "Funk, C. et al. (2015). The climate hazards infrared precipitation with stations. Scientific Data 2, 150066.",
  },
  {
    name: "FAOSTAT — Crop Yields",
    institution: "Food and Agriculture Organization",
    url: "https://www.fao.org/faostat",
    resolution: "country level", cadence: "annual", range: "1961–present",
    note: "Country-level reported yields used for analogue-year context. Not sub-national — treat as regional signal, not field-level truth.",
    citation: "FAO (2024). FAOSTAT Crops and livestock products. Food and Agriculture Organization of the United Nations.",
  },
  {
    name: "ESA WorldCover — Land Cover",
    institution: "European Space Agency",
    url: "https://esa-worldcover.org",
    resolution: "10 m → 250 m", cadence: "static (2021)", range: "2021",
    note: "Used for dominant-crop context. Static snapshot; does not reflect current-year planting decisions or rotation.",
    citation: "Zanaga, D. et al. (2022). ESA WorldCover 10 m 2021 v200.",
  },
];

export function ProvenancePanel() {
  const [open, setOpen] = useState(false);
  const { snapshot } = useApp();
  const composite = snapshot.result?.composite;
  const source = snapshot.result?.source;

  return (
    <>
      <button className="prov-fab" title="Data sources & limitations" onClick={() => setOpen(true)}>
        <Info size={16} weight="fill" />
      </button>

      {open && (
        <div className="prov-overlay" onClick={() => setOpen(false)}>
          <div className="prov-modal panel" onClick={(e) => e.stopPropagation()}>
            <div className="prov-head">
              <div>
                <h2>Data provenance & limitations</h2>
                <p className="prov-sub">Every number in CropWatch comes from free, public scientific infrastructure. Nothing is proprietary or synthesised{source === "demo" ? " — except this demo instance, which serves synthetic-but-plausible data (no NASA credentials configured)." : "."}</p>
              </div>
              <button className="prov-close" onClick={() => setOpen(false)} aria-label="Close"><X size={16} /></button>
            </div>

            {composite && (
              <div className="prov-currency">
                <span className="prov-dot" data-source={source} />
                Most recent NDVI composite: <strong>{composite.date_label}</strong> ({composite.age_days} days old) ·
                Historical baseline: 2001–present
              </div>
            )}

            <div className="prov-list">
              {DATASETS.map((d) => (
                <div key={d.name} className="prov-item">
                  <div className="prov-item-head">
                    <h3>{d.name}</h3>
                    <a href={d.url} target="_blank" rel="noreferrer">{d.institution}</a>
                  </div>
                  <div className="prov-specs">
                    <span>Resolution <b>{d.resolution}</b></span>
                    <span>Cadence <b>{d.cadence}</b></span>
                    <span>Record <b>{d.range}</b></span>
                  </div>
                  <p className="prov-note">{d.note}</p>
                  <button className="prov-cite" onClick={() => navigator.clipboard?.writeText(d.citation)}>
                    <Copy size={12} /> Copy citation
                  </button>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </>
  );
}
