import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  server: {
    // Les appels à /api/... sont relayés vers l'API FastAPI (sans le préfixe /api).
    // Même origine pour le navigateur : pas de configuration CORS côté backend.
    proxy: {
      "/api": {
        // RUGBY_API_URL permet de viser une autre API (ex. une instance de test).
        target: process.env.RUGBY_API_URL ?? "http://localhost:8000",
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
});
