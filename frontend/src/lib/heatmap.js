/* Rasterise an NDVI (or z-score) grid into a data-URL image for Leaflet.
 *
 * We render the grid at native resolution (one canvas pixel per MODIS pixel)
 * and let Leaflet's ImageOverlay scale it with `image-rendering: pixelated`,
 * so zoom/pan is handled by the map with no data re-fetch — smooth even on
 * modest hardware, exactly the Feature 1 brief.
 */
import { ndviRGBA, zRGBA } from "./ndviColor";

/**
 * @param grid  { rows, cols, bbox:[minLon,minLat,maxLon,maxLat] }
 * @param values flat row-major array (NDVI or z-score), north-to-south rows
 * @param opts  { mode: "absolute"|"anomaly", cvd: boolean }
 * @returns { url, bounds } bounds = [[south,west],[north,east]] for Leaflet
 */
export function gridToImage(grid, values, { mode = "absolute", cvd = false } = {}) {
  const { rows, cols, bbox } = grid;
  const canvas = document.createElement("canvas");
  canvas.width = cols;
  canvas.height = rows;
  const ctx = canvas.getContext("2d");
  const img = ctx.createImageData(cols, rows);

  const encode = mode === "anomaly" ? (v) => zRGBA(v) : (v) => ndviRGBA(v, cvd);
  for (let i = 0; i < values.length; i++) {
    const [r, g, b, a] = encode(values[i]);
    const o = i * 4;
    img.data[o] = r; img.data[o + 1] = g; img.data[o + 2] = b; img.data[o + 3] = a;
  }
  ctx.putImageData(img, 0, 0);

  const [minLon, minLat, maxLon, maxLat] = bbox;
  return {
    url: canvas.toDataURL("image/png"),
    bounds: [[minLat, minLon], [maxLat, maxLon]],
  };
}

/** Read the grid value under a lat/lon (for click-to-inspect). */
export function sampleGrid(grid, values, lat, lon) {
  const { rows, cols, bbox } = grid;
  const [minLon, minLat, maxLon, maxLat] = bbox;
  if (lon < minLon || lon > maxLon || lat < minLat || lat > maxLat) return null;
  const col = Math.min(cols - 1, Math.floor(((lon - minLon) / (maxLon - minLon)) * cols));
  // Row 0 is north (maxLat), so invert the latitude fraction.
  const row = Math.min(rows - 1, Math.floor(((maxLat - lat) / (maxLat - minLat)) * rows));
  return values[row * cols + col];
}
