import { defineConfig, devices } from '@playwright/test';

// Smoke tests against a live `kb-core serve` (the dev stack with the OCBC documents built and indexed).
const BASE = process.env.KB_CORE_UI_BASE ?? 'http://127.0.0.1:8200';

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 60_000,
  reporter: [['list']],
  use: {
    baseURL: `${BASE}/ui/`,
    trace: 'off',
    screenshot: 'off',
    launchOptions: process.env.PW_CHROMIUM_PATH ? { executablePath: process.env.PW_CHROMIUM_PATH } : {},
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'], viewport: { width: 1440, height: 940 } } }],
  webServer: {
    command: 'uv run kb-core serve',
    cwd: '..',
    url: `${BASE}/v1/admin/config`,
    reuseExistingServer: true,
    timeout: 120_000,
  },
});
