import { fileURLToPath, URL } from "node:url"
import tailwindcss from "@tailwindcss/vite"
import react from "@vitejs/plugin-react"
import { defineConfig } from "vite"
import { VitePWA } from "vite-plugin-pwa"

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    /*
     * Installable shell. The worker precaches the app shell and static assets
     * it needs to start, and nothing else: every `/api/*` request is
     * NetworkOnly, so no student record is ever written to disk. Offline data
     * is out of scope (docs/WEB_APP_PLAN.md, D1).
     *
     * The manifest is authored in `public/manifest.webmanifest` rather than
     * generated here, because it carries the school's name, icons and start
     * URL, which are content rather than build configuration.
     */
    VitePWA({
      registerType: "autoUpdate",
      manifest: false,
      includeAssets: [
        "favicon.svg",
        "hcci-logo.png",
        "apple-touch-icon.png",
        "icon-192.png",
        "icon-512.png",
        "maskable-192.png",
        "maskable-512.png",
      ],
      workbox: {
        globPatterns: ["**/*.{js,css,html,svg,webmanifest,woff2}"],
        navigateFallback: "/index.html",
        navigateFallbackDenylist: [/^\/api\//],
        // The push handlers live in a static file so the precache list stays
        // derived from the build; the worker imports it at install time.
        importScripts: ["/push-sw.js"],
        runtimeCaching: [
          {
            // Same origin in production, Render directly in local dev: match
            // the path, not the host. NetworkOnly writes nothing.
            urlPattern: /\/api\//,
            handler: "NetworkOnly",
          },
        ],
        cleanupOutdatedCaches: true,
      },
    }),
  ],
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  server: {
    port: 5173,
    host: "127.0.0.1",
  },
})
