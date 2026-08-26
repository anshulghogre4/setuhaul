import path from 'node:path'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { VitePWA } from 'vite-plugin-pwa'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    // TECH_STACK.md section 9: the driver surface ships as an installable PWA (roadside use,
    // poor connectivity, cheap Android). `registerType: 'prompt'` rather than 'autoUpdate'
    // because a silent reload can land mid-exception, and auth-and-scoping.md is explicit that
    // a driver must never lose in-flight work.
    VitePWA({
      registerType: 'prompt',
      includeAssets: ['favicon.svg'],
      manifest: {
        name: 'SetuHaul Dock Command',
        short_name: 'SetuHaul',
        description: 'Dock appointment coordination for drivers, planners and gate officers.',
        start_url: '/',
        display: 'standalone',
        // implementation-spec.md section 2.5 PWA note: NOT the mockup board's #E2E8F0
        // (neutral-200 is the reference board's own chrome, not an app surface).
        // surface-base is the real app background.
        background_color: '#F8FAFC',
        theme_color: '#F8FAFC',
        icons: [
          { src: '/pwa-192.png', sizes: '192x192', type: 'image/png' },
          { src: '/pwa-512.png', sizes: '512x512', type: 'image/png' },
          { src: '/pwa-512.png', sizes: '512x512', type: 'image/png', purpose: 'maskable' },
        ],
      },
      workbox: {
        // Never precache the API. Postgres is the source of truth and a cached capacity
        // response is exactly the stale-commitment risk SOLUTION_DESIGN.md section 7.1 exists
        // to prevent.
        navigateFallbackDenylist: [/^\/api\//],
        globPatterns: ['**/*.{js,css,html,svg,png,woff2}'],
      },
      devOptions: { enabled: false },
    }),
  ],
  resolve: {
    alias: {
      '@': path.resolve(import.meta.dirname, './src'),
    },
  },
})
