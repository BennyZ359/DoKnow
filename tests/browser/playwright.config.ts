import { defineConfig } from '@playwright/test'
import { resolve } from 'node:path'
import { mkdirSync } from 'node:fs'
import { randomUUID } from 'node:crypto'

const root = resolve(import.meta.dirname, '../..')
const cache = resolve(root, '.cache/browser')
mkdirSync(cache, { recursive: true })
const dbPath = process.env.DOKNOW_TEST_DB || resolve(cache, `${randomUUID()}.db`)
process.env.DOKNOW_TEST_DB = dbPath
const python = resolve(root, 'backend/.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python')

export default defineConfig({
  testDir: '.',
  testMatch: '**/*.spec.ts',
  timeout: 60_000,
  workers: 1,
  fullyParallel: false,
  reporter: 'list',
  use: {
    baseURL: 'http://127.0.0.1:5174',
    browserName: 'chromium',
    channel: process.env.DOKNOW_BROWSER_CHANNEL || 'chrome',
    headless: true,
    viewport: { width: 1440, height: 1000 },
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  webServer: [
    {
      command: `"${python}" -m uvicorn app.main:app --host 127.0.0.1 --port 8001`,
      cwd: resolve(root, 'backend'),
      url: 'http://127.0.0.1:8001/api/health',
      env: { DATABASE_URL: `sqlite:///${dbPath.replaceAll('\\', '/')}`, AI_PROVIDER: 'demo', REDIS_URL: '' },
      reuseExistingServer: false,
      timeout: 30_000,
    },
    {
      command: `"${process.execPath}" "${resolve(root, 'frontend/node_modules/vite/bin/vite.js')}" --host 127.0.0.1 --port 5174 --strictPort`,
      cwd: resolve(root, 'frontend'),
      url: 'http://127.0.0.1:5174',
      env: { DOKNOW_API_TARGET: 'http://127.0.0.1:8001' },
      reuseExistingServer: false,
      timeout: 30_000,
    },
  ],
})
