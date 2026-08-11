const { defineConfig, devices } = require('@playwright/test');
const path = require('path');

const baseURL = process.env.RUANA_BASE_URL || 'http://127.0.0.1:5000';
const qaArtifactsDir = path.join(__dirname, 'qa-artifacts');
const qaDbPath =
  process.env.RUANA_DB_PATH || path.join(qaArtifactsDir, `ruana-e2e-${Date.now()}.db`);

module.exports = defineConfig({
  testDir: './e2e',
  timeout: 180 * 1000,
  expect: {
    timeout: 12 * 1000,
  },
  fullyParallel: false,
  retries: process.env.CI ? 1 : 0,
  reporter: [
    ['list'],
    ['html', { outputFolder: 'qa-artifacts/playwright-report', open: 'never' }],
    ['json', { outputFile: 'qa-artifacts/results/qa-e2e-results.json' }],
  ],
  outputDir: 'qa-artifacts/test-results',
  use: {
    baseURL,
    locale: 'es-ES',
    timezoneId: 'Europe/Madrid',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'on',
  },
  webServer: process.env.RUANA_SKIP_WEBSERVER
    ? undefined
    : {
        command: 'python RUANA/web/run.py',
        url: baseURL,
        reuseExistingServer: false,
        timeout: 45 * 1000,
        env: {
          ...process.env,
          FLASK_SECRET_KEY: process.env.FLASK_SECRET_KEY || 'ruana_qa_secret_key',
          PYTHONIOENCODING: 'utf-8',
          PYTHONUTF8: '1',
          RUANA_DB_PATH: qaDbPath,
          RUANA_ADMIN_CREDENTIALS_PATH: path.join(__dirname, 'RUANA/config/admin_credentials.qa.json'),
          RUANA_ALLOW_LOCAL_UPLOADS: '1',
          DATABASE_URL: '',
          SUPABASE_URL: '',
          SUPABASE_SERVICE_ROLE_KEY: '',
        },
      },
  projects: [
    {
      name: 'chromium-desktop-video',
      use: {
        ...devices['Desktop Chrome'],
        viewport: { width: 1440, height: 950 },
      },
    },
  ],
});
