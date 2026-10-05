import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig(({ mode }) => {
  // Empty prefix: read YOUGENE_API_PORT from the process environment too.
  const env = loadEnv(mode, ".", "");
  return {
    plugins: [react(), tailwindcss()],
    server: {
      host: "127.0.0.1",
      port: 5180,
      strictPort: true,
      allowedHosts: ["yougene.gen"],
      proxy: {
        "/api": {
          target: `http://127.0.0.1:${env.YOUGENE_API_PORT || "8765"}`,
          changeOrigin: true,
        },
      },
    },
    preview: { host: "127.0.0.1" },
  };
});
