/* Shared Recharts styling for the dark instrument theme. */
export const AXIS = {
  stroke: "#2a3644",
  tick: { fill: "#7d8b9c", fontSize: 10.5, fontFamily: "Geist Mono, monospace" },
  tickLine: false,
  axisLine: { stroke: "#1e2733" },
};

export const GRID = { stroke: "#161e28", strokeDasharray: "3 3", vertical: false };

export const THRESHOLDS = [
  { y: 0.2, label: "severe", color: "#8B0000" },
  { y: 0.4, label: "moderate", color: "#E8870A" },
  { y: 0.5, label: "mild", color: "#F5C842" },
  { y: 0.7, label: "healthy", color: "#4CAF50" },
];

export function fmtDate(iso, range) {
  const d = new Date(iso);
  if (range === "5y") return d.toLocaleDateString("en-GB", { month: "short", year: "2-digit" });
  return d.toLocaleDateString("en-GB", { day: "numeric", month: "short" });
}
