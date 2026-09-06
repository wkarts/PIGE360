import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";

const configuredPort = Number(process.env.VITE_DEV_PORT || process.env.PIGE360_DEPLOYER_WEB_PORT || process.env.PORT || 61002);
const configuredHost = process.env.TAURI_DEV_HOST || process.env.VITE_DEV_HOST || process.env.PIGE360_DEPLOYER_WEB_HOST || "127.0.0.1";
const internalApiTarget = process.env.VITE_API_PROXY_TARGET || process.env.PIGE360_DEPLOYER_API_BASE_URL || "http://127.0.0.1:61001";

export default defineConfig({
  base: "./",
  plugins: [vue()],
  build: {
    minify: false,
    cssMinify: false,
    sourcemap: true,
    assetsInlineLimit: 0,
  },
  server: {
    host: configuredHost,
    port: Number.isFinite(configuredPort) ? configuredPort : 61002,
    strictPort: false,
    proxy: {
      "/__internal_api": {
        target: internalApiTarget,
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/__internal_api/, ""),
      },
    },
  },
  preview: {
    host: process.env.VITE_PREVIEW_HOST || configuredHost,
    port: Number(process.env.VITE_PREVIEW_PORT || process.env.PIGE360_DEPLOYER_WEB_PORT || 61002),
    strictPort: false,
  },
});
