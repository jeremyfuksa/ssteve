import { defineConfig, devices } from '@playwright/test';

const baseURL = process.env.TAURI_DEV_URL || 'http://localhost:5173';
const useWebServer = process.env.PLAYWRIGHT_WEB_SERVER !== '0';

export default defineConfig({
  timeout: 60_000,
  testDir: 'tests/e2e',
  use: {
    baseURL,
    headless: true,
    viewport: { width: 1280, height: 720 },
  },
  webServer: useWebServer
    ? {
        command: 'npm run dev -- --host --port 5173',
        port: 5173,
        reuseExistingServer: true,
        stdout: 'pipe',
        stderr: 'pipe',
      }
    : undefined,
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
});
