import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    // Stay on localhost so auth cookies from OAuth (AUTH_ORIGIN localhost:8000)
    // are visible to the SPA — 127.0.0.1 is a different cookie host.
    host: "localhost",
    port: 5173,
    proxy: {
      // Proxy target must be 127.0.0.1 — on Windows, Node often resolves
      // "localhost" to ::1 while uvicorn binds 127.0.0.1 only.
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
        // Keep Set-Cookie host-only for the SPA origin (localhost:5173).
        cookieDomainRewrite: "",
      },
    },
  },
});
