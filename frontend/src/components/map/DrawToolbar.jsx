import { useEffect, useState } from "react";
import { ArrowCounterClockwise, Check, X } from "@phosphor-icons/react";
import { useApp } from "../../state/AppContext";

/** Floating toolbar shown while polygon-drawing — Undo / Finish / Cancel.
 *  Touch users have no double-click; this is their way to close the shape.
 *  Lives outside the Leaflet tree and talks to PolyDraw over window events. */
export function DrawToolbar() {
  const { drawMode, setDrawMode } = useApp();
  const [points, setPoints] = useState(0);

  useEffect(() => {
    const onPts = (e) => setPoints(e.detail);
    window.addEventListener("cw-draw-points", onPts);
    return () => window.removeEventListener("cw-draw-points", onPts);
  }, []);

  useEffect(() => { if (!drawMode) setPoints(0); }, [drawMode]);

  if (drawMode !== "poly") return null;

  return (
    <div className="draw-toolbar panel">
      <span className="draw-count num">{points} pts</span>
      <button className="dtb" disabled={points === 0}
        onClick={() => window.dispatchEvent(new Event("cw-draw-undo"))}>
        <ArrowCounterClockwise size={14} /> Undo
      </button>
      <button className="dtb dtb-ok" disabled={points < 3}
        onClick={() => window.dispatchEvent(new Event("cw-draw-finish"))}>
        <Check size={14} weight="bold" /> Finish
      </button>
      <button className="dtb dtb-x" onClick={() => setDrawMode(null)}>
        <X size={14} /> Cancel
      </button>
    </div>
  );
}
