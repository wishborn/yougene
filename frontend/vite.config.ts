import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// FastAPI renders every page (Inertia) and serves /api. In development Vite
// fronts the site: it serves its own module paths and proxies everything else
// to FastAPI, so pages, API and HMR share one origin (needed for yougene.gen).

export default defineConfig(({ mode }) => {
  // Empty prefix: read YOUGENE_API_PORT from the process environment too.
  const env = loadEnv(mode, ".", "");
  const api = `http://127.0.0.1:${env.YOUGENE_API_PORT || "8765"}`;
  return {
    plugins: [react(), tailwindcss()],
    base: mode === "production" ? "/build/" : "/",
    build: {
      manifest: true,
      outDir: "dist",
      rollupOptions: { input: "src/main.tsx" },
    },
    server: {
      host: "127.0.0.1",
      port: 5180,
      strictPort: true,
      allowedHosts: ["yougene.gen"],
      proxy: {
        // Anything that isn't one of Vite's own paths goes to FastAPI.
        "^(?!/(@vite|@react-refresh|@id|@fs|src/|node_modules/|\\.vite/)).*": {
          target: api,
          changeOrigin: true,
        },
      },
    },
    preview: { host: "127.0.0.1" },
  };
});

