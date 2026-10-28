import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  build: {
    rollupOptions: {
      output: {
        // Function form (not object form): the object form also pulls each
        // listed package's transitive deps into the named chunk, which dragged
        // react-dom/scheduler/zustand into `three` and created a circular
        // three -> vendor -> three chunk graph. That made the entry's vendor
        // chunk side-effect-import the 1 MB three chunk, so dist/index.html
        // modulepreloaded it on every page load despite TwinScene being lazy.
        // Assigning per-module keeps react in vendor, the three stack in
        // `three`, and postprocessing in its own chunk (it only depends on
        // three/fiber, never the reverse), so all three.js code loads only
        // via the dynamic TwinScene import.
        manualChunks(id) {
          const p = id.replace(/\\/g, '/')
          // Keep Vite's dynamic-import preload helper out of `three`:
          // Rollup otherwise placed it there, making the entry chunk
          // statically import three just for that one helper.
          if (p.includes('vite/preload-helper')) return 'vendor'
          if (!p.includes('/node_modules/')) return undefined
          if (p.includes('/@react-three/postprocessing/') || p.includes('/postprocessing/')) return 'postprocessing'
          if (
            p.includes('/three/') || p.includes('/three-stdlib/')
            || p.includes('/@react-three/fiber/') || p.includes('/@react-three/drei/')
          ) return 'three'
          if (p.includes('/framer-motion/') || p.includes('/motion-dom/') || p.includes('/motion-utils/')) return 'motion'
          if (
            p.includes('/react/') || p.includes('/react-dom/') || p.includes('/scheduler/')
            || p.includes('/zustand/') || p.includes('/@tanstack/react-query/') || p.includes('/@tanstack/query-core/')
          ) return 'vendor'
          return undefined
        },
      },
    },
  },
  server: { port: 5173 },
  test: { environment: 'jsdom', exclude: ['**/node_modules/**', '**/e2e/**'] },
})
