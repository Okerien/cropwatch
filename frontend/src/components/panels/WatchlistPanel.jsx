import { useEffect, useRef, useState } from "react";
import {
  Star, Trash, BellRinging, NotePencil, DownloadSimple, UploadSimple, Plus,
} from "@phosphor-icons/react";
import { useApp } from "../../state/AppContext";
import { exportWorkspace, importWorkspace, loadRegions } from "../../lib/watchlist";
import "./watchlist.css";

export function WatchlistPanel() {
  const { watchlist, regionStatus, region, snapshot, dispatch,
          saveRegion, patchRegion, deleteRegion, refreshWatchlistStatus, loadRegion } = useApp();
  const [expanded, setExpanded] = useState(null);   // region id with open editor
  const fileRef = useRef();

  // Background severity + alert pass on mount and when the list membership changes.
  useEffect(() => {
    if (watchlist.length) refreshWatchlistStatus(watchlist);
  }, [watchlist.length]); // eslint-disable-line react-hooks/exhaustive-deps

  const canSave = region?.geojson && snapshot.status === "ready" &&
    !watchlist.some((r) => r.name === region.name);

  return (
    <div className="rail-card panel watch">
      <div className="watch-head">
        <span className="rail-title eyebrow" style={{ marginBottom: 0 }}>Watchlist</span>
        <div className="watch-tools">
          <button title="Export all regions (GeoJSON)" onClick={exportWorkspace}
            disabled={!watchlist.length}><DownloadSimple size={14} /></button>
          <button title="Import regions" onClick={() => fileRef.current?.click()}>
            <UploadSimple size={14} />
          </button>
          <input ref={fileRef} type="file" accept=".geojson,.json" hidden
            onChange={async (e) => {
              const f = e.target.files?.[0];
              if (!f) return;
              try {
                dispatch({ type: "WATCHLIST", list: importWorkspace(await f.text()) });
              } catch (err) { alert(err.message); }
              e.target.value = "";
            }} />
        </div>
      </div>

      {canSave && (
        <button className="watch-save btn" onClick={() => saveRegion(region.name, region.geojson)}>
          <Plus size={14} weight="bold" /> Save {region.name}
        </button>
      )}

      {!watchlist.length && !canSave && (
        <p className="watch-empty">Saved regions appear here with live status dots.</p>
      )}

      <ul className="watch-list">
        {watchlist.map((r) => (
          <WatchCard key={r.id} r={r} status={regionStatus[r.id]}
            active={region?.name === r.name}
            expanded={expanded === r.id}
            onExpand={() => setExpanded(expanded === r.id ? null : r.id)}
            onLoad={() => loadRegion(r.geojson, r.name)}
            onPatch={(p) => patchRegion(r.id, p)}
            onDelete={() => { deleteRegion(r.id); if (expanded === r.id) setExpanded(null); }} />
        ))}
      </ul>
    </div>
  );
}

function WatchCard({ r, status, active, expanded, onExpand, onLoad, onPatch, onDelete }) {
  return (
    <li className={`wcard ${active ? "active" : ""}`}>
      <div className="wcard-row">
        <button className="wcard-main" onClick={onLoad} title="Load this region">
          <span className="wdot" style={{ background: status?.colour || "var(--line-strong)" }} />
          <span className="wname">{r.name}</span>
          {status && <span className="wscore num">{status.score}</span>}
        </button>
        <button className={`wbtn ${r.starred ? "starred" : ""}`}
          title="Compare on trend chart"
          onClick={() => onPatch({ starred: !r.starred })}>
          <Star size={14} weight={r.starred ? "fill" : "regular"} />
        </button>
        <button className={`wbtn ${r.threshold != null ? "alerting" : ""}`}
          title="Alert threshold" onClick={onExpand}>
          <BellRinging size={14} weight={r.threshold != null ? "fill" : "regular"} />
        </button>
        <button className="wbtn" title="Note & tags" onClick={onExpand}>
          <NotePencil size={14} />
        </button>
        <button className="wbtn danger" title="Remove" onClick={onDelete}>
          <Trash size={14} />
        </button>
      </div>

      {r.tags?.length > 0 && (
        <div className="wtags">{r.tags.map((t) => <span key={t} className="chip">{t}</span>)}</div>
      )}

      {expanded && <WatchEditor r={r} status={status} onPatch={onPatch} />}
    </li>
  );
}

function WatchEditor({ r, status, onPatch }) {
  const [note, setNote] = useState(r.note || "");
  const [tagText, setTagText] = useState((r.tags || []).join(", "));
  const [thr, setThr] = useState(r.threshold ?? 0.4);
  const [thrOn, setThrOn] = useState(r.threshold != null);
  const [mode, setMode] = useState(r.thresholdMode || "below");

  const apply = () => {
    onPatch({
      note,
      tags: tagText.split(",").map((t) => t.trim()).filter(Boolean),
      threshold: thrOn ? Number(thr) : null,
      thresholdMode: mode,
    });
  };

  return (
    <div className="weditor" onBlur={apply}>
      <label className="wlabel">
        <input type="checkbox" checked={thrOn} onChange={(e) => { setThrOn(e.target.checked); }} />
        Alert when mean NDVI {mode === "below" ? "falls below" : "rises above"}
        <input className="wthr num" type="number" min="0" max="1" step="0.05"
          value={thr} disabled={!thrOn}
          onChange={(e) => setThr(e.target.value)} />
        <button className="wmode num" type="button"
          onClick={() => setMode(mode === "below" ? "above" : "below")}>
          {mode === "below" ? "↓" : "↑"}
        </button>
      </label>
      {status?.mean != null && (
        <div className="wnow num">current mean: {status.mean.toFixed(3)}</div>
      )}
      <div className="wnote-head">
        <button className="wdated" type="button"
          title="Prepend a dated log entry"
          onClick={() => setNote((n) => `[${new Date().toISOString().slice(0, 10)}] \n${n}`.slice(0, 500))}>
          + dated entry
        </button>
      </div>
      <textarea className="wnote" rows={3} placeholder="Field log (up to 500 chars)…"
        maxLength={500} value={note} onChange={(e) => setNote(e.target.value)} />
      <input className="wtags-in" placeholder="tags, comma separated"
        value={tagText} onChange={(e) => setTagText(e.target.value)} />
      <button className="btn btn-accent wapply" type="button" onClick={apply}>Apply</button>
    </div>
  );
}
