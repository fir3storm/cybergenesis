import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          three: ['three', '@react-three/fiber', '@react-three/drei'],
          motion: ['framer-motion'],
          vendor: ['react', 'react-dom', 'zustand', '@tanstack/react-query'],
        },
      },
    },
  },
  server: { port: 5173 },
  test: { environment: 'jsdom', exclude: ['**/node_modules/**', '**/e2e/**'] },
})
