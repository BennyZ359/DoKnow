import { test, expect } from '@playwright/test'
import { resolve } from 'node:path'
import { readFileSync } from 'node:fs'

const output = resolve(import.meta.dirname, '../../.cache/browser')
async function create(request: any, topic = '机器学习') {
  const response = await request.post('/api/graphs', { data: { topic } })
  expect(response.ok()).toBeTruthy()
  return response.json()
}

test('single topic builds a semantic entity graph, saves it, restores it and exports assertions', async ({ page }) => {
  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  await page.goto('/')
  await page.getByLabel('你想学什么？', { exact: true }).fill('机器学习')
  await page.getByRole('button', { name: '构建知识图谱', exact: true }).click()
  await expect(page.locator('.concept-network')).toHaveAttribute('data-ready', 'true')
  await expect(page.locator('.concept-network')).toHaveAttribute('data-entity-count', '31')
  await expect(page.locator('.concept-network')).toHaveAttribute('data-relation-count', '45')
  await expect(page.getByLabel('显示优化关系')).toBeChecked()
  await expect(page.getByLabel('显示依赖关系')).toBeChecked()
  await expect(page.locator('.map-node')).toHaveCount(0)
  await page.evaluate(() => window.scrollTo(0, 0))
  await page.screenshot({ path: resolve(output, 'concept-network-desktop.png'), fullPage: true })
  const id = page.url().split('/').pop()!
  const downloadEvent = page.waitForEvent('download')
  await page.getByRole('button', { name: '导出图数据' }).click()
  const download = await downloadEvent
  const file = resolve(output, 'exported-graph.json')
  await download.saveAs(file)
  const saved = JSON.parse(readFileSync(file, 'utf8'))
  expect(saved.relations.filter((edge: any) => edge.kind === 'optimizes').length).toBeGreaterThan(0)
  expect(saved.entities).toHaveLength(31)
  await page.reload()
  await expect(page.locator('.concept-network')).toHaveAttribute('data-entity-count', '31')
  await page.getByRole('button', { name: '探索新的主题' }).click()
  await page.locator('.kg-history > div button').filter({ hasText: '机器学习' }).first().click()
  await expect(page).toHaveURL(new RegExp(id + '$'))
  expect(errors).toEqual([])
})

test('alias search, explicit relationship detail, neighbor query, expansion and shortest path work', async ({ page, request }) => {
  const graph = await create(request)
  const ids = Object.fromEntries(graph.entities.map((node: any) => [node.key, node.id]))
  await page.goto(`/#/map/${graph.id}`)
  await page.getByLabel('搜索知识实体或别名').fill('GD')
  await expect(page.locator('.kg-results button')).toHaveCount(1)
  await page.locator('.kg-results button').click()
  await expect(page.locator('.kg-detail h3')).toHaveText('梯度下降')
  await page.locator('.kg-assertions button').filter({ hasText: '损失函数' }).click()
  await expect(page.locator('.kg-triple')).toContainText('优化')
  await expect(page.locator('.kg-detail')).toContainText('梯度下降以减小损失函数值为优化目标')
  await page.getByRole('button', { name: '返回实体', exact: true }).click()
  const neighborCall = page.waitForResponse(response => response.url().includes(`/neighbors/${ids['gradient-descent']}`))
  await page.getByRole('button', { name: '聚焦一度关系' }).click()
  await neighborCall
  await expect(page.locator('.concept-network')).toHaveAttribute('data-entity-count', '5')
  await page.getByLabel('搜索知识实体或别名').fill('梯度')
  await expect(page.locator('.kg-results button')).toHaveCount(2)
  await page.locator('.kg-results button').filter({ hasText: /^梯度概念/ }).click()
  await page.getByRole('button', { name: /展开邻居 \+1/ }).click()
  await expect(page.locator('.concept-network')).toHaveAttribute('data-entity-count', '6')
  await page.getByLabel('搜索知识实体或别名').fill('GD')
  await expect(page.locator('.kg-results button')).toHaveCount(1)
  await page.locator('.kg-results button').click()
  await page.getByLabel('关联路径终点').selectOption(ids.derivative)
  await page.getByRole('button', { name: '查找关联路径' }).click()
  await expect(page.locator('.kg-path-result')).toContainText('2 跳')
  await expect(page.locator('.kg-path-result')).toContainText('梯度下降 —依赖→ 梯度')
  await expect(page.locator('.kg-path-result')).toContainText('梯度 —依赖→ 导数')
  await page.getByLabel('显示依赖关系').uncheck()
  await page.getByRole('button', { name: '查找关联路径' }).click()
  await expect(page.locator('.kg-path-result')).toContainText('没有关联路径')
})

test('network canvas selects and drags actual entities, supports pan and relation filtering', async ({ page, request }) => {
  const graph = await create(request, 'Python')
  await page.goto(`/#/map/${graph.id}`)
  await expect(page.locator('.concept-network')).toHaveAttribute('data-ready', 'true')
  await page.locator('.concept-network').scrollIntoViewIfNeeded()
  const id = graph.entities.find((node: any) => node.key === 'function').id
  const point = await page.locator('.concept-network').evaluate((element: any, id) => {
    const cy = element._cyreg.cy
    const position = cy.$id(id).renderedPosition()
    const box = element.getBoundingClientRect()
    return { x: box.x + position.x, y: box.y + position.y }
  }, id)
  await page.mouse.click(point.x, point.y)
  await expect(page.locator('.kg-detail h3')).toHaveText('函数')
  await page.mouse.move(point.x, point.y)
  await page.mouse.down()
  await page.mouse.move(point.x + 35, point.y + 25, { steps: 8 })
  await page.mouse.up()
  const after = await page.locator('.concept-network').evaluate((element: any, id) => element._cyreg.cy.$id(id).renderedPosition(), id)
  const box = await page.locator('.concept-network').boundingBox()
  expect(Math.abs(after.x + box!.x - point.x)).toBeGreaterThan(15)
  await page.getByLabel('显示使用关系').uncheck()
  await expect(page.locator('.concept-network')).not.toHaveAttribute('data-relation-count', String(graph.relation_count))
  await page.getByLabel('筛选实体类型').selectOption('tool')
  await expect(page.locator('.concept-network')).toHaveAttribute('data-entity-count', '1')
  await page.getByRole('button', { name: '恢复全图', exact: true }).click()
  await expect(page.locator('.concept-network')).toHaveAttribute('data-entity-count', String(graph.entity_count))
})

test('old course maps are explicitly identified and can be rebuilt into semantic data', async ({ page, request }) => {
  const old = await (await request.post('/api/roadmaps', { data: { topic: 'Python' } })).json()
  await page.goto(`/#/map/${old.id}`)
  await expect(page.locator('.kg-legacy')).toContainText('上一版课程路线')
  await expect(page.getByLabel('你想学什么？', { exact: true })).toHaveValue('Python')
  await page.getByRole('button', { name: '构建知识图谱', exact: true }).click()
  await expect(page.locator('.concept-network')).toHaveAttribute('data-entity-count', '13')
  await expect(page).not.toHaveURL(new RegExp(old.id + '$'))
})

test('lost graph creation responses are restored once after reload', async ({ page, request }) => {
  const before = (await (await request.get('/api/graphs')).json()).length
  let intercepted = false
  await page.route('**/api/graphs', async route => {
    if (route.request().method() !== 'POST' || intercepted) return route.continue()
    intercepted = true
    await route.fetch()
    await route.abort()
  })
  await page.goto('/')
  await page.getByLabel('你想学什么？', { exact: true }).fill('AI Agent')
  await page.getByRole('button', { name: '构建知识图谱', exact: true }).click()
  await expect(page.getByRole('button', { name: '确认上次操作', exact: true })).toBeVisible()
  await page.reload()
  await page.getByRole('button', { name: '确认上次操作', exact: true }).click()
  await expect(page.locator('.concept-network')).toHaveAttribute('data-entity-count', '16')
  expect((await (await request.get('/api/graphs')).json()).length).toBe(before + 1)
})

test('unknown subjects preserve input and mobile exploration remains accessible', async ({ page, request }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/')
  await page.getByLabel('你想学什么？', { exact: true }).fill('古典吉他')
  await page.getByRole('button', { name: '构建知识图谱', exact: true }).click()
  await expect(page.getByRole('alert')).toContainText('暂未收录')
  await expect(page.getByLabel('你想学什么？', { exact: true })).toHaveValue('古典吉他')
  const graph = await create(request, '前端开发')
  await page.goto(`/#/map/${graph.id}`)
  await expect(page.locator('.concept-network')).toHaveAttribute('data-ready', 'true')
  await page.getByRole('button', { name: '实体与关系', exact: true }).click()
  await page.locator('.kg-entity-list button').filter({ hasText: /^HTML/ }).focus()
  await page.keyboard.press('Enter')
  await expect(page.locator('.kg-detail h3')).toHaveText('HTML')
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await page.getByRole('button', { name: '关系网络', exact: true }).click()
  await page.evaluate(() => window.scrollTo(0, 0))
  await page.screenshot({ path: resolve(output, 'concept-network-mobile.png'), fullPage: true })
})

test('late neighbor results cannot replace the neighborhood of a newly selected concept', async ({ page, request }) => {
  const graph = await create(request)
  let release!: () => void
  let entered!: () => void
  const gate = new Promise<void>(resolve => { release = resolve })
  const started = new Promise<void>(resolve => { entered = resolve })
  await page.route(`**/api/graphs/${graph.id}/neighbors/**`, async route => {
    entered()
    await gate
    await route.continue()
  })
  await page.goto(`/#/map/${graph.id}`)
  await page.getByRole('button', { name: '聚焦一度关系' }).click()
  await started
  await page.getByLabel('搜索知识实体或别名').fill('GD')
  await expect(page.locator('.kg-results button')).toHaveCount(1)
  await page.locator('.kg-results button').click()
  const response = page.waitForResponse(response => response.url().includes('/neighbors/'))
  release()
  await response
  await expect(page.locator('.kg-detail h3')).toHaveText('梯度下降')
  await expect(page.locator('.concept-network')).toHaveAttribute('data-entity-count', '31')
})

test('a late graph creation saves to history without stealing navigation', async ({ page }) => {
  let release!: () => void
  let entered!: () => void
  const gate = new Promise<void>(resolve => { release = resolve })
  const started = new Promise<void>(resolve => { entered = resolve })
  await page.route('**/api/graphs', async route => {
    if (route.request().method() !== 'POST') return route.continue()
    entered()
    await gate
    await route.continue()
  })
  await page.goto('/')
  await page.getByLabel('你想学什么？', { exact: true }).fill('Python 异步知识图谱')
  await page.getByRole('button', { name: '构建知识图谱', exact: true }).click()
  await started
  await page.getByRole('button', { name: '学习概览', exact: true }).click()
  const response = page.waitForResponse(response => response.url().endsWith('/api/graphs') && response.request().method() === 'POST')
  release()
  await response
  await expect(page).toHaveURL(/#\/dashboard$/)
  await page.getByRole('navigation', { name: '主要导航' }).getByRole('button', { name: '知识图谱', exact: true }).click()
  await expect(page.locator('.kg-history')).toContainText('Python 异步知识图谱')
})
