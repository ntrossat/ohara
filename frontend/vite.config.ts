import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  // Relative asset paths, so Ohara works under any base path. The server sets the page's paths.
  base: "./",
  plugins: [react()],
  server: { proxy: { "/api": "http://localhost:8000" } },
});
