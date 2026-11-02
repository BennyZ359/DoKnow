import { test, expect, type APIRequestContext } from '@playwright/test'
import { execFileSync } from 'node:child_process'
import { resolve } from 'node:path'

const root = resolve(import.meta.dirname, '../..')
const python = resolve(root, 'backend/.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python')
const api = 'http://127.0.0.1:8001/api'
const reflection = '变量让名字指向一个值，数字和字符串的用途不同，应先确认类型，再用实际计算检验自己的理解。'

async function makeGoal(request: APIRequestContext) {
  const response = await request.post(`${api}/goals`, { data: { title: `Python 可靠性 ${crypto.randomUUID()}` } })
  expect(response.ok()).toBeTruthy()
  return response.json()
}

test('drafts survive navigation and reload; only the successfully submitted stage is cleared', async ({ page, request }) => {
  const goal = await makeGoal(request)
  const [first, second] = goal.units
  await page.goto(`/#/learn/${first.id}`)
  await page.locator('#learn-reflection').fill(reflection)
  await page.getByLabel('向导师提问').fill('这是尚未发送的导师问题。')
  await page.locator('.unit-nav').filter({ hasText: second.title }).click()
  await page.locator('#learn-reflection').fill('第二个单元自己的草稿，切换回来时不能被第一个单元的文字覆盖。')
  await page.locator('.unit-nav').filter({ hasText: first.title }).click()
  await expect(page.locator('#learn-reflection')).toHaveValue(reflection)
  await page.reload()
  await expect(page.locator('#learn-reflection')).toHaveValue(reflection)
  await expect(page.getByLabel('向导师提问')).toHaveValue('这是尚未发送的导师问题。')
  await page.route(`**/api/units/${first.id}/learn`, (route) => route.fulfill({ status: 503, json: { detail: '暂时无法记录' } }))
  await page.getByRole('button', { name: '记录理解，进入练习' }).click()
  await expect(page.locator('main .alert.error')).toContainText('暂时无法记录')
  await expect(page.locator('#learn-reflection')).toHaveValue(reflection)
  await page.unroute(`**/api/units/${first.id}/learn`)
  await page.getByRole('button', { name: '记录理解，进入练习' }).click()
  await expect(page.locator('.assessment-feedback')).toContainText('已记录你的理解')
  await expect(page.locator('#learn-reflection')).toHaveValue('')
  await expect(page.getByLabel('向导师提问')).toHaveValue('这是尚未发送的导师问题。')
  await page.locator('.unit-nav').filter({ hasText: second.title }).click()
  await expect(page.locator('#learn-reflection')).toHaveValue('第二个单元自己的草稿，切换回来时不能被第一个单元的文字覆盖。')
})

test('a saved submission remains successful when the follow-up reads fail', async ({ page, request }) => {
  const goal = await makeGoal(request)
  const id = goal.units[0].id
  await page.goto(`/#/learn/${id}`)
  await page.locator('#learn-reflection').fill(reflection)
  let saved = false
  await page.route('**/api/dashboard', (route) => saved ? route.abort() : route.continue())
  await page.route(`**/api/units/${id}`, (route) => saved ? route.abort() : route.continue())
  await page.route(`**/api/units/${id}/learn`, async (route) => {
    const response = await route.fetch()
    expect(response.ok()).toBeTruthy()
    saved = true
    await route.fulfill({ response })
  })
  await page.getByRole('button', { name: '记录理解，进入练习' }).click()
  await expect(page.locator('.assessment-feedback')).toContainText('已记录你的理解')
  await expect(page.getByText('提交已保存，部分记录暂未同步。可以稍后同步最新记录。')).toBeVisible()
  await expect(page.locator('.alert.error')).toHaveCount(0)
  await expect(page.getByRole('button', { name: '记录理解，进入练习' })).toHaveCount(0)
  await page.getByRole('button', { name: '进入检验理解' }).click()
  await expect(page.getByText('能理解，也能辨别', { exact: true })).toBeVisible()
  saved = false
  await page.getByRole('button', { name: '同步最新记录', exact: true }).click()
  await expect(page.getByText('提交已保存，部分记录暂未同步。可以稍后同步最新记录。')).toHaveCount(0)
  const unit = await (await request.get(`${api}/units/${id}`)).json()
  expect(unit.sessions.filter((session: { kind: string }) => session.kind === 'learn')).toHaveLength(1)
})

test('a lost note response can be confirmed after reload without creating a duplicate', async ({ page, request }) => {
  const title = `响应恢复 ${crypto.randomUUID()}`
  const content = '这是已经写到数据库、但浏览器没有收到成功响应的笔记。'
  const keys: string[] = []
  page.on('request', (request) => {
    if (request.method() === 'POST' && request.url().endsWith('/api/knowledge')) keys.push(request.headers()['idempotency-key'])
  })
  await page.goto('/#/knowledge')
  await page.getByRole('button', { name: '写一篇笔记' }).click()
  await page.getByLabel('笔记标题', { exact: true }).fill(title)
  await page.getByLabel('笔记内容', { exact: true }).fill(content)
  await page.route('**/api/knowledge', async (route) => {
    if (route.request().method() !== 'POST') return route.continue()
    const response = await route.fetch()
    expect(response.ok()).toBeTruthy()
    await route.abort()
  })
  await page.getByRole('button', { name: '存入知识库', exact: true }).click()
  await expect(page.getByLabel('待确认的操作')).toBeVisible()
  await page.unroute('**/api/knowledge')
  await page.reload()
  await expect(page.getByLabel('笔记标题', { exact: true })).toHaveValue(title)
  await page.getByRole('button', { name: '确认上次操作', exact: true }).click()
  await expect(page.getByLabel('待确认的操作')).toHaveCount(0)
  await expect(page.getByRole('heading', { name: title, exact: true })).toHaveCount(1)
  expect(keys).toHaveLength(2)
  expect(keys[1]).toBe(keys[0])
  let notes = await (await request.get(`${api}/knowledge`)).json()
  expect(notes.filter((note: { title: string }) => note.title === title)).toHaveLength(1)
  // A later deliberate operation gets a fresh key even with identical text.
  await page.getByRole('button', { name: '写一篇笔记' }).click()
  await page.getByLabel('笔记标题', { exact: true }).fill(title)
  await page.getByLabel('笔记内容', { exact: true }).fill(content)
  await page.getByRole('button', { name: '存入知识库', exact: true }).click()
  await expect(page.getByRole('heading', { name: title, exact: true })).toHaveCount(2)
  expect(keys[2]).not.toBe(keys[0])
  notes = await (await request.get(`${api}/knowledge`)).json()
  expect(notes.filter((note: { title: string }) => note.title === title)).toHaveLength(2)
})

test('a lost file import response reuses its key when the same file is selected after reload', async ({ page, request }) => {
  const filename = `文件恢复-${crypto.randomUUID()}.md`
  const file = { name: filename, mimeType: 'text/markdown', buffer: Buffer.from('# 导入恢复\n资料先保存再丢失响应，重新选择同一文件应该只确认原有记录。') }
  const keys: string[] = []
  page.on('request', (request) => {
    if (request.url().endsWith('/api/knowledge/import')) keys.push(request.headers()['idempotency-key'])
  })
  await page.goto('/#/knowledge')
  await page.route('**/api/knowledge/import', async (route) => {
    const response = await route.fetch()
    expect(response.ok()).toBeTruthy()
    await route.abort()
  })
  await page.getByLabel('导入学习资料').setInputFiles(file)
  await expect(page.getByLabel('待确认的操作')).toBeVisible()
  await page.unroute('**/api/knowledge/import')
  await page.reload()
  await page.getByLabel('导入学习资料').setInputFiles(file)
  await expect(page.getByLabel('待确认的操作')).toHaveCount(0)
  expect(keys).toHaveLength(2)
  expect(keys[0]).toBe(keys[1])
  const notes = await (await request.get(`${api}/knowledge`)).json()
  expect(notes.filter((note: { source: string }) => note.source === filename)).toHaveLength(1)
})

test('an open review page unlocks and updates the navigation count when the review becomes due', async ({ page, request }) => {
  const goal = await makeGoal(request)
  const id = goal.units[0].id
  execFileSync(python, ['-c',
    "import sqlite3,sys; from datetime import datetime,timedelta,timezone; db=sqlite3.connect(sys.argv[1]); due=(datetime.now(timezone.utc)+timedelta(seconds=5)).replace(tzinfo=None).isoformat(' '); db.execute(\"UPDATE units SET stage='review',review_due_at=? WHERE id=?\", (due,sys.argv[2])); db.commit(); db.close()",
    process.env.DOKNOW_TEST_DB!, id,
  ])
  await page.goto(`/#/learn/${id}`)
  await expect(page.getByRole('heading', { name: '让知识在时间里留下来', exact: true })).toBeVisible()
  await expect(page.getByRole('heading', { name: '不看笔记，先试着回忆', exact: true })).toBeVisible({ timeout: 12_000 })
  await expect(page.locator('#review-answer')).toBeEnabled()
  await expect(page.locator('.nav-count')).toBeVisible()
  await page.getByRole('button', { name: '温故知新', exact: false }).click()
  await expect(page.locator('.review-list')).toContainText(goal.title)
})

test('two tabs retain their own in-progress drafts after another tab edits and both reload', async ({ page, context, request }) => {
  const goal = await makeGoal(request)
  const id = goal.units[0].id
  await page.goto(`/#/learn/${id}`)
  await page.locator('#learn-reflection').fill('第一个页面正在思考的文字，不能被另一个页面的修改抹掉。')
  const other = await context.newPage()
  await other.goto(`/#/learn/${id}`)
  await expect(other.locator('#learn-reflection')).toHaveValue('第一个页面正在思考的文字，不能被另一个页面的修改抹掉。')
  await other.locator('#learn-reflection').fill('第二个页面独立修改的草稿，也要在刷新之后被完整保留。')
  await expect(page.locator('#learn-reflection')).toHaveValue('第一个页面正在思考的文字，不能被另一个页面的修改抹掉。')
  await page.reload()
  await other.reload()
  await expect(page.locator('#learn-reflection')).toHaveValue('第一个页面正在思考的文字，不能被另一个页面的修改抹掉。')
  await expect(other.locator('#learn-reflection')).toHaveValue('第二个页面独立修改的草稿，也要在刷新之后被完整保留。')
  await other.close()
})

test('blocked browser storage leaves typed drafts usable and warns about reload limits', async ({ page, request }) => {
  const goal = await makeGoal(request)
  const [first, second] = goal.units
  const errors: string[] = []
  page.on('pageerror', (error) => errors.push(error.message))
  await page.addInitScript(() => {
    Storage.prototype.setItem = () => { throw new DOMException('Storage unavailable', 'QuotaExceededError') }
  })
  await page.goto(`/#/learn/${first.id}`)
  await page.locator('#learn-reflection').fill(reflection)
  await expect(page.getByText(/浏览器暂时无法完整保存草稿/)).toBeVisible()
  await page.locator('.unit-nav').filter({ hasText: second.title }).click()
  await page.locator('.unit-nav').filter({ hasText: first.title }).click()
  await expect(page.locator('#learn-reflection')).toHaveValue(reflection)
  expect(errors).toEqual([])
})

test('a successful write queues a fresh sync behind an older background read', async ({ page, request }) => {
  const goal = await makeGoal(request)
  const id = goal.units[0].id
  await page.goto(`/#/learn/${id}`)
  await page.locator('#learn-reflection').fill(reflection)
  await page.clock.install()
  let started!: () => void
  let release!: () => void
  const received = new Promise<void>((resolve) => { started = resolve })
  const delayed = new Promise<void>((resolve) => { release = resolve })
  let first = true
  await page.route(`**/api/units/${id}`, async (route) => {
    if (!first) return route.continue()
    first = false
    const stale = await route.fetch()
    started()
    await delayed
    await route.fulfill({ response: stale })
  })
  await page.clock.fastForward(30_001)
  await received
  await page.getByRole('button', { name: '记录理解，进入练习' }).click()
  await expect(page.locator('.assessment-feedback')).toContainText('已记录你的理解')
  release()
  await expect(page.locator('.session-history summary')).toContainText('1 条记录')
  await expect(page.getByRole('button', { name: '进入检验理解' })).toBeVisible()
  await expect(page.getByRole('button', { name: '记录理解，进入练习' })).toHaveCount(0)
})

test('a response body that stalls after its headers times out and leaves a confirmable write', async ({ page, request }) => {
  const goal = await makeGoal(request)
  const id = goal.units[0].id
  await page.addInitScript(({ unitId }) => {
    const originalFetch = window.fetch
    window.fetch = async (input, options) => {
      const response = await originalFetch(input, options)
      if (String(input).endsWith(`/units/${unitId}/learn`) && options?.method === 'POST') {
        const stream = new ReadableStream({
          start(controller) {
            controller.enqueue(new TextEncoder().encode('{"unit":'))
            options.signal?.addEventListener('abort', () => controller.error(new DOMException('Aborted', 'AbortError')), { once: true })
          },
        })
        return new Response(stream, { status: response.status, headers: response.headers })
      }
      return response
    }
  }, { unitId: id })
  await page.clock.install()
  await page.goto(`/#/learn/${id}`)
  await page.locator('#learn-reflection').fill(reflection)
  const committed = page.waitForResponse((response) => response.url().endsWith(`/units/${id}/learn`))
  await page.getByRole('button', { name: '记录理解，进入练习' }).click()
  await committed
  await page.clock.fastForward(90_001)
  await expect(page.locator('main .alert.error')).toContainText('操作结果尚未确认')
  await expect(page.getByRole('button', { name: '确认上次操作', exact: true })).toBeEnabled()
  await expect(page.locator('#learn-reflection')).toHaveValue(reflection)
})

test('deleting a goal removes its drafts and unconfirmed local operations', async ({ page, request }) => {
  const goal = await makeGoal(request)
  const [first, second] = goal.units
  await page.goto(`/#/learn/${first.id}`)
  await page.locator('#learn-reflection').fill(reflection)
  await page.locator('.unit-nav').filter({ hasText: second.title }).click()
  await page.locator('#learn-reflection').fill('第二个单元等待清理的本地草稿。')
  await page.route(`**/api/units/${second.id}/chat`, (route) => route.fulfill({ status: 503, json: { detail: '暂时无法回复' } }))
  await page.getByLabel('向导师提问').fill('这是待确认的导师交流内容。')
  await page.getByRole('button', { name: '一起思考', exact: true }).click()
  await expect(page.getByLabel('待确认的操作')).toBeVisible()
  await page.getByRole('button', { name: '学习概览', exact: true }).click()
  page.on('dialog', (dialog) => dialog.accept())
  await page.getByRole('button', { name: `删除目标 ${goal.title}`, exact: true }).click()
  await expect(page.getByLabel('待确认的操作')).toHaveCount(0)
  const remaining = await page.evaluate((ids: string[]) => {
    return [localStorage, sessionStorage].flatMap((storage) => Object.entries(storage).filter(([key, value]) =>
      key.startsWith('doknow:v1:') && ids.some((id) => key.includes(`unit:${id}:`) || value.includes(`unit:${id}:`))
    ))
  }, goal.units.map((unit: { id: string }) => unit.id))
  expect(remaining).toEqual([])
})

test('corrupt recovery metadata cannot turn confirmation into a new write', async ({ page }) => {
  const key = crypto.randomUUID()
  await page.addInitScript(({ receiptKey }) => {
    const entry = { key: receiptKey, scope: 'note', path: '/knowledge', label: '损坏的恢复记录', fingerprint: 'corrupted', payload: { title: '不应写入', content: '这份恢复记录的内容与原始指纹已经不一致。' } }
    localStorage.setItem(`doknow:v1:write:${receiptKey}`, JSON.stringify(entry))
  }, { receiptKey: key })
  let writes = 0
  page.on('request', (request) => { if (request.method() === 'POST') writes++ })
  await page.goto('/#/knowledge')
  await page.getByRole('button', { name: '确认上次操作', exact: true }).click()
  await expect(page.locator('main .alert.error')).toContainText('恢复记录已损坏')
  await expect(page.getByLabel('待确认的操作')).toContainText('损坏的恢复记录')
  expect(writes).toBe(0)
})
