import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const backendTarget = env.VITE_BACKEND_TARGET || "http://127.0.0.1:8000";
  console.info(`[vite] API proxy target: ${backendTarget}`);

  return {
    plugins: [react()],
    base: "./",
    server: {
      port: 3000,
      proxy: {
        "/api": {
          target: backendTarget,
          changeOrigin: true,
        },
      },
    },
  };
});
