import { useState, useRef, useEffect } from "react";
import { MagnifyingGlass, MapPin, Plant } from "@phosphor-icons/react";
import { api } from "../../services/cropwatchApi";
import { useApp } from "../../state/AppContext";

const PRESETS = [
  { name: "Kano, Nigeria", geojson: rect(8.2, 11.6, 8.9, 12.3) },
  { name: "US Corn Belt", geojson: rect(-94.5, 40.2, -92.0, 42.2) },
  { name: "Ethiopian Highlands", geojson: rect(37.5, 8.5, 39.5, 10.5) },
  { name: "SA Highveld", geojson: rect(26.0, -27.5, 28.5, -25.8) },
];

function rect(w, s, e, n) {
  return { type: "Polygon", coordinates: [[[w, s], [e, s], [e, n], [w, n], [w, s]]] };
}

export function RegionSearch() {
  const { loadRegion, region } = useApp();
  const [q, setQ] = useState("");
  const [suggestions, setSuggestions] = useState([]);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const debounce = useRef();

  useEffect(() => {
    clearTimeout(debounce.current);
    if (q.trim().length < 2) { setSuggestions([]); return; }
    debounce.current = setTimeout(async () => {
      setLoading(true);
      try {
        const res = await api.geocode(q, 8);
        setSuggestions(res.suggestions.filter((s) => s.geometry));
        setOpen(true);
      } catch { /* ignore */ } finally { setLoading(false); }
    }, 300);
    return () => clearTimeout(debounce.current);
  }, [q]);

  const pick = (name, geojson) => {
    setQ(name); setOpen(false); setSuggestions([]);
    loadRegion(geojson, name);
  };

  return (
    <div className="region-search">
      <div className="search-field">
        <MagnifyingGlass size={16} color="var(--text-dim)" />
        <input
          value={q} onChange={(e) => setQ(e.target.value)}
          onFocus={() => suggestions.length && setOpen(true)}
          placeholder="Search a place or farming zone…"
          aria-label="Search region"
        />
        {loading && <span className="search-spin" />}
      </div>

      {open && suggestions.length > 0 && (
        <ul className="suggest" role="listbox">
          {suggestions.map((s, i) => (
            <li key={i} role="option" onClick={() => pick(s.name, s.geometry)}>
              {s.type === "agri_zone"
                ? <Plant size={15} weight="fill" color="var(--sev-mild)" />
                : <MapPin size={15} color="var(--text-dim)" />}
              <span className="suggest-name">{s.name}</span>
              <span className="suggest-meta">{s.country || s.admin_level}</span>
            </li>
          ))}
        </ul>
      )}

      <div className="presets">
        {PRESETS.map((p) => (
          <button key={p.name}
            className={`preset ${region?.name === p.name ? "on" : ""}`}
            onClick={() => pick(p.name, p.geojson)}>
            {p.name}
          </button>
        ))}
      </div>
    </div>
  );
}
