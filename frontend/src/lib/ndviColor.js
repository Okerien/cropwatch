/* NDVI + anomaly colour scales — the heart of CropWatch's visual language.
 *
 * The absolute NDVI ramp mirrors the backend's 7-stop USDA-style convention so
 * users of Crop Explorer recognise it instantly. A deuteranopia-safe blue-gold
 * alternative is available. The z-score scale is the diverging blue-white-red
 * anomaly convention used by NOAA CPC / FEWS NET.
 */
import chroma from "chroma-js";

// Absolute NDVI: deep red (0.0) → forest green (0.9+)
const NDVI_STOPS = [
  [0.0, "#8B0000"], [0.1, "#CC4400"], [0.2, "#E8870A"], [0.3, "#F5C842"],
  [0.4, "#A8D26B"], [0.6, "#4CAF50"], [0.9, "#1A5C38"],
];

// Deuteranopia-safe: blue (0.0) → white (0.4) → gold (0.9)
const NDVI_CVD_STOPS = [
  [0.0, "#053061"], [0.4, "#F7F7F7"], [0.9, "#B5851B"],
];

// Anomaly z-score: deep red (−2.5) → white (0) → deep blue (+2.5)
const Z_STOPS = [
  [-2.5, "#B22222"], [-1.5, "#E8730A"], [-0.5, "#F5D9A8"],
  [0.0, "#FAFAFA"], [0.5, "#BBD6F2"], [1.5, "#3B7DD8"], [2.5, "#1A237E"],
];

function buildScale(stops) {
  const domain = stops.map((s) => s[0]);
  const colors = stops.map((s) => s[1]);
  return chroma.scale(colors).domain(domain).mode("lab");
}

const ndviScale = buildScale(NDVI_STOPS);
const ndviCvdScale = buildScale(NDVI_CVD_STOPS);
const zScale = buildScale(Z_STOPS);

/** RGBA byte tuple for an NDVI value; nulls / no-data → transparent. */
export function ndviRGBA(v, cvd = false) {
  if (v == null || Number.isNaN(v) || v < -0.05) return [0, 0, 0, 0];
  const [r, g, b] = (cvd ? ndviCvdScale : ndviScale)(v).rgb();
  return [r | 0, g | 0, b | 0, 255];
}

/** RGBA byte tuple for a z-score anomaly value. */
export function zRGBA(v) {
  if (v == null || Number.isNaN(v)) return [0, 0, 0, 0];
  const [r, g, b] = zScale(v).rgb();
  return [r | 0, g | 0, b | 0, 255];
}

export function ndviHex(v, cvd = false) {
  if (v == null || Number.isNaN(v)) return "transparent";
  return (cvd ? ndviCvdScale : ndviScale)(v).hex();
}
export function zHex(v) {
  if (v == null || Number.isNaN(v)) return "transparent";
  return zScale(v).hex();
}

/** Legend stops (value + hex) for the colour bar component. */
export function ndviLegend(cvd = false) {
  const scale = cvd ? ndviCvdScale : ndviScale;
  return Array.from({ length: 11 }, (_, i) => {
    const v = i / 10;
    return { value: v, hex: scale(v).hex() };
  });
}
export function zLegend() {
  return [-2.5, -2, -1.5, -1, -0.5, 0, 0.5, 1, 1.5, 2, 2.5].map((v) => ({
    value: v, hex: zScale(v).hex(),
  }));
}

/** Five stress zones — names, ranges, colours (matches backend). */
export const STRESS_ZONES = [
  { key: "severe", label: "Severe", range: [0.0, 0.2], color: "#8B0000" },
  { key: "moderate", label: "Moderate", range: [0.2, 0.4], color: "#E8870A" },
  { key: "mild", label: "Mild", range: [0.4, 0.5], color: "#F5C842" },
  { key: "healthy", label: "Healthy", range: [0.5, 0.7], color: "#4CAF50" },
  { key: "dense_healthy", label: "Dense", range: [0.7, 1.0], color: "#1A5C38" },
];

export function classifyNDVI(v) {
  if (v == null) return null;
  for (const z of STRESS_ZONES) if (v >= z.range[0] && v < z.range[1]) return z;
  return STRESS_ZONES[STRESS_ZONES.length - 1];
}
