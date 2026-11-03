import { test, expect, type APIRequestContext, type Page } from '@playwright/test'
import { readFile } from 'node:fs/promises'
import { resolve } from 'node:path'

const api = 'http://127.0.0.1:8001/api'
const root = resolve(import.meta.dirname, '../..')

async function makeRecord(request: APIRequestContext, kind: 'knowledge' | 'goals') {
  const response = await request.post(`${api}/${kind}`, { data: {
    title: `编辑验证 ${crypto.randomUUID()}`,
    ...(kind === 'knowledge' ? { content: '星桥练习采用红色记录卡，用具体例子检验认识。' } : {}),
  } })
  expect(response.ok()).toBeTruthy()
  return response.json()
}

async function openEditor(page: Page, kind: 'knowledge' | 'goals', title: string) {
  await page.getByRole('button', { name: `${kind === 'knowledge' ? '编辑笔记' : '编辑目标'} ${title}`, exact: true }).click()
  await expect(page.locator('#edit-title')).toBeVisible()
  await expect(page.getByText('正在读取最新记录…')).toHaveCount(0)
}

test('notes can be edited, filtered and exported while original evidence and grounded answers remain correct', async ({ page, request }) => {
  const item = await makeRecord(request, 'knowledge')
  const updatedTitle = `整理后的星桥 ${crypto.randomUUID()}`
  const content = '星桥练习采用蓝色行动卡，每次先检查边界，再记录实际结果。'
  await page.goto('/#/knowledge')
  await page.getByLabel('知识库问题').fill('星桥练习采用什么？')
  await page.getByRole('button', { name: '寻找答案' }).click()
  await expect(page.locator('.knowledge-answer')).toContainText('红色记录卡')
  await openEditor(page, 'knowledge', item.title)
  await page.locator('#edit-title').fill(updatedTitle)
  await page.getByLabel('笔记正文', { exact: true }).fill(content)
  await page.getByLabel('标签', { exact: true }).fill('行动，待实践, 行动')
  await page.getByRole('button', { name: '保存修改', exact: true }).click()
  await expect(page.locator('.record-editor')).toHaveCount(0)
  await expect(page.locator('.knowledge-answer')).toHaveCount(0)
  await page.getByLabel('搜索知识笔记').fill(updatedTitle)
  await page.getByLabel('标签筛选').selectOption('待实践')
  await page.getByLabel('来源筛选').selectOption('note')
  await expect(page.locator('.note-card')).toHaveCount(1)
  await expect(page.locator('.note-tags')).toHaveText('行动待实践')
  await page.getByRole('button', { name: '查看原始记录', exact: true }).click()
  await expect(page.getByLabel('原始记录', { exact: true })).toContainText(item.content)
  await expect(page.locator('.note-content')).toContainText(content)
  const downloading = page.waitForEvent('download')
  await page.getByRole('link', { name: '导出筛选结果 Markdown' }).click()
  const download = await downloading
  const markdown = await readFile((await download.path())!, 'utf8')
  expect(markdown).toContain(updatedTitle)
  expect(markdown).toContain(content)
  expect(markdown).toContain(item.content)
  expect(markdown).toContain('原始记录（保留）')
  await page.getByRole('button', { name: '寻找答案' }).click()
  await expect(page.locator('.knowledge-answer')).toContainText('蓝色行动卡')
  const saved = await (await request.get(`${api}/knowledge/${item.id}`)).json()
  expect(saved.tags).toEqual(['行动', '待实践'])
  expect(saved.original).toEqual({ title: item.title, content: item.content })
  expect(saved.version).toBe(2)
})

test('two note editors preserve their drafts and require an explicit decision after a conflict or reload', async ({ page, context, request }) => {
  const item = await makeRecord(request, 'knowledge')
  const first = '第一个页面的新认识：用正常输入和边界输入验证行为。'
  const second = '第二个页面正在写的内容，发生冲突和刷新之后都不能丢失。'
  await page.goto('/#/knowledge')
  await openEditor(page, 'knowledge', item.title)
  const other = await context.newPage()
  await other.goto('/#/knowledge')
  await openEditor(other, 'knowledge', item.title)
  await page.getByLabel('笔记正文', { exact: true }).fill(first)
  await other.getByLabel('笔记正文', { exact: true }).fill(second)
  await page.getByRole('button', { name: '保存修改', exact: true }).click()
  await expect(page.locator('.record-editor')).toHaveCount(0)
  await other.getByRole('button', { name: '保存修改', exact: true }).click()
  await expect(other.getByLabel('编辑冲突', { exact: true })).toContainText(first)
  await expect(other.getByLabel('笔记正文', { exact: true })).toHaveValue(second)
  await expect(other.getByRole('button', { name: '保存修改', exact: true })).toBeDisabled()
  await other.reload()
  await openEditor(other, 'knowledge', item.title)
  await expect(other.getByLabel('笔记正文', { exact: true })).toHaveValue(second)
  await expect(other.getByLabel('编辑冲突', { exact: true })).toContainText(first)
  await other.getByLabel('笔记正文', { exact: true }).fill(`${first}\n${second}`)
  await other.getByRole('button', { name: '已核对，保留我的修改', exact: true }).click()
  await other.getByRole('button', { name: '保存修改', exact: true }).click()
  await expect(other.locator('.record-editor')).toHaveCount(0)
  const saved = await (await request.get(`${api}/knowledge/${item.id}`)).json()
  expect(saved.version).toBe(3)
  expect(saved.content).toBe(`${first}\n${second}`)
  expect(saved.original.content).toBe(item.content)
  await other.close()
})

test('basic goal edits describe their effect, retain courses and handle another page changing the goal', async ({ page, context, request }) => {
  const goal = await makeRecord(request, 'goals')
  const id = goal.units[0].id
  await request.post(`${api}/units/${id}/learn`, { data: { reflection: '变量指向值，数字和字符串需要区分，先转换再计算，并检查边界条件。' } })
  const before = await (await request.get(`${api}/units/${id}`)).json()
  await page.goto(`/#/learn/${id}`)
  await page.getByRole('button', { name: '编辑目标信息', exact: true }).click()
  await expect(page.getByText(/不会重排课程或改变复习日期/)).toBeVisible()
  const other = await context.newPage()
  await other.goto('/#/dashboard')
  await openEditor(other, 'goals', goal.title)
  const title = `新的学习方向名称 ${crypto.randomUUID()}`
  await page.getByLabel('目标标题', { exact: true }).fill(title)
  await page.getByLabel('学习动机（可选）').fill('把可验证的小程序应用到每天的工作中。')
  await page.getByLabel('每日学习时间（分钟）').fill('75')
  await page.getByRole('button', { name: '保存修改', exact: true }).click()
  await expect(page.locator('.record-editor')).toHaveCount(0)
  await expect(page.locator('#goal-select option:checked')).toHaveText(title)
  await other.getByLabel('目标标题', { exact: true }).fill('第二个页面的旧版本修改')
  await other.getByRole('button', { name: '保存修改', exact: true }).click()
  await expect(other.getByLabel('编辑冲突', { exact: true })).toContainText(title)
  await other.getByRole('button', { name: '使用最新内容', exact: true }).click()
  await expect(other.getByLabel('目标标题', { exact: true })).toHaveValue(title)
  await expect(other.getByLabel('每日学习时间（分钟）')).toHaveValue('75')
  const after = await (await request.get(`${api}/units/${id}`)).json()
  expect(after).toEqual({ ...before, goal_title: title })
  const saved = await (await request.get(`${api}/goals/${goal.id}`)).json()
  expect(saved.units.map((unit: { id: string }) => unit.id)).toEqual(goal.units.map((unit: { id: string }) => unit.id))
  expect(saved.version).toBe(2)
  expect(saved.daily_minutes).toBe(75)
  await other.close()
})

for (const kind of ['knowledge', 'goals'] as const) {
  test(`a lost ${kind} edit response is confirmed after reload using the same PATCH and receipt`, async ({ page, request }) => {
    const item = await makeRecord(request, kind)
    const path = `${api}/${kind}/${item.id}`
    const routePath = `**/api/${kind}/${item.id}`
    const keys: string[] = []
    page.on('request', (request) => {
      if (request.method() === 'PATCH' && request.url().endsWith(`/api/${kind}/${item.id}`)) keys.push(request.headers()['idempotency-key'])
    })
    await page.goto(kind === 'knowledge' ? '/#/knowledge' : '/#/dashboard')
    await openEditor(page, kind, item.title)
    const title = `恢复确认后的标题 ${crypto.randomUUID()}`
    await page.locator('#edit-title').fill(title)
    await page.route(routePath, async (route) => {
      if (route.request().method() !== 'PATCH') return route.continue()
      const response = await route.fetch()
      expect(response.ok()).toBeTruthy()
      await route.abort()
    })
    await page.getByRole('button', { name: '保存修改', exact: true }).click()
    await expect(page.getByRole('button', { name: '确认上次保存', exact: true })).toBeVisible()
    await expect(page.getByRole('button', { name: '确认上次保存', exact: true })).toBeEnabled()
    await page.unroute(routePath)
    await page.reload()
    await page.getByRole('button', { name: '确认上次操作', exact: true }).click()
    await expect(page.getByLabel('待确认的操作')).toHaveCount(0)
    await expect(page.getByRole('heading', { name: title, exact: true })).toHaveCount(1)
    expect(keys).toHaveLength(2)
    expect(keys[1]).toBe(keys[0])
    const saved = await (await request.get(path)).json()
    expect(saved.version).toBe(2)
    await openEditor(page, kind, title)
    await expect(page.locator('#edit-title')).toHaveValue(title)
    await expect(page.getByLabel('编辑冲突', { exact: true })).toHaveCount(0)
  })
}

test('confirming an earlier edit keeps newer unsaved text for comparison', async ({ page, request }) => {
  const item = await makeRecord(request, 'knowledge')
  const path = `${api}/knowledge/${item.id}`
  const routePath = `**/api/knowledge/${item.id}`
  await page.goto('/#/knowledge')
  await openEditor(page, 'knowledge', item.title)
  await page.getByLabel('笔记正文', { exact: true }).fill('先保存这份已经完成的笔记，后续内容要单独保留。')
  await page.route(routePath, async (route) => {
    if (route.request().method() !== 'PATCH') return route.continue()
    await route.fetch()
    await route.abort()
  })
  await page.getByRole('button', { name: '保存修改', exact: true }).click()
  await expect(page.getByRole('button', { name: '确认上次保存', exact: true })).toBeVisible()
  await page.getByLabel('笔记正文', { exact: true }).fill('响应丢失之后又写的新内容，不应被上次保存回执清空。')
  await page.unroute(routePath)
  await page.getByRole('button', { name: '确认上次保存', exact: true }).click()
  await expect(page.getByLabel('笔记正文', { exact: true })).toHaveValue('响应丢失之后又写的新内容，不应被上次保存回执清空。')
  await expect(page.getByLabel('编辑冲突', { exact: true })).toContainText('先保存这份已经完成的笔记')
  expect((await (await request.get(path)).json()).version).toBe(2)
})

test('a saved note edit stays successful when subsequent reads fail', async ({ page, request }) => {
  const item = await makeRecord(request, 'knowledge')
  await page.goto('/#/knowledge')
  await openEditor(page, 'knowledge', item.title)
  const title = `同步失败仍已保存 ${crypto.randomUUID()}`
  await page.locator('#edit-title').fill(title)
  await page.route('**/api/dashboard', (route) => route.abort())
  await page.route('**/api/knowledge', (route) => route.abort())
  await page.getByRole('button', { name: '保存修改', exact: true }).click()
  await expect(page.locator('.record-editor')).toHaveCount(0)
  await expect(page.getByRole('heading', { name: title, exact: true })).toBeVisible()
  await expect(page.getByText('提交已保存，部分记录暂未同步。可以稍后同步最新记录。')).toBeVisible()
  await expect(page.getByLabel('待确认的操作')).toHaveCount(0)
  expect((await (await request.get(`${api}/knowledge/${item.id}`)).json()).version).toBe(2)
})

test('note management and editing remain usable on a phone', async ({ page, request }) => {
  const item = await makeRecord(request, 'knowledge')
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/#/knowledge')
  await page.getByLabel('搜索知识笔记').fill(item.title)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy()
  await page.screenshot({ path: resolve(root, '.cache/browser/knowledge-management-mobile.png'), fullPage: true })
  await openEditor(page, 'knowledge', item.title)
  await page.getByLabel('标签', { exact: true }).fill('移动编辑, 待复习')
  expect(await page.locator('.record-editor').evaluate((node) => node.scrollWidth <= node.clientWidth)).toBeTruthy()
  await page.screenshot({ path: resolve(root, '.cache/browser/note-editor-mobile.png') })
  await page.getByRole('button', { name: '保存修改', exact: true }).click()
  await expect(page.locator('.record-editor')).toHaveCount(0)
  await expect(page.getByLabel('笔记标签')).toContainText('移动编辑')
})

test('confirmed deletion clears that record editing draft and pending save', async ({ page, request }) => {
  const item = await makeRecord(request, 'knowledge')
  await page.goto('/#/knowledge')
  await openEditor(page, 'knowledge', item.title)
  await page.getByLabel('笔记正文', { exact: true }).fill('删除前的本地编辑内容，在确认删除以后也需要从本页清理。')
  await page.route(`**/api/knowledge/${item.id}`, async (route) => {
    if (route.request().method() !== 'PATCH') return route.continue()
    await route.fetch()
    await route.abort()
  })
  await page.getByRole('button', { name: '保存修改', exact: true }).click()
  await expect(page.getByRole('button', { name: '确认上次保存', exact: true })).toBeVisible()
  await page.getByRole('button', { name: '关闭，保留草稿', exact: true }).click()
  const scope = `edit:knowledge:${item.id}`
  const saved = () => page.evaluate((scope) => Object.keys(localStorage).some((key) => key.includes(scope)), scope)
  expect(await saved()).toBeTruthy()
  page.once('dialog', (dialog) => dialog.accept())
  await page.getByRole('button', { name: `删除笔记 ${item.title}`, exact: true }).click()
  await expect(page.getByText('笔记已删除。', { exact: true })).toBeVisible()
  await expect(page.getByLabel('待确认的操作')).toHaveCount(0)
  expect(await saved()).toBeFalsy()
  expect((await request.get(`${api}/knowledge/${item.id}`)).status()).toBe(404)
})

test('tagging a short imported document preserves its existing title and body', async ({ page, request }) => {
  const response = await request.post(`${api}/knowledge/import`, { multipart: {
    file: { name: 'X.md', mimeType: 'text/markdown', buffer: Buffer.from('短文') },
  } })
  expect(response.ok()).toBeTruthy()
  const item = await response.json()
  await page.goto('/#/knowledge')
  await openEditor(page, 'knowledge', item.title)
  await page.getByLabel('标签', { exact: true }).fill('简短资料')
  await page.getByRole('button', { name: '保存修改', exact: true }).click()
  await expect(page.locator('.record-editor')).toHaveCount(0)
  const saved = await (await request.get(`${api}/knowledge/${item.id}`)).json()
  expect(saved.title).toBe('X')
  expect(saved.content).toBe('短文')
  expect(saved.tags).toEqual(['简短资料'])
  expect(saved.original).toEqual({ title: 'X', content: '短文' })
})
