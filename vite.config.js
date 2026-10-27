import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ mode }) => ({
  plugins: [react()],
  base: mode === "production" ? "/static/dist/" : "/",
  server: {
    host: "127.0.0.1",
    proxy: {
      "/api": process.env.VITE_BACKEND_URL || "http://127.0.0.1:5000",
      "/login": process.env.VITE_BACKEND_URL || "http://127.0.0.1:5000",
      "/register": process.env.VITE_BACKEND_URL || "http://127.0.0.1:5000",
      "/logout": process.env.VITE_BACKEND_URL || "http://127.0.0.1:5000",
      "/sales": process.env.VITE_BACKEND_URL || "http://127.0.0.1:5000",
      "/settings": process.env.VITE_BACKEND_URL || "http://127.0.0.1:5000",
      "/inventory": process.env.VITE_BACKEND_URL || "http://127.0.0.1:5000",
    },
  },
  build: {
    outDir: "static/dist",
    emptyOutDir: true,
    rollupOptions: {
      input: "index.html",
      output: {
        entryFileNames: "app.js",
        chunkFileNames: "chunks/[name].js",
        assetFileNames: (asset) =>
          asset.name && asset.name.endsWith(".css") ? "app.css" : "assets/[name][extname]",
      },
    },
  },
}));
