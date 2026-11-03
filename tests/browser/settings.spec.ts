import { test, expect } from '@playwright/test'
import { resolve } from 'node:path'

test('settings report real demo and schema status with keyboard refresh and help', async ({ page }) => {
  const writes: string[] = []
  page.on('request', request => { if (request.method() !== 'GET') writes.push(request.method()) })
  await page.goto('/#/settings')
  const panel = page.getByRole('region', { name: '运行状态' })
  await expect(panel).toContainText('0004_editable_records')
  await expect(panel).toContainText('体验模式，无需密钥；未调用模型')
  await expect(page.getByRole('heading', { level: 1 })).toBeFocused()
  await page.keyboard.press('Tab')
  const refresh = panel.getByRole('button', { name: '刷新运行状态' })
  await expect(refresh).toBeFocused()
  await page.keyboard.press('Enter')
  await expect(panel).toContainText('0004_editable_records')
  await expect(refresh).toBeFocused()
  await page.keyboard.press('Tab')
  await expect(panel.locator('summary')).toBeFocused()
  await page.keyboard.press('Enter')
  await expect(panel.getByText('在项目目录运行', { exact: false })).toBeVisible()
  expect(writes).toEqual([])
})

test('failed refresh clears stale success and keyboard retry recovers without losing focus', async ({ page }) => {
  await page.goto('/#/settings')
  const panel = page.getByRole('region', { name: '运行状态' })
  await expect(panel).toContainText('0004_editable_records')
  await page.route('**/api/diagnostics', route => route.abort())
  const refresh = panel.getByRole('button', { name: '刷新运行状态' })
  await refresh.focus()
  await page.keyboard.press('Enter')
  await expect(panel.getByRole('alert')).toContainText('diagnose')
  await expect(panel.locator('.runtime-checks')).toHaveCount(0)
  await expect(refresh).toBeFocused()
  await page.unroute('**/api/diagnostics')
  await page.keyboard.press('Enter')
  await expect(panel).toContainText('0004_editable_records')
  await expect(panel.getByRole('alert')).toHaveCount(0)
  await expect(refresh).toBeFocused()
})

test('diagnosis remains available when dashboard reads fail and displays database guidance on mobile', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await page.route('**/api/dashboard', route => route.fulfill({ status: 503, json: { detail: '数据库暂不可用' } }))
  await page.route('**/api/diagnostics', route => route.fulfill({ json: {
    status: 'error', mode: 'demo', database: 'sqlite', read_only: true,
    checks: [
      { name: 'backend', status: 'ok', detail: '后端已响应。', action: '' },
      { name: 'mode', status: 'ok', detail: '体验模式，无需密钥；未调用模型。', action: '' },
      { name: 'database', status: 'error', detail: '数据库无法读取或结构不兼容。', action: '保留原库，按 docs/DATA_MANAGEMENT.md 校验备份。' },
    ],
  } }))
  await page.goto('/#/settings')
  const panel = page.getByRole('region', { name: '运行状态' })
  await expect(panel).toContainText('数据库无法读取')
  await expect(panel).toContainText('需处理')
  await panel.locator('summary').click()
  await expect(panel).toContainText('保留原库')
  await page.evaluate(() => window.scrollTo(0, 0))
  await expect(panel.getByRole('button', { name: '刷新运行状态' })).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy()
  await page.screenshot({ path: resolve(import.meta.dirname, '../../.cache/browser/settings-mobile.png'), fullPage: true })
})

test('settings do not wait for stalled learning-data requests', async ({ page }) => {
  let dashboardCalls = 0
  await page.route('**/api/dashboard', async route => {
    dashboardCalls++
    await route.abort()
  })
  await page.goto('/#/settings')
  await expect(page.locator('.runtime-checks')).toContainText('0004_editable_records')
  expect(dashboardCalls).toBe(0)
})

test('refresh prevents duplicate requests and cancels an in-flight report when leaving settings', async ({ page }) => {
  await page.goto('/#/settings')
  await expect(page.locator('.runtime-checks')).toContainText('0004_editable_records')
  let calls = 0
  let release!: () => void
  const waiting = new Promise<void>(resolve => { release = resolve })
  await page.route('**/api/diagnostics', async route => {
    calls++
    await waiting
    await route.continue().catch(() => {})
  })
  const refresh = page.getByRole('button', { name: '刷新运行状态' })
  await refresh.click()
  await expect(page.getByRole('button', { name: '正在检查…' })).toHaveAttribute('aria-disabled', 'true')
  await page.keyboard.press('Enter')
  expect(calls).toBe(1)
  await page.getByRole('button', { name: '学习概览', exact: true }).click()
  release()
  await expect(page.locator('.runtime-panel')).toHaveCount(0)
  await expect(page.getByRole('heading', { level: 1 })).not.toContainText('一套有来处')
})
