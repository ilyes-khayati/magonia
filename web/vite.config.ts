import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// During development, /api/... is forwarded to the FastAPI server (MAGONIA_API names another,
// e.g. a second checkout's on another port).
export default defineConfig({
  plugins: [react()],
  // MapLibre loads its worker by relative URL, which pre-bundling breaks
  optimizeDeps: { exclude: ["maplibre-gl"] },
  server: {
    proxy: {
      "/api": {
        target: process.env.MAGONIA_API ?? "http://127.0.0.1:8000",
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
});
