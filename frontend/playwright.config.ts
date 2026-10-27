import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  testMatch: '**/*.e2e.ts',
  timeout: 240_000,
  use: { baseURL: process.env.E2E_BASE_URL ?? 'http://localhost:5173', channel: process.env.E2E_CHANNEL ?? 'msedge' },
})
