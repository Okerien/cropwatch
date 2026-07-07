import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Dev proxies /api → Flask backend so the frontend calls same-origin.
// In production, VITE_API_URL points at the Render deployment.
export default defineConfig({
  plugins: [react()],
  build: {
    rollupOptions: {
      output: {
        // Split the heavy, rarely-changing vendor libs so the app chunk stays
        // small and long-term caching works across deploys.
        manualChunks: {
          leaflet: ["leaflet", "react-leaflet"],
          charts: ["recharts"],
          i18n: ["i18next", "react-i18next", "i18next-browser-languagedetector"],
        },
      },
    },
  },
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: process.env.VITE_API_TARGET || "http://localhost:5050",
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/api/, ""),
      },
    },
  },
});
