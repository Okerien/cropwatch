import { useState } from "react";
import { Sparkle, PencilSimple, Check } from "@phosphor-icons/react";
import { api } from "../../services/cropwatchApi";
import { useApp } from "../../state/AppContext";
import "./report.css";

const AUDIENCES = ["Farmer", "Trader", "NGO/Government", "Researcher"];
const LANGS = [
  { code: "en", label: "English" },
  { code: "fr", label: "Français" },
  { code: "sw", label: "Kiswahili" },
];

/** Feature 13: one button → professional two-paragraph field report.
 *  The edited text is what the PDF export embeds (reportText is lifted up). */
export function ReportPanel({ reportText, setReportText }) {
  const { region, snapshot, historical } = useApp();
  const [audience, setAudience] = useState("Farmer");
  const [lang, setLang] = useState("en");
  const [busy, setBusy] = useState(false);
  const [meta, setMeta] = useState(null);
  const [editing, setEditing] = useState(false);
  const [error, setError] = useState(null);

  const stats = snapshot.result?.stats;
  const ready = snapshot.status === "ready" && stats;

  const generate = async () => {
    setBusy(true); setError(null);
    try {
      // Reports are 10× more useful with historical context — fetch it inline
      // if the user hasn't visited Historical mode yet (server caches it).
      let h = historical.result;
      if (!h && region?.geojson) {
        try { h = await api.historical(region.geojson, { years: 20 }); } catch { /* optional */ }
      }
      const payload = {
        region_name: region?.name,
        date_label: snapshot.result?.composite?.date_label,
        mean_ndvi: stats?.mean,
        severity: stats?.severity,
        mean_z: h?.mean_z ?? null,
        analogue_years: h?.analogue_years?.map((a) => ({
          year: a.year, yield_deviation_pct: a.yield_deviation_pct,
        })),
        audience, language: lang,
      };
      const res = await api.report(payload);
      setReportText(res.report);
      setMeta({ source: res.source, note: res.note });
      setEditing(false);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="report panel">
      <div className="report-head">
        <span className="rail-title eyebrow" style={{ marginBottom: 0 }}>Field report</span>
        {reportText && (
          <button className="wbtn" title={editing ? "Done" : "Edit"}
            onClick={() => setEditing(!editing)}>
            {editing ? <Check size={14} /> : <PencilSimple size={14} />}
          </button>
        )}
      </div>

      <div className="report-controls">
        <select value={audience} onChange={(e) => setAudience(e.target.value)}
          aria-label="Audience">
          {AUDIENCES.map((a) => <option key={a}>{a}</option>)}
        </select>
        <select value={lang} onChange={(e) => setLang(e.target.value)} aria-label="Language">
          {LANGS.map((l) => <option key={l.code} value={l.code}>{l.label}</option>)}
        </select>
        <button className="btn btn-accent report-gen" disabled={!ready || busy} onClick={generate}>
          <Sparkle size={14} weight="fill" />
          {busy ? "Writing…" : reportText ? "Regenerate" : "Generate"}
        </button>
      </div>

      {error && <p className="report-err">{error}</p>}

      {reportText && !editing && (
        <div className="report-text fade-up">
          {reportText.split("\n\n").map((p, i) => <p key={i}>{p}</p>)}
        </div>
      )}
      {reportText && editing && (
        <textarea className="report-edit" rows={9} value={reportText}
          onChange={(e) => setReportText(e.target.value)} />
      )}

      {meta?.note && <div className="report-note">{meta.note}</div>}
    </div>
  );
}
