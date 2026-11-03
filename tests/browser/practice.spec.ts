import { test, expect, type APIRequestContext } from '@playwright/test'
import { execFileSync } from 'node:child_process'
import { resolve } from 'node:path'

const api = 'http://127.0.0.1:8001/api'
const root = resolve(import.meta.dirname, '../..')
const python = resolve(root, 'backend/.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python')

async function practiceGoal(request: APIRequestContext) {
  const response = await request.post(`${api}/goals`, { data: { title: `Python 多题验证 ${crypto.randomUUID()}` } })
  expect(response.ok()).toBeTruthy()
  const goal = await response.json()
  const id = goal.units[0].id
  const learned = await request.post(`${api}/units/${id}/learn`, { data: { reflection: '变量指向值，字符串和数字需要区分，先转换再计算，并检查边界。' } })
  expect(learned.ok()).toBeTruthy()
  return id
}

test('question drafts survive reload and a stale tab cannot answer the next question', async ({ page, context, request }) => {
  const id = await practiceGoal(request)
  await page.goto(`/#/learn/${id}`)
  await page.getByRole('radio', { name: "int('3') + 2" }).check()
  await page.reload()
  await expect(page.locator('.practice-options input:checked')).toHaveCount(1)
  const other = await context.newPage()
  await other.goto(`/#/learn/${id}`)
  await other.getByRole('radio', { name: "int('3') + 2" }).check()
  await page.getByRole('button', { name: '提交答案', exact: true }).click()
  await expect(page.locator('.practice-progress')).toContainText('已通过 1 / 3 题')
  await expect(page.locator('.practice-options input:checked')).toHaveCount(0)
  await expect(page.getByRole('button', { name: '进入真实问题', exact: true })).toHaveCount(0)
  await other.getByRole('button', { name: '提交答案', exact: true }).click()
  await expect(other.locator('main .alert.error')).toContainText('题目已更新')
  await other.reload()
  await expect(other.locator('.practice-progress')).toContainText('已通过 1 / 3 题')
  await expect(other.locator('.practice-options input:checked')).toHaveCount(0)
  const unit = await (await request.get(`${api}/units/${id}`)).json()
  expect(unit.sessions.filter((item: { kind: string }) => item.kind === 'practice')).toHaveLength(1)
  await other.close()
})

test('confirming a lost practice response preserves the next question draft and does not grade twice', async ({ page, request }) => {
  const id = await practiceGoal(request)
  await page.goto(`/#/learn/${id}`)
  await page.getByRole('radio', { name: "int('3') + 2" }).check()
  await page.route(`**/api/units/${id}/practice`, async (route) => {
    const response = await route.fetch()
    expect(response.ok()).toBeTruthy()
    await route.abort()
  })
  await page.getByRole('button', { name: '提交答案', exact: true }).click()
  await expect(page.getByLabel('待确认的操作')).toBeVisible()
  await page.unroute(`**/api/units/${id}/practice`)
  await page.reload()
  await expect(page.locator('.practice-progress')).toContainText('已通过 1 / 3 题')
  await page.getByRole('radio', { name: "int('4') * 3" }).check()
  await page.getByRole('button', { name: '确认上次操作', exact: true }).click()
  await expect(page.getByLabel('待确认的操作')).toHaveCount(0)
  await expect(page.locator('.practice-progress')).toContainText('已通过 1 / 3 题')
  await expect(page.locator('.practice-options input:checked')).toHaveCount(1)
  const unit = await (await request.get(`${api}/units/${id}`)).json()
  expect(unit.sessions.filter((item: { kind: string }) => item.kind === 'practice')).toHaveLength(1)
  await page.getByRole('button', { name: '提交答案', exact: true }).click()
  await expect(page.locator('.practice-progress')).toContainText('已通过 2 / 3 题')
})

test('history distinguishes unknown records, AI model snapshots and structural checks on mobile', async ({ page, request }) => {
  const id = await practiceGoal(request)
  // Seed only the isolated test database, preserving null provenance for the legacy row.
  execFileSync(python, ['-c',
    "import sqlite3,sys,json; db=sqlite3.connect(sys.argv[1]); rows=[('old-evidence',None),('ai-evidence',json.dumps({'source':'ai','provider':'compatible','requested_model':'requested-v1','model':'reported-v1','rule_version':'semantic-v1','passed':False})),('demo-evidence',json.dumps({'source':'demo','rule_version':'structure-v1','passed':True}))]; db.executemany('INSERT INTO learning_sessions (id,unit_id,kind,content,feedback,score,created_at,assessment) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',[(key,sys.argv[2],'project','历史作品','已有评价',40,'2026-01-01 00:00:00',meta) for key,meta in rows]); db.commit(); db.close()",
    process.env.DOKNOW_TEST_DB!, id,
  ])
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto(`/#/learn/${id}`)
  await page.locator('.session-history summary').click()
  await page.getByLabel('筛选学习足迹').selectOption('assessments')
  await expect(page.locator('.session-history article')).toHaveCount(3)
  await expect(page.getByText('来源未知', { exact: true })).toBeVisible()
  await expect(page.getByText('AI · 语义评价', { exact: true })).toBeVisible()
  await expect(page.getByText('体验 · 结构检查', { exact: true })).toBeVisible()
  await expect(page.locator('.assessment-model')).toContainText('请求模型：requested-v1')
  await expect(page.locator('.assessment-model')).toContainText('返回模型：reported-v1')
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy()
  await page.screenshot({ path: resolve(root, '.cache/browser/p1-history-mobile.png'), fullPage: true })
})
