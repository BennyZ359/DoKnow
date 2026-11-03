import { test, expect } from '@playwright/test'
import { execFileSync } from 'node:child_process'
import { resolve } from 'node:path'

const root = resolve(import.meta.dirname, '../..')
const python = resolve(root, 'backend/.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python')

function makeDue(id: string) {
  // Change only the isolated browser-test database; never expose a time-travel API.
  execFileSync(python, ['-c',
    "import sqlite3,sys; db=sqlite3.connect(sys.argv[1]); db.execute('UPDATE units SET review_due_at=? WHERE id=?', ('2020-01-01 00:00:00.000000',sys.argv[2])); db.commit(); db.close()",
    process.env.DOKNOW_TEST_DB!, id,
  ])
}

test('learning evidence, wrong answer, teach-back, reflection and delayed recall survive refresh', async ({ page }) => {
  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  await page.goto('/#/dashboard')
  await expect(page.getByRole('heading', { name: /让知识生根/ })).toBeVisible()
  await page.getByRole('button', { name: '新建学习目标', exact: true }).click()
  await page.getByLabel('我的学习目标', { exact: true }).fill('学习 Python 基础 · 浏览器验证')
  await page.locator('#goal-motivation').fill('写购物总价程序，并能解释变量和类型。')
  await page.getByRole('button', { name: '生成我的学习路线' }).click()
  await expect(page.getByRole('heading', { name: 'Python 变量与数据类型', exact: true })).toBeVisible()
  const id = page.url().split('/').pop()!
  await page.getByLabel('向导师提问').fill('我不理解字符串与数字有什么区别，能引导我验证吗？')
  await page.getByRole('button', { name: '一起思考', exact: true }).click()
  await expect(page.locator('.tutor-reply')).toContainText('体验导师')
  await page.getByLabel('用自己的话，说说你的理解').fill('变量让名字指向一个值，字符串和整数有不同用途，我需要先转换类型，再通过实际计算验证。')
  await page.getByRole('button', { name: '记录理解，进入练习' }).click()
  await page.getByRole('button', { name: '进入检验理解' }).click()
  await page.getByRole('radio', { name: "'3' + 2" }).check()
  await page.getByRole('button', { name: '提交答案', exact: true }).click()
  await expect(page.getByText('再想一想，再试一次', { exact: true })).toBeVisible()
  for (const [index, answer] of ["int('4') * 3", '捕获转换错误并提示输入有效数字', "int('3') + 2"].entries()) {
    await page.getByRole('radio', { name: answer }).check()
    await page.getByRole('button', { name: '提交答案', exact: true }).click()
    await expect(page.locator('.practice-progress')).toContainText(`已通过 ${index + 1} / 3 题`)
  }
  await page.locator('.session-history summary').click()
  await page.getByLabel('筛选学习足迹').selectOption('mistakes')
  await expect(page.locator('.session-history article')).toHaveCount(1)
  await expect(page.locator('.session-history article')).toContainText('服务端 · 答案核对')
  await expect(page.locator('.session-history article')).toContainText("'3' + 2")
  await page.getByLabel('筛选学习足迹').selectOption('all')
  await page.locator('.session-history summary').click()
  await page.getByRole('button', { name: '进入真实问题' }).click()
  await page.locator('#project-content').fill('我写了购物程序：price = 12，count = 3，print(price * count)。输入条件是单价12元和数量3个，预测结果36元，实际运行输出36。边界测试数量0，结果0；输入字符串必须先int转换，无效输入“三”会产生错误，需要提示重试。')
  await page.getByRole('button', { name: /提交.*实战|检验.*实践|提交.*实践/ }).click()
  await expect(page.locator('.assessment-feedback')).toContainText('体验 · 结构检查')
  await expect(page.locator('.assessment-feedback')).toContainText('structure-v1')
  await page.getByRole('button', { name: '进入教会别人' }).click()
  await page.locator('#teach-content').fill('变量是指向值的名字，例如price保存整数12，count保存整数3，计算price * count得到36。因为数字可以做算术，而字符串主要表示文本，所以int("3") + 2输出5。注意字符串拼接与数字相加不同，int("三")不能转换，边界和错误输入要单独测试，不能认为任何文本都能变成数字。')
  await page.getByRole('button', { name: '检验我的讲解', exact: true }).click()
  await page.getByRole('button', { name: '进入复盘沉淀' }).click()
  await page.locator('#reflection-content').fill('实际运行购物程序后，我发现字符串与数字的行为不同，先预测再运行暴露了原来的理解缺口。')
  await page.locator('#reflection-takeaway').fill('计算之前先确认类型，用正常与边界输入验证结果。')
  await page.locator('#reflection-change').fill('我以前只背定义，现在会主动设计输入和错误案例来检查理解。')
  await page.getByRole('button', { name: '保存复盘，安排回看' }).click()
  await page.getByRole('button', { name: '进入间隔回看' }).click()
  await expect(page.getByRole('heading', { name: '让知识在时间里留下来' })).toBeVisible()
  await page.reload()
  await expect(page.getByRole('heading', { name: '让知识在时间里留下来' })).toBeVisible()
  makeDue(id)
  await page.reload()
  await page.locator('#review-answer').fill('变量让名字引用值，字符串用于文本，整数可算术。例如int("3") + 2得到5，因为转换后两边都是数字；如果输入不能转换，如“三”，会错误，需要先检查输入条件与边界。')
  await page.getByRole('button', { name: '完成这次回看' }).click()
  await expect(page.locator('.assessment-feedback')).toContainText('本轮主动回忆已完成')
  await page.getByRole('button', { name: '知识沉淀', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Python 变量与数据类型 · 学习沉淀', exact: true })).toBeVisible()
  await page.getByRole('button', { name: '学习概览', exact: true }).click()
  await page.screenshot({ path: resolve(root, '.cache/browser/dashboard.png'), fullPage: true })
  expect(errors).toEqual([])
})

test('late tutor response cannot overwrite a newly selected learning unit', async ({ page, request }) => {
  const response = await request.post('http://127.0.0.1:8001/api/goals', { data: { title: 'Python 异步导航验证' } })
  const goal = await response.json()
  const [first, second] = goal.units
  let received!: () => void
  let release!: () => void
  const started = new Promise<void>(resolve => { received = resolve })
  const delayed = new Promise<void>(resolve => { release = resolve })
  await page.route(`**/api/units/${first.id}/chat`, async route => {
    received()
    await delayed
    await route.fulfill({ json: { reply: '这是上一个单元的旧回复', mode: 'demo' } })
  })
  await page.goto(`/#/learn/${first.id}`)
  await page.getByLabel('向导师提问').fill('请帮我思考这个例子')
  await page.getByRole('button', { name: '一起思考', exact: true }).click()
  await started
  await page.locator('.unit-nav').filter({ hasText: second.title }).click()
  await expect(page.getByRole('heading', { name: second.title, exact: true })).toBeVisible()
  release()
  await expect(page.getByRole('button', { name: '一起思考', exact: true })).toHaveText(/一起思考/)
  await expect(page.getByRole('heading', { name: second.title, exact: true })).toBeVisible()
  await expect(page.getByText('这是上一个单元的旧回复')).toHaveCount(0)
})

test('knowledge import, grounded answer, insufficient sources and mobile navigation', async ({ page }) => {
  await page.goto('/#/knowledge')
  await page.getByLabel('导入学习资料').setInputFiles({ name: '间隔学习.md', mimeType: 'text/markdown', buffer: Buffer.from('# 间隔学习\n主动回忆是先闭卷尝试提取知识，然后对照资料纠错。间隔复习使回忆经历时间检验。') })
  await expect(page.getByRole('heading', { name: '间隔学习', exact: true })).toBeVisible()
  await page.getByLabel('知识库问题').fill('什么是主动回忆？')
  await page.getByRole('button', { name: '寻找答案' }).click()
  await expect(page.locator('.source-card').filter({ hasText: '间隔学习' })).toBeVisible()
  await page.getByLabel('知识库问题').fill('银河系中心黑洞质量是多少？')
  await page.getByRole('button', { name: '寻找答案' }).click()
  await expect(page.getByText(/现有资料中没有找到/)).toBeVisible()
  await page.setViewportSize({ width: 390, height: 844 })
  await page.getByRole('button', { name: '打开导航' }).click()
  await page.getByRole('button', { name: '学习概览', exact: true }).click()
  await expect(page.getByRole('heading', { name: /让知识生根/ })).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy()
  await page.screenshot({ path: resolve(root, '.cache/browser/mobile.png'), fullPage: true })
})
