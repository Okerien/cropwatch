import { Popup } from "react-leaflet";
import { ndviHex } from "../../lib/ndviColor";

/** Click-to-inspect popup: NDVI value, classification, coordinates, date. */
export function InspectPopup({ inspect, composite }) {
  const { lat, lon, ndvi, zone } = inspect;
  return (
    <Popup position={[lat, lon]} className="cw-popup">
      <div className="inspect">
        <div className="inspect-ndvi">
          <span className="inspect-swatch" style={{ background: ndviHex(ndvi) }} />
          <span className="num inspect-val">{ndvi.toFixed(3)}</span>
        </div>
        <div className="inspect-zone" style={{ color: zone?.color }}>
          {zone?.label} vegetation
        </div>
        <dl className="inspect-meta">
          <div><dt>Lat</dt><dd className="num">{lat.toFixed(4)}</dd></div>
          <div><dt>Lon</dt><dd className="num">{lon.toFixed(4)}</dd></div>
          {composite && <div><dt>Composite</dt><dd>{composite.date_label}</dd></div>}
        </dl>
      </div>
    </Popup>
  );
}
