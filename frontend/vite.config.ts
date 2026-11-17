import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// Rutas de la API de Python. En desarrollo el servidor de Vite las reenvía a `brain serve`
// (así no hace falta CORS); en producción las sirve la propia API junto con los estáticos.
const API = "http://127.0.0.1:8000";
const apiPaths = ["/health", "/stats", "/search", "/ask", "/notes", "/graph", "/reindex"];

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    host: "127.0.0.1",
    port: 5173,
    proxy: Object.fromEntries(apiPaths.map((p) => [p, { target: API, changeOrigin: false }])),
  },
  build: { outDir: "dist", sourcemap: false },
  test: {
    environment: "jsdom",
    globals: false,
    setupFiles: ["./src/test/setup.ts"],
    css: false,
    restoreMocks: true,
  },
});
