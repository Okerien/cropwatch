import { useEffect, useRef, useState, useCallback } from "react";
import { Play, Pause } from "@phosphor-icons/react";
import { api } from "../../services/cropwatchApi";
import { useApp } from "../../state/AppContext";

/* 8-day time slider (Feature 3). Pre-fetches the last N composites in the
 * background (the backend caches each, so scrubbing back is instant), then
 * scrub or play the sequence. Frames override the heatmap via onFrame.
 */
const N_FRAMES = 12;               // ~3 months of 8-day composites
const SPEEDS = [
  { label: "0.5×", ms: 2000 }, { label: "1×", ms: 1000 }, { label: "2×", ms: 500 },
];

function compositeWindows(n) {
  // Most recent completed composite ends ~10 days ago (MODIS latency).
  const out = [];
  const end = new Date(); end.setDate(end.getDate() - 10);
  for (let i = n - 1; i >= 0; i--) {
    const e = new Date(end); e.setDate(e.getDate() - i * 8);
    const s = new Date(e); s.setDate(s.getDate() - 7);
    out.push({
      start: s.toISOString().slice(0, 10),
      end: e.toISOString().slice(0, 10),
    });
  }
  return out;
}

export function TimeSlider({ onFrame }) {
  const { region, snapshot } = useApp();
  const [frames, setFrames] = useState([]);      // { window, result }
  const [loaded, setLoaded] = useState(0);
  const [idx, setIdx] = useState(N_FRAMES - 1);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(1);
  const timer = useRef(null);
  const gen = useRef(0);

  // Pre-fetch all composites when the region changes.
  useEffect(() => {
    if (!region?.geojson || snapshot.status !== "ready") return;
    const g = ++gen.current;
    const windows = compositeWindows(N_FRAMES);
    const slots = windows.map((w) => ({ window: w, result: null }));
    setFrames(slots); setLoaded(0); setIdx(N_FRAMES - 1); setPlaying(false);

    (async () => {
      let done = 0;
      // Fetch newest-first so scrubbing near "now" works immediately.
      for (let i = windows.length - 1; i >= 0; i--) {
        if (g !== gen.current) return;
        try {
          const res = await api.ndviAwait(region.geojson, {
            start_date: windows[i].start, end_date: windows[i].end,
          });
          if (g !== gen.current) return;
          slots[i] = { window: windows[i], result: res };
          done += 1;
          setFrames([...slots]); setLoaded(done);
        } catch { /* skip failed frame */ }
      }
    })();
    return () => { gen.current++; };
  }, [region, snapshot.status]); // eslint-disable-line react-hooks/exhaustive-deps

  // Playback loop.
  useEffect(() => {
    if (!playing) { clearInterval(timer.current); return; }
    timer.current = setInterval(() => {
      setIdx((i) => (i + 1) % frames.length);
    }, SPEEDS[speed].ms);
    return () => clearInterval(timer.current);
  }, [playing, speed, frames.length]);

  // Push the active frame up to the map.
  useEffect(() => {
    const f = frames[idx];
    onFrame(f?.result || null);
  }, [idx, frames, onFrame]);

  const scrub = useCallback((e) => {
    setPlaying(false);
    setIdx(Number(e.target.value));
  }, []);

  if (!frames.length || snapshot.status !== "ready") return null;
  const current = frames[idx];
  const allLoaded = loaded >= frames.length;

  return (
    <div className="timeslider panel">
      <button className="ts-play" disabled={!allLoaded}
        onClick={() => setPlaying((p) => !p)}
        title={allLoaded ? "Animate" : `Loading composites… ${loaded}/${frames.length}`}
        aria-label={playing ? "Pause" : "Play"}>
        {playing ? <Pause size={15} weight="fill" /> : <Play size={15} weight="fill" />}
      </button>

      <div className="ts-body">
        <div className="ts-date num">
          {current?.result
            ? current.result.composite.date_label
            : `${current?.window.start} · loading…`}
        </div>
        <input type="range" min={0} max={frames.length - 1} value={idx}
          onChange={scrub} className="ts-range" aria-label="Composite date" />
        <div className="ts-progress">
          {frames.map((f, i) => (
            <span key={i} className={`ts-tick ${f.result ? "ok" : ""} ${i === idx ? "cur" : ""}`} />
          ))}
        </div>
      </div>

      <button className="ts-speed num" onClick={() => setSpeed((s) => (s + 1) % SPEEDS.length)}>
        {SPEEDS[speed].label}
      </button>
    </div>
  );
}
