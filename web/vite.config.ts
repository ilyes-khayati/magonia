import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// During development, /api/... is forwarded to the FastAPI server.
export default defineConfig({
  plugins: [react()],
  // MapLibre loads its worker by relative URL, which pre-bundling breaks
  optimizeDeps: { exclude: ["maplibre-gl"] },
  server: {
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
});
