import { defineConfig, devices } from '@playwright/test'

// T18: the whole demo flow in a real browser against the real local stack (FalkorDB + the
// local Ollama model). It uses its own graph (campaign_context_e2e, reset and re-seeded by
// scripts/e2e_backend.py), API port 8001 and UI origin 5174, so the demo graph and the
// normal dev servers on 8000/5173 are never touched.
const E2E_API = 'http://127.0.0.1:8001'
const E2E_UI = 'http://127.0.0.1:5174'
const PYTHON = process.platform === 'win32' ? '..\\.venv\\Scripts\\python.exe' : '../.venv/bin/python'

export default defineConfig({
  testDir: './tests',
  // Three real agent runs, the first including a cold model load.
  timeout: 12 * 60_000,
  expect: { timeout: 15_000 },
  workers: 1,
  retries: 0,
  reporter: [['list'], ['html', { open: 'never' }]],
  use: {
    ...devices['Desktop Chrome'],
    baseURL: E2E_UI,
    viewport: { width: 1280, height: 720 },
    // Tracing is off by default to spare memory on the 5.9 GB demo machine; add `--trace on` to debug.
    trace: 'off',
    screenshot: 'only-on-failure',
  },
  webServer: [
    {
      command: `${PYTHON} ../scripts/e2e_backend.py`,
      url: `${E2E_API}/api/health`,
      timeout: 120_000,
      reuseExistingServer: false,
      stdout: 'pipe',
    },
    {
      // A production build served statically: lighter than the dev server and closer to a demo.
      command: 'npx vite build --outDir dist-e2e --emptyOutDir && npx vite preview --outDir dist-e2e --host 127.0.0.1 --port 5174 --strictPort',
      url: E2E_UI,
      env: { VITE_API_BASE: E2E_API },
      timeout: 120_000,
      reuseExistingServer: false,
    },
  ],
})
