import { defineConfig } from 'vitest/config'

// Unit tests only; the Playwright browser flow in tests/ runs with `npm run test:e2e`.
export default defineConfig({
  test: { include: ['src/**/*.test.ts'] },
})
