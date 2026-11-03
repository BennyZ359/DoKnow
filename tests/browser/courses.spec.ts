import { test, expect, type APIRequestContext, type Page } from '@playwright/test'
import { resolve } from 'node:path'

const api = 'http://127.0.0.1:8001/api'

async function makeGoal(request: APIRequestContext) {
  const response = await request.post(`${api}/goals`, { data: { title: `Python 课程调整 ${crypto.randomUUID()}` } })
  expect(response.ok()).toBeTruthy()
  return response.json()
}

async function open(page: Page, goal: any) {
  await page.goto(`/#/learn/${goal.units[0].id}`)
  await page.getByRole('button', { name: '调整课程与查看历史' }).click()
  await expect(page.locator('.course-editor')).toBeVisible()
  await expect(page.getByRole('button', { name: '读取最新课程', exact: true })).toBeEnabled()
}

async function confirm(page: Page) {
  await page.getByRole('checkbox', { name: /我已核对调整范围/ }).check()
  await page.getByRole('button', { name: '确认课程调整', exact: true }).click()
  await expect(page.locator('.course-editor')).toContainText('课程调整已保存')
}

test('difficulty preview is explicit, survives closing and preserves protected evidence and old drafts', async ({ page, request }) => {
  const goal = await makeGoal(request)
  const fixed = goal.units[1].id
  await request.post(`${api}/units/${fixed}/chat`, { data: { message: '这条导师记录必须保留' } })
  const evidence = await (await request.get(`${api}/units/${fixed}`)).json()
  await page.goto(`/#/learn/${goal.units[0].id}`)
  const draft = '旧单元的思考草稿还没有提交，调整以后也要留在原来的材料旁边。'
  await page.locator('#learn-reflection').fill(draft)
  await page.getByRole('button', { name: '调整课程与查看历史' }).click()
  await page.getByLabel('调整方式').selectOption('difficulty')
  await page.getByLabel('后续课程难度').selectOption('advanced')
  await page.getByRole('button', { name: '预览课程调整' }).click()
  await expect(page.getByLabel('课程变更预览')).toContainText('入门 → 高级')
  await expect(page.getByRole('button', { name: '确认课程调整', exact: true })).toBeDisabled()
  await page.getByText('查看新课程材料', { exact: true }).first().click()
  await expect(page.getByLabel('课程变更预览')).toContainText('设计反例')
  expect((await (await request.get(`${api}/goals/${goal.id}`)).json()).course_version).toBe(1)
  await page.getByRole('button', { name: '关闭课程调整' }).click()
  await expect(page.locator('#learn-reflection')).toHaveValue(draft)
  await page.getByRole('button', { name: '调整课程与查看历史' }).click()
  await expect(page.getByLabel('课程变更预览')).toBeVisible()
  await confirm(page)
  await expect(page.getByLabel('课程变更记录')).toContainText('版本 1 → 2')
  expect(await (await request.get(`${api}/units/${fixed}`)).json()).toEqual(evidence)
  await page.getByRole('button', { name: '关闭课程调整' }).click()
  await expect(page.getByText(/这是已被替换的旧单元/)).toBeVisible()
  await expect(page.locator('#learn-reflection')).toHaveValue(draft)
  await expect(page.locator('#learn-reflection')).toBeDisabled()
  await expect(page.getByRole('button', { name: '一起思考' })).toBeDisabled()
  await page.reload()
  await expect(page.locator('#learn-reflection')).toHaveValue(draft)
  await expect(page.getByText(/这是已被替换的旧单元/)).toBeVisible()
})

test('keyboard reorder keeps a started middle slot fixed and returns focus on close', async ({ page, request }) => {
  const goal = await makeGoal(request)
  await request.post(`${api}/units/${goal.units[1].id}/chat`, { data: { message: '固定这个位置' } })
  await open(page, goal)
  await expect(page.getByLabel('调整方式')).toBeFocused()
  await page.getByLabel('调整方式').selectOption('reorder')
  const move = page.getByRole('button', { name: `上移 ${goal.units[2].title}` })
  await move.focus()
  await page.keyboard.press('Enter')
  await expect(page.getByLabel('当前课程顺序').locator('li').first()).toContainText(goal.units[2].title)
  await expect(page.getByLabel('当前课程顺序').locator('li').nth(1)).toContainText(goal.units[1].title)
  await expect(page.getByLabel('当前课程顺序').locator('li').last()).toContainText(goal.units[0].title)
  await page.getByRole('button', { name: '预览课程调整' }).click()
  await expect(page.locator('.course-preview h3')).toBeFocused()
  await confirm(page)
  const saved = await (await request.get(`${api}/goals/${goal.id}`)).json()
  expect(saved.units.map((unit: any) => unit.id)).toEqual([goal.units[2].id, goal.units[1].id, goal.units[0].id])
  await page.keyboard.press('Escape')
  await expect(page.locator('.course-editor')).toHaveCount(0)
  await expect(page.getByRole('button', { name: '调整课程与查看历史' })).toBeFocused()
})

test('a new learning record invalidates preview and requires a fresh user confirmation', async ({ page, request }) => {
  const goal = await makeGoal(request)
  await open(page, goal)
  await page.getByRole('button', { name: '预览课程调整' }).click()
  await expect(page.getByLabel('课程变更预览')).toBeVisible()
  await request.post(`${api}/units/${goal.units[0].id}/chat`, { data: { message: '预览后新保存的记录' } })
  await page.getByRole('checkbox', { name: /我已核对调整范围/ }).check()
  await page.getByRole('button', { name: '确认课程调整', exact: true }).click()
  await expect(page.locator('.course-editor')).toContainText('预览后课程或学习记录已变化')
  await expect(page.getByRole('button', { name: '确认课程调整', exact: true })).toBeDisabled()
  await page.getByRole('button', { name: '读取最新课程', exact: true }).click()
  await expect(page.getByLabel('当前课程顺序').locator('li').first()).toContainText('固定保留')
  await page.getByRole('button', { name: '预览课程调整' }).click()
  await confirm(page)
  const saved = await (await request.get(`${api}/goals/${goal.id}`)).json()
  expect(saved.units[0].id).toBe(goal.units[0].id)
  expect(saved.course_version).toBe(2)
})

for (const action of ['preview', 'apply'] as const) {
  test(`lost ${action} response recovers the same action after reload`, async ({ page, request }) => {
    const goal = await makeGoal(request)
    await open(page, goal)
    if (action === 'apply') {
      await page.getByRole('button', { name: '预览课程调整' }).click()
      await expect(page.getByLabel('课程变更预览')).toBeVisible()
      await page.getByRole('checkbox', { name: /我已核对调整范围/ }).check()
    }
    let originalKey = ''
    let dropped = false
    const pattern = `**/api/goals/${goal.id}/course/${action}`
    await page.route(pattern, async (route) => {
      const response = await route.fetch()
      if (!dropped) {
        dropped = true
        originalKey = route.request().headers()['idempotency-key']!
        expect(response.ok()).toBeTruthy()
        await route.abort('failed')
      } else {
        expect(route.request().headers()['idempotency-key']).toBe(originalKey)
        expect(response.headers()['idempotency-replayed']).toBe('true')
        await route.fulfill({ response })
      }
    })
    await page.getByRole('button', { name: action === 'preview' ? '预览课程调整' : '确认课程调整', exact: true }).click()
    await expect(page.locator('.course-editor .pending-operations')).toBeVisible()
    await page.reload()
    await page.getByRole('button', { name: '调整课程与查看历史' }).click()
    await page.getByRole('button', { name: action === 'preview' ? '恢复生成课程预览' : '恢复确认课程调整' }).click()
    if (action === 'preview') {
      await expect(page.getByLabel('课程变更预览')).toBeVisible()
      await confirm(page)
    } else await expect(page.locator('.course-editor')).toContainText('课程调整已保存')
    await expect(page.locator('.course-editor .pending-operations')).toHaveCount(0)
    const course = await (await request.get(`${api}/goals/${goal.id}/course`)).json()
    expect(course.goal.course_version).toBe(2)
    expect(course.history).toHaveLength(1)
  })
}

test('confirmed adjustment remains successful when current-state synchronization fails', async ({ page, request }) => {
  const goal = await makeGoal(request)
  await open(page, goal)
  await page.getByRole('button', { name: '预览课程调整' }).click()
  await expect(page.getByLabel('课程变更预览')).toBeVisible()
  await page.route(`**/api/goals/${goal.id}/course`, (route) => route.fulfill({ status: 503, json: { detail: '临时不可用' } }))
  await confirm(page)
  await expect(page.locator('.course-editor')).toContainText('调整已保存，最新课程暂未同步')
  await expect(page.locator('.course-editor .pending-operations')).toHaveCount(0)
  await expect(page.getByRole('button', { name: '确认课程调整', exact: true })).toHaveCount(0)
  await page.unroute(`**/api/goals/${goal.id}/course`)
  await page.getByRole('button', { name: '读取最新课程', exact: true }).click()
  await expect(page.getByLabel('课程变更记录')).toContainText('版本 1 → 2')
  expect((await (await request.get(`${api}/goals/${goal.id}/course`)).json()).history).toHaveLength(1)
})

test('mobile preview stays within the dialog and handles a failed generation', async ({ page, request }) => {
  const goal = await makeGoal(request)
  await page.setViewportSize({ width: 390, height: 844 })
  await open(page, goal)
  const pattern = `**/api/goals/${goal.id}/course/preview`
  await page.route(pattern, (route) => route.fulfill({ status: 502, json: { detail: '规划服务暂时不可用，课程尚未改变。' } }))
  await page.getByRole('button', { name: '预览课程调整' }).click()
  await expect(page.locator('.course-editor')).toContainText('课程尚未改变')
  await page.unroute(pattern)
  await page.getByRole('button', { name: '恢复生成课程预览' }).click()
  await expect(page.getByLabel('课程变更预览')).toBeVisible()
  await page.getByText('查看新课程材料', { exact: true }).first().click()
  expect(await page.locator('.course-editor').evaluate((element) => element.scrollWidth <= element.clientWidth + 1)).toBeTruthy()
  await page.screenshot({ path: resolve(import.meta.dirname, '../../.cache/browser/course-preview-mobile.png') })
  await confirm(page)
})

test('all-started course explains why adjustments are unavailable', async ({ page, request }) => {
  const goal = await makeGoal(request)
  for (const unit of goal.units) await request.post(`${api}/units/${unit.id}/chat`, { data: { message: '保留此单元' } })
  await open(page, goal)
  await expect(page.locator('.course-editor')).toContainText('没有可调整的未开始单元')
  await expect(page.getByRole('button', { name: '预览课程调整' })).toBeDisabled()
  await expect(page.getByLabel('课程变更记录')).toContainText('还没有已确认')
})
