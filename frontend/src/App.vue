<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, reactive, ref } from 'vue'
import Icon from './components/Icon.vue'
import { api, post } from './api'
import type {
  Dashboard,
  FullUnit,
  Goal,
  KnowledgeAnswer,
  Note,
  Settings,
  Stage,
  Submission,
  Unit,
} from './api'

type View = 'dashboard' | 'learn' | 'reviews' | 'knowledge' | 'settings'
const stages: { key: Stage; label: string; subtitle: string; icon: string }[] = [
  { key: 'learn', label: '学', subtitle: '理解与思考', icon: 'book' },
  { key: 'practice', label: '练', subtitle: '检验理解', icon: 'target' },
  { key: 'project', label: '用', subtitle: '真实问题', icon: 'leaf' },
  { key: 'teach', label: '讲', subtitle: '教会别人', icon: 'message' },
  { key: 'reflect', label: '悟', subtitle: '复盘沉淀', icon: 'notes' },
  { key: 'review', label: '温', subtitle: '间隔回看', icon: 'repeat' },
]
const nav = [
  { view: 'dashboard' as View, label: '学习概览', icon: 'home' },
  { view: 'learn' as View, label: '我的学习', icon: 'book' },
  { view: 'reviews' as View, label: '温故知新', icon: 'repeat' },
  { view: 'knowledge' as View, label: '知识沉淀', icon: 'notes' },
]
const view = ref<View>('dashboard')
const mobileNav = ref(false)
const dashboard = ref<Dashboard>({
  goals: [],
  reviews_due: 0,
  total_sessions: 0,
  knowledge_count: 0,
  recent_activity: [],
})
const settings = ref<Settings | null>(null)
const reviews = ref<Unit[]>([])
const notes = ref<Note[]>([])
const unit = ref<FullUnit | null>(null)
const activeTab = ref<Stage>('learn')
const busy = ref('')
const loading = ref(true)
const error = ref('')
const notice = ref('')
const feedback = ref<Submission | null>(null)
const goalDialog = ref<HTMLDialogElement | null>(null)
const goalTitleInput = ref<HTMLInputElement | null>(null)
const goalForm = reactive({ title: '', motivation: '', level: 'beginner', daily_minutes: 30 })
const learnReflection = ref('')
const practiceAnswer = ref('')
const projectContent = ref('')
const teachContent = ref('')
const reflection = reactive({ content: '', takeaway: '', change: '' })
const recall = reactive({ answer: '', rating: 3 })
const chatMessage = ref('')
const chatReply = ref('')
const knowledgeQuery = ref('')
const knowledgeAnswer = ref<KnowledgeAnswer | null>(null)
const noteSearch = ref('')
const noteForm = reactive({ title: '', content: '' })
const showNoteForm = ref(false)
const selectedNote = ref<string | null>(null)
const uploadInput = ref<HTMLInputElement | null>(null)
const goals = computed(() => dashboard.value.goals)
const currentGoal = computed(() => goals.value.find((g) => g.id === unit.value?.goal_id))
const nextGoal = computed(
  () =>
    goals.value.find((g) => g.units.some((u) => u.stage !== 'complete' && u.stage !== 'review')) ||
    goals.value.find((g) => g.units.some((u) => u.stage !== 'complete')) ||
    goals.value[0]
)
const nextUnit = computed(() => (nextGoal.value ? goalNextUnit(nextGoal.value) : undefined))
const nextStudyUnit = computed(() =>
  goals.value
    .flatMap((g) => g.units)
    .find((u) => u.id !== unit.value?.id && u.stage !== 'complete' && u.stage !== 'review')
)
const completedUnits = computed(
  () => goals.value.flatMap((g) => g.units).filter((u) => u.stage === 'complete').length
)
const filteredNotes = computed(() =>
  notes.value.filter((n) =>
    `${n.title} ${n.content}`.toLocaleLowerCase().includes(noteSearch.value.toLocaleLowerCase())
  )
)
const stagePosition = computed(() =>
  unit.value?.stage === 'complete' ? 6 : stages.findIndex((s) => s.key === unit.value?.stage)
)
const reviewDue = computed(
  () => !!unit.value?.review_due_at && new Date(unit.value.review_due_at).getTime() <= Date.now()
)
const canSubmit = computed(
  () =>
    !!unit.value &&
    (activeTab.value === unit.value.stage ||
      (activeTab.value === 'review' && unit.value.stage === 'complete')) &&
    (activeTab.value !== 'review' || reviewDue.value)
)
const today = new Intl.DateTimeFormat('zh-CN', {
  month: 'long',
  day: 'numeric',
  weekday: 'long',
}).format(new Date())
const greeting =
  new Date().getHours() < 12 ? '上午好' : new Date().getHours() < 18 ? '下午好' : '晚上好'
let routeSequence = 0
let summarySequence = 0

const length = (text: string) => text.replace(/\s/g, '').length
const stageLabel = (stage: string) =>
  stage === 'complete'
    ? '已完成 · 持续复习'
    : stages.find((s) => s.key === stage)?.subtitle || stage
const date = (value: string | null | undefined, time = false) =>
  value
    ? new Intl.DateTimeFormat('zh-CN', {
        month: 'numeric',
        day: 'numeric',
        ...(time ? { hour: '2-digit', minute: '2-digit' } : {}),
      }).format(new Date(value))
    : '尚未安排'
const levelLabel = (level: string) =>
  ({ beginner: '初学者', intermediate: '有些基础', advanced: '进阶探索' })[level] || level
const activityLabel = (kind: string) =>
  ({
    learn: '记录理解',
    practice: '完成练习',
    project: '提交实战',
    teach: '讲解检验',
    reflect: '复盘沉淀',
    review: '回忆检验',
    chat: '与导师交流',
  })[kind] || '学习记录'
const goalNextUnit = (goal: Goal) =>
  goal.units.find((u) => u.stage !== 'complete' && u.stage !== 'review') ||
  goal.units.find((u) => u.stage !== 'complete') ||
  goal.units[0]
const skipToMain = () => document.getElementById('main')?.focus()

function navigate(target: View, id?: string) {
  mobileNav.value = false
  const hash = `#/${target}${id ? `/${id}` : ''}`
  if (location.hash === hash) void readRoute()
  else location.hash = hash
}

async function refreshSummary() {
  const request = ++summarySequence
  const result = await api<Dashboard>('/dashboard')
  if (request === summarySequence) dashboard.value = result
}

async function readRoute() {
  const sequence = ++routeSequence
  const parts = location.hash.replace(/^#\/?/, '').split('/')
  view.value = ['dashboard', 'learn', 'reviews', 'knowledge', 'settings'].includes(parts[0])
    ? (parts[0] as View)
    : 'dashboard'
  error.value = ''
  notice.value = ''
  loading.value = true
  try {
    await refreshSummary()
    if (sequence !== routeSequence) return
    if (view.value === 'learn') {
      const id = parts[1] || nextUnit.value?.id
      if (id) {
        if (unit.value?.id !== id) {
          clearStudyForm()
          unit.value = null
        }
        const response = await api<FullUnit>(`/units/${id}`)
        if (sequence !== routeSequence) return
        if (unit.value?.id !== id) clearStudyForm()
        unit.value = response
        activeTab.value = response.stage === 'complete' ? 'review' : response.stage
      } else unit.value = null
    }
    if (view.value === 'reviews') {
      const result = await api<Unit[]>('/reviews')
      if (sequence === routeSequence) reviews.value = result
    }
    if (view.value === 'knowledge') {
      const result = await api<Note[]>('/knowledge')
      if (sequence === routeSequence) notes.value = result
    }
    if (!settings.value || view.value === 'settings') {
      const result = await api<Settings>('/settings')
      if (sequence === routeSequence) settings.value = result
    }
  } catch (e) {
    if (sequence === routeSequence) error.value = (e as Error).message
  } finally {
    if (sequence === routeSequence) loading.value = false
  }
}

function clearStudyForm() {
  learnReflection.value = ''
  practiceAnswer.value = ''
  projectContent.value = ''
  teachContent.value = ''
  reflection.content = ''
  reflection.takeaway = ''
  reflection.change = ''
  recall.answer = ''
  recall.rating = 3
  chatMessage.value = ''
  chatReply.value = ''
  feedback.value = null
}

async function run(key: string, action: () => Promise<void>) {
  if (busy.value) return
  const sequence = routeSequence
  busy.value = key
  error.value = ''
  notice.value = ''
  try {
    await action()
  } catch (e) {
    if (sequence === routeSequence) error.value = (e as Error).message
  } finally {
    busy.value = ''
  }
}

async function openGoal() {
  error.value = ''
  goalDialog.value?.showModal()
  await nextTick()
  goalTitleInput.value?.focus()
}

async function createGoal() {
  const sequence = routeSequence
  await run('goal', async () => {
    const goal = await post<Goal>('/goals', goalForm)
    goalDialog.value?.close()
    goalForm.title = ''
    goalForm.motivation = ''
    if (sequence === routeSequence) navigate('learn', goal.units[0]?.id)
  })
}

async function submitStage() {
  if (!unit.value || !canSubmit.value) return
  const currentId = unit.value.id
  const currentStage = activeTab.value
  const sequence = routeSequence
  const bodies: Record<string, unknown> = {
    learn: { reflection: learnReflection.value },
    practice: { answer: practiceAnswer.value },
    project: { content: projectContent.value },
    teach: { content: teachContent.value },
    reflect: reflection,
    review: recall,
  }
  await run('submission', async () => {
    const result = await post<Submission>(
      `/units/${currentId}/${currentStage}`,
      bodies[currentStage]
    )
    const updated = await api<FullUnit>(`/units/${currentId}`)
    await refreshSummary()
    if (sequence !== routeSequence || unit.value?.id !== currentId) return
    feedback.value = result
    unit.value = updated
    if (result.passed === false) {
      if (unit.value.stage !== currentStage) activeTab.value = unit.value.stage
    } else notice.value = '这一步已记录。继续把理解变成能力。'
  })
}

async function sendChat() {
  if (!unit.value || !chatMessage.value.trim()) return
  const id = unit.value.id
  const sequence = routeSequence
  await run('chat', async () => {
    const answer = await post<{ reply: string; mode: string }>(`/units/${id}/chat`, {
      message: chatMessage.value,
    })
    const updated = await api<FullUnit>(`/units/${id}`)
    await refreshSummary()
    if (sequence !== routeSequence || unit.value?.id !== id) return
    chatReply.value = answer.reply
    chatMessage.value = ''
    unit.value = updated
  })
}

async function deleteGoal(goal: Goal) {
  if (!window.confirm(`删除「${goal.title}」及其学习记录？已经沉淀到知识库的笔记会保留。`)) return
  const sequence = routeSequence
  await run('delete', async () => {
    await api(`/goals/${goal.id}`, { method: 'DELETE' })
    await refreshSummary()
    if (sequence === routeSequence) notice.value = '学习目标已删除。'
  })
}

async function createNote() {
  const sequence = routeSequence
  await run('note', async () => {
    const result = await post<Note>('/knowledge', noteForm)
    const updated = await api<Note[]>('/knowledge')
    await refreshSummary()
    if (sequence !== routeSequence) return
    notes.value = updated
    selectedNote.value = result.id
    noteForm.title = ''
    noteForm.content = ''
    showNoteForm.value = false
    notice.value = '笔记已存入知识库。'
  })
}

async function importFile(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  const sequence = routeSequence
  if (!file) return
  if (file.size > 10 * 1024 * 1024) {
    error.value = '文件请控制在 10 MB 以内。'
    input.value = ''
    return
  }
  await run('import', async () => {
    const body = new FormData()
    body.append('file', file)
    const result = await api<Note>('/knowledge/import', { method: 'POST', body })
    const updated = await api<Note[]>('/knowledge')
    await refreshSummary()
    if (sequence !== routeSequence) return
    notes.value = updated
    selectedNote.value = result.id
    notice.value = `「${result.title}」已导入。`
  })
  input.value = ''
}

async function deleteNote(note: Note) {
  if (!window.confirm(`删除知识笔记「${note.title}」？`)) return
  const sequence = routeSequence
  await run('delete-note', async () => {
    await api(`/knowledge/${note.id}`, { method: 'DELETE' })
    await refreshSummary()
    if (sequence !== routeSequence) return
    notes.value = notes.value.filter((n) => n.id !== note.id)
    knowledgeAnswer.value = null
    notice.value = '笔记已删除。'
  })
}

async function askKnowledge() {
  const sequence = routeSequence
  const question = knowledgeQuery.value
  await run('ask', async () => {
    const result = await post<KnowledgeAnswer>('/knowledge/ask', { question })
    if (sequence === routeSequence && question === knowledgeQuery.value)
      knowledgeAnswer.value = result
  })
}

function selectTab(stage: Stage) {
  activeTab.value = stage
  feedback.value = null
  notice.value = ''
}
function nextStage() {
  if (unit.value) activeTab.value = unit.value.stage === 'complete' ? 'review' : unit.value.stage
  feedback.value = null
  notice.value = ''
}

onMounted(() => {
  window.addEventListener('hashchange', readRoute)
  void readRoute()
})
onUnmounted(() => {
  window.removeEventListener('hashchange', readRoute)
})
</script>

<template>
  <a href="#main" class="skip-link" @click.prevent="skipToMain">跳转到主要内容</a>
  <div class="app-shell">
    <aside class="sidebar" :class="{ 'is-open': mobileNav }">
      <a href="#/dashboard" class="brand" aria-label="DoKnow 首页"
        ><span class="brand-symbol">d<span>·</span></span
        ><span>DoKnow<small>知而后行 · 行而后知</small></span></a
      >
      <div class="sidebar-label">你的成长空间</div>
      <nav aria-label="主要导航">
        <button
          v-for="item in nav"
          :key="item.view"
          :class="['nav-item', { active: view === item.view }]"
          :aria-current="view === item.view ? 'page' : undefined"
          @click="navigate(item.view)"
        >
          <Icon :name="item.icon" /><span>{{ item.label }}</span
          ><span v-if="item.view === 'reviews' && dashboard.reviews_due" class="nav-count">{{
            dashboard.reviews_due
          }}</span>
        </button>
      </nav>
      <div class="sidebar-note">
        <Icon name="leaf" :size="24" />
        <p>知道，是起点。<br />做到，才是自己的。</p>
        <span>KNOW. DO. GROW.</span>
      </div>
      <button
        class="nav-item settings-nav"
        :class="{ active: view === 'settings' }"
        @click="navigate('settings')"
      >
        <Icon name="settings" /><span>理念与设置</span>
      </button>
      <div class="learner">
        <span class="avatar">知</span>
        <div>终身学习者<small>保持好奇，持续生长</small></div>
        <span class="learner-dot"></span>
      </div>
    </aside>
    <button
      v-if="mobileNav"
      class="nav-backdrop"
      aria-label="关闭导航"
      @click="mobileNav = false"
    ></button>
    <div class="main-shell">
      <header class="topbar">
        <button
          class="icon-button mobile-menu"
          aria-label="打开导航"
          @click="mobileNav = !mobileNav"
        >
          <Icon name="menu" />
        </button>
        <div class="breadcrumb">
          我的成长空间 <span>/</span>
          {{ view === 'settings' ? '理念与设置' : nav.find((n) => n.view === view)?.label }}
        </div>
        <span class="mode-badge"
          ><span></span
          >{{
            settings?.mode === 'demo'
              ? '体验模式'
              : settings?.configured
                ? 'AI 模型已配置'
                : 'AI 配置待完善'
          }}</span
        >
      </header>
      <main id="main" tabindex="-1">
        <div v-if="error" class="alert error" role="alert">
          <Icon name="message" /><span>{{ error }}</span
          ><button class="icon-button" aria-label="关闭错误提示" @click="error = ''">
            <Icon name="close" :size="17" />
          </button>
        </div>
        <div v-if="notice" class="alert success" role="status">
          <Icon name="check" /><span>{{ notice }}</span>
        </div>
        <div v-if="loading" class="loading-state" role="status">
          <span class="spinner"></span>正在整理你的学习空间…
        </div>

        <template v-else-if="view === 'dashboard'">
          <div class="page-heading">
            <div>
              <p class="eyebrow">{{ today }}</p>
              <h1>{{ greeting }}，让知识生根。</h1>
              <p>每一次思考、行动与回看，都让你离真正掌握更近一步。</p>
            </div>
            <button class="button primary" @click="openGoal">
              <Icon name="plus" :size="18" />新建学习目标
            </button>
          </div>
          <section class="hero">
            <div class="hero-copy">
              <div class="hero-kicker"><span></span>把「我知道」变成「我能做到」</div>
              <h2>学有所思，<br />行有所获。</h2>
              <p>先学，再练；走进真实问题，讲给别人听。<br />最后回头看，留下属于自己的理解。</p>
              <button
                class="button light"
                @click="nextUnit ? navigate('learn', nextUnit.id) : openGoal()"
              >
                {{ nextUnit ? '继续我的学习' : '开启第一个学习目标'
                }}<Icon name="arrow" :size="18" />
              </button>
            </div>
            <div class="learning-orbit" aria-label="学、练、用、讲、悟、温的学习闭环">
              <div class="orbit-ring"></div>
              <div class="orbit-core">
                <Icon name="leaf" :size="38" /><strong>知行合一</strong><span>LEARN BY DOING</span>
              </div>
              <div v-for="(stage, i) in stages" :key="stage.key" :class="`orbit-step step-${i}`">
                <span>{{ stage.label }}</span
                ><small>{{ stage.subtitle }}</small>
              </div>
              <span class="orbit-star star-one">✧</span><span class="orbit-star star-two">✧</span>
            </div>
            <ol class="mobile-learning-cycle" aria-label="完整学习闭环">
              <li v-for="stage in stages" :key="stage.key">
                <span>{{ stage.label }}</span
                ><small>{{ stage.subtitle }}</small>
              </li>
            </ol>
          </section>
          <section class="stats-strip" aria-label="学习统计">
            <div>
              <span class="stat-icon"><Icon name="target" /></span>
              <div>
                <strong>{{ goals.length }}<small>个</small></strong
                ><span>正在探索的目标</span>
              </div>
            </div>
            <div>
              <span class="stat-icon orange"><Icon name="check" /></span>
              <div>
                <strong>{{ completedUnits }}<small>个</small></strong
                ><span>完成学习闭环</span>
              </div>
            </div>
            <div>
              <span class="stat-icon"><Icon name="repeat" /></span>
              <div>
                <strong>{{ dashboard.reviews_due }}<small>项</small></strong
                ><span>今天等待回看</span>
              </div>
            </div>
            <div>
              <span class="stat-icon orange"><Icon name="notes" /></span>
              <div>
                <strong>{{ dashboard.knowledge_count }}<small>篇</small></strong
                ><span>自己的知识沉淀</span>
              </div>
            </div>
          </section>
          <div class="dashboard-columns">
            <section class="goal-section">
              <div class="section-heading">
                <h2>
                  正在生长的目标 <span>{{ goals.length.toString().padStart(2, '0') }}</span>
                </h2>
                <button class="text-button" @click="navigate('learn')">
                  全部学习<Icon name="arrow" :size="16" />
                </button>
              </div>
              <div v-if="!goals.length" class="empty-state goal-empty">
                <span class="empty-mark"><Icon name="leaf" :size="31" /></span>
                <h3>一段成长，从一个好问题开始</h3>
                <p>你希望具备什么能力？把它写下来，<br />我们一起拆成可以行动的小步。</p>
                <button class="button secondary" @click="openGoal">
                  写下我的目标<Icon name="plus" :size="17" />
                </button>
              </div>
              <article v-for="(goal, i) in goals" :key="goal.id" class="goal-card">
                <div class="goal-card-top">
                  <span class="goal-number">{{ String(i + 1).padStart(2, '0') }}</span
                  ><span class="pill">{{ levelLabel(goal.level) }}</span
                  ><button
                    class="icon-button muted"
                    :aria-label="`删除目标 ${goal.title}`"
                    :disabled="!!busy"
                    @click="deleteGoal(goal)"
                  >
                    <Icon name="trash" :size="16" />
                  </button>
                </div>
                <h3>{{ goal.title }}</h3>
                <p>{{ goal.motivation || '把理解变成能够独立解决问题的能力。' }}</p>
                <div class="goal-meta">
                  <span><Icon name="book" :size="15" />{{ goal.units.length }} 个学习单元</span
                  ><span><Icon name="clock" :size="15" />每天 {{ goal.daily_minutes }} 分钟</span>
                </div>
                <div class="progress-line">
                  <span>学习闭环进度</span><strong>{{ Math.round(goal.progress) }}%</strong>
                </div>
                <div class="progress-track">
                  <span :style="{ width: `${goal.progress}%` }"></span>
                </div>
                <button class="goal-continue" @click="navigate('learn', goalNextUnit(goal)?.id)">
                  <span>{{ stageLabel(goalNextUnit(goal)?.stage || 'learn') }}</span
                  >继续探索<Icon name="arrow" :size="17" />
                </button>
              </article>
            </section>
            <aside class="growth-column">
              <section class="daily-principle">
                <div class="eyebrow">学习的另一种可能</div>
                <span class="quote-mark">“</span>
                <blockquote>学而不思则罔，<br />思而不学则殆。</blockquote>
                <p>读完一个知识点，停一停：<br />它为什么成立？我在哪里能用到？</p>
                <div class="quote-author">《论语》 · 学思结合</div>
              </section>
              <section class="review-card">
                <div class="section-heading">
                  <h3>温故，才能知新</h3>
                  <Icon name="repeat" />
                </div>
                <p>
                  {{
                    dashboard.reviews_due
                      ? `有 ${dashboard.reviews_due} 个知识点到了回看的时候。先试着回忆，再看笔记。`
                      : '完成复盘后，系统会安排间隔复习。给理解一点时间，让它留下来。'
                  }}
                </p>
                <button class="text-button" @click="navigate('reviews')">
                  看看复习安排<Icon name="arrow" :size="16" />
                </button>
              </section>
              <section v-if="dashboard.recent_activity.length" class="activity-panel">
                <h3>最近的足迹</h3>
                <div
                  v-for="activity in dashboard.recent_activity.slice(0, 4)"
                  :key="activity.id"
                  class="activity-item"
                >
                  <span class="activity-dot"></span>
                  <div>
                    <strong>{{ activityLabel(activity.kind) }}</strong
                    ><small
                      >{{ date(activity.created_at, true)
                      }}<span v-if="activity.score !== null">
                        · {{ activity.score }} 分</span
                      ></small
                    >
                  </div>
                </div>
              </section>
            </aside>
          </div>
        </template>

        <template v-else-if="view === 'learn'">
          <div class="page-heading">
            <div>
              <p class="eyebrow">KNOW → DO → GROW</p>
              <h1>让理解，经得起实践。</h1>
              <p>不急着划掉任务。每一步，都留下一份真实的学习证据。</p>
            </div>
            <button class="button secondary" @click="openGoal">
              <Icon name="plus" :size="17" />新建目标
            </button>
          </div>
          <div v-if="!unit" class="empty-state large-empty">
            <Icon name="book" :size="42" />
            <h2>你的第一条学习路线，等你开启</h2>
            <p>写下一个具体的能力目标，我们从最小的一步开始。</p>
            <button class="button primary" @click="openGoal">
              创建学习目标<Icon name="arrow" :size="18" />
            </button>
          </div>
          <div v-else class="study-layout">
            <aside class="curriculum">
              <label for="goal-select" class="eyebrow">当前学习目标</label
              ><select
                id="goal-select"
                :value="unit.goal_id"
                @change="
                  navigate(
                    'learn',
                    goals.find((g) => g.id === ($event.target as HTMLSelectElement).value)?.units[0]
                      ?.id
                  )
                "
              >
                <option v-for="goal in goals" :key="goal.id" :value="goal.id">
                  {{ goal.title }}
                </option>
              </select>
              <div class="unit-mobile-picker">
                <label for="unit-select">学习单元</label
                ><select
                  id="unit-select"
                  :value="unit.id"
                  @change="navigate('learn', ($event.target as HTMLSelectElement).value)"
                >
                  <option v-for="item in currentGoal?.units" :key="item.id" :value="item.id">
                    {{ item.title }} · {{ stageLabel(item.stage) }}
                  </option>
                </select>
              </div>
              <div class="curriculum-progress">
                <span>闭环进度 {{ Math.round(currentGoal?.progress || 0) }}%</span>
                <div class="progress-track">
                  <span :style="{ width: `${currentGoal?.progress || 0}%` }"></span>
                </div>
              </div>
              <button
                v-for="(item, i) in currentGoal?.units"
                :key="item.id"
                :class="['unit-nav', { active: item.id === unit.id }]"
                @click="navigate('learn', item.id)"
              >
                <span class="unit-index"
                  ><Icon v-if="item.stage === 'complete'" name="check" :size="16" /><template
                    v-else
                    >{{ String(i + 1).padStart(2, '0') }}</template
                  ></span
                ><span
                  ><strong>{{ item.title }}</strong
                  ><small>{{ stageLabel(item.stage) }}</small></span
                >
              </button>
              <div class="curriculum-footer">
                <Icon name="clock" :size="16" /><span
                  >每天 {{ currentGoal?.daily_minutes }} 分钟<br /><small
                    >小步行动，比匆忙完成更有力量。</small
                  ></span
                >
              </div>
            </aside>
            <div class="study-main">
              <div class="unit-heading">
                <p class="eyebrow">
                  学习单元
                  {{
                    String(
                      (currentGoal?.units.findIndex((u) => u.id === unit?.id) ?? 0) + 1
                    ).padStart(2, '0')
                  }}
                </p>
                <h2>{{ unit.title }}</h2>
                <p>{{ unit.objective }}</p>
                <span class="mastery-badge">掌握记录 {{ Math.round(unit.mastery) }}%</span>
              </div>
              <nav class="stage-tabs" aria-label="学习闭环阶段">
                <button
                  v-for="(stage, i) in stages"
                  :key="stage.key"
                  :class="{ active: activeTab === stage.key, done: i < stagePosition }"
                  :disabled="i > stagePosition"
                  :aria-current="activeTab === stage.key ? 'step' : undefined"
                  @click="selectTab(stage.key)"
                >
                  <span
                    ><Icon v-if="i < stagePosition" name="check" :size="15" /><template v-else>{{
                      stage.label
                    }}</template></span
                  ><strong>{{ stage.subtitle }}</strong
                  ><Icon v-if="i > stagePosition" name="lock" :size="12" />
                </button>
              </nav>
              <section class="lesson-panel">
                <div v-if="!canSubmit && activeTab !== 'review'" class="read-only-hint">
                  <Icon name="history" :size="16" />这是你已经走过的一步，可以回看已有的理解与记录。
                </div>
                <form v-if="activeTab === 'learn'" @submit.prevent="submitStage">
                  <div class="panel-eyebrow">
                    <Icon name="book" :size="17" />闻 · 先听懂，再想一想
                  </div>
                  <h3>理解这个知识点</h3>
                  <div class="prose">{{ unit.lesson.explanation }}</div>
                  <div class="example-box">
                    <span class="eyebrow">从一个例子开始</span>
                    <p class="prose">{{ unit.lesson.example }}</p>
                  </div>
                  <div class="thinking-question">
                    <Icon name="sparkle" :size="19" />
                    <p>{{ unit.lesson.question }}</p>
                  </div>
                  <label for="learn-reflection">用自己的话，说说你的理解</label
                  ><textarea
                    id="learn-reflection"
                    v-model="learnReflection"
                    rows="4"
                    maxlength="12000"
                    :disabled="!canSubmit || !!busy"
                    placeholder="不要照抄。写下你的理解、一个疑问，以及它与已有经验的联系。"
                  ></textarea>
                  <div class="form-footer">
                    <small>{{ length(learnReflection) }}/20 字起，写下你真正理解的内容</small
                    ><button
                      v-if="canSubmit"
                      class="button primary"
                      :disabled="!!busy || length(learnReflection) < 20"
                    >
                      {{ busy === 'submission' ? '正在记录…' : '记录理解，进入练习'
                      }}<Icon name="arrow" :size="17" />
                    </button>
                  </div>
                </form>
                <form v-else-if="activeTab === 'practice'" @submit.prevent="submitStage">
                  <div class="panel-eyebrow">
                    <Icon name="target" :size="17" />习 · 试着独立判断
                  </div>
                  <h3>能理解，也能辨别</h3>
                  <p class="prose question-text">{{ unit.practice.question }}</p>
                  <fieldset class="practice-options">
                    <legend class="sr-only">选择你的答案</legend>
                    <label
                      v-for="(option, index) in unit.practice.options"
                      :key="index"
                      :class="['option', { selected: practiceAnswer === String(index) }]"
                      ><input
                        v-model="practiceAnswer"
                        type="radio"
                        name="practice"
                        :value="String(index)"
                        :disabled="!canSubmit || !!busy"
                      /><span>{{ String.fromCharCode(65 + index) }}</span>
                      <p>{{ option }}</p></label
                    >
                  </fieldset>
                  <div class="form-footer">
                    <small>判断后提交。答错也会留下一次学习的线索。</small
                    ><button
                      v-if="canSubmit"
                      class="button primary"
                      :disabled="!!busy || practiceAnswer === ''"
                    >
                      {{ busy === 'submission' ? '正在评估…' : '提交答案'
                      }}<Icon name="arrow" :size="17" />
                    </button>
                  </div>
                </form>
                <form v-else-if="activeTab === 'project'" @submit.prevent="submitStage">
                  <div class="panel-eyebrow">
                    <Icon name="leaf" :size="17" />做 · 让知识进入真实问题
                  </div>
                  <h3>{{ unit.project.title }}</h3>
                  <p class="prose">{{ unit.project.brief }}</p>
                  <div class="criteria-box">
                    <strong>让结果可检验</strong>
                    <ul>
                      <li v-for="criterion in unit.project.criteria" :key="criterion">
                        <Icon name="check" :size="15" />{{ criterion }}
                      </li>
                    </ul>
                  </div>
                  <label for="project-content">提交你的实战成果</label
                  ><textarea
                    id="project-content"
                    v-model="projectContent"
                    rows="8"
                    maxlength="20000"
                    :disabled="!canSubmit || !!busy"
                    placeholder="可以是代码、方案或实验记录。交代问题、你的做法、实际结果与验证方式，让别人能看懂你的行动。"
                  ></textarea>
                  <div class="form-footer">
                    <small>把做过的事写具体，包括不顺利的部分。</small
                    ><button
                      v-if="canSubmit"
                      class="button primary"
                      :disabled="!!busy || length(projectContent) < 20"
                    >
                      {{ busy === 'submission' ? '正在评估…' : '提交实战成果'
                      }}<Icon name="arrow" :size="17" />
                    </button>
                  </div>
                </form>
                <form v-else-if="activeTab === 'teach'" @submit.prevent="submitStage">
                  <div class="panel-eyebrow">
                    <Icon name="message" :size="17" />教 · 讲给一个初学者听
                  </div>
                  <h3>你能把它讲清楚吗？</h3>
                  <p class="prose">{{ unit.teach.prompt }}</p>
                  <div class="criteria-box">
                    <strong>好讲解的几个线索</strong>
                    <ul>
                      <li v-for="criterion in unit.teach.checklist" :key="criterion">
                        <Icon name="check" :size="15" />{{ criterion }}
                      </li>
                    </ul>
                  </div>
                  <label for="teach-content">你的讲解稿</label
                  ><textarea
                    id="teach-content"
                    v-model="teachContent"
                    rows="8"
                    maxlength="20000"
                    :disabled="!canSubmit || !!busy"
                    placeholder="假设对方第一次接触这个知识：用日常语言说明原理，举一个例子，再提醒一个容易误解的地方。"
                  ></textarea>
                  <div class="form-footer">
                    <small>发现讲不顺的地方，往往就是下次学习的入口。</small
                    ><button
                      v-if="canSubmit"
                      class="button primary"
                      :disabled="!!busy || length(teachContent) < 20"
                    >
                      {{ busy === 'submission' ? '正在评估…' : '检验我的讲解'
                      }}<Icon name="arrow" :size="17" />
                    </button>
                  </div>
                </form>
                <form v-else-if="activeTab === 'reflect'" @submit.prevent="submitStage">
                  <div class="panel-eyebrow">
                    <Icon name="notes" :size="17" />思 · 回看，留下自己的理解
                  </div>
                  <h3>这一次，有什么不一样？</h3>
                  <p class="panel-intro">
                    学习不是把页面翻完。回到最初的理解，看看实践带来了什么改变。
                  </p>
                  <label for="reflection-content">回看整个学习过程</label
                  ><textarea
                    id="reflection-content"
                    v-model="reflection.content"
                    rows="4"
                    maxlength="12000"
                    :disabled="!canSubmit || !!busy"
                    placeholder="最初怎么想？实践中发生了什么？哪些问题还没有解决？（至少 20 字）"
                  ></textarea
                  ><label for="reflection-takeaway">值得沉淀的一个发现</label
                  ><textarea
                    id="reflection-takeaway"
                    v-model="reflection.takeaway"
                    rows="3"
                    maxlength="4000"
                    :disabled="!canSubmit || !!busy"
                    placeholder="留下一个你能够再次使用的方法或判断。（至少 10 字）"
                  ></textarea
                  ><label for="reflection-change">理解的变化，或下一次的新尝试</label
                  ><textarea
                    id="reflection-change"
                    v-model="reflection.change"
                    rows="3"
                    maxlength="4000"
                    :disabled="!canSubmit || !!busy"
                    placeholder="我的想法如何变化？下次遇到类似问题，会怎么做？（至少 10 字）"
                  ></textarea>
                  <div class="form-footer">
                    <small>自动保存为知识笔记，并安排间隔复习。</small
                    ><button
                      v-if="canSubmit"
                      class="button primary"
                      :disabled="
                        !!busy ||
                        length(reflection.content) < 20 ||
                        length(reflection.takeaway) < 10 ||
                        length(reflection.change) < 10
                      "
                    >
                      {{ busy === 'submission' ? '正在沉淀…' : '保存复盘，安排回看'
                      }}<Icon name="check" :size="17" />
                    </button>
                  </div>
                </form>
                <form v-else-if="activeTab === 'review'" @submit.prevent="submitStage">
                  <div class="panel-eyebrow">
                    <Icon name="repeat" :size="17" />修 · 给理解一点时间
                  </div>
                  <h3>{{ reviewDue ? '不看笔记，先试着回忆' : '让知识在时间里留下来' }}</h3>
                  <div class="review-schedule">
                    <Icon name="clock" :size="25" />
                    <div>
                      <strong>{{ reviewDue ? '现在适合回看' : '下一次回看' }}</strong>
                      <p>
                        {{ date(unit.review_due_at, true) }} · 已回看 {{ unit.review_count }} 次
                      </p>
                    </div>
                    <span v-if="unit.stage === 'complete'" class="pill">闭环已完成</span>
                  </div>
                  <p class="panel-intro">
                    {{
                      reviewDue
                        ? unit.lesson.question
                        : '已经做过、讲过，也留下了复盘。先去探索新的单元，等间隔复习到期，再检验留下了多少理解。'
                    }}
                  </p>
                  <template v-if="reviewDue"
                    ><label for="review-answer">你还记得什么？</label
                    ><textarea
                      id="review-answer"
                      v-model="recall.answer"
                      rows="6"
                      maxlength="12000"
                      :disabled="!canSubmit || !!busy"
                      placeholder="闭卷解释核心概念、一个应用例子和容易混淆的边界。先回忆，再对照。"
                    ></textarea>
                    <fieldset class="recall-rating">
                      <legend>这次回忆有多轻松？</legend>
                      <label
                        v-for="(label, i) in ['忘记很多', '比较吃力', '基本记得', '很有把握']"
                        :key="label"
                        :class="{ selected: recall.rating === i + 1 }"
                        ><input
                          v-model="recall.rating"
                          type="radio"
                          name="rating"
                          :value="i + 1"
                          :disabled="!canSubmit || !!busy"
                        />{{ label }}</label
                      >
                    </fieldset>
                    <div class="form-footer">
                      <small>回忆内容与自评共同决定下次复习时间。</small
                      ><button
                        class="button primary"
                        :disabled="!!busy || !canSubmit || length(recall.answer) < 20"
                      >
                        {{ busy === 'submission' ? '正在评估…' : '完成这次回看'
                        }}<Icon name="check" :size="17" />
                      </button></div></template
                  ><button
                    v-else
                    class="button secondary"
                    type="button"
                    @click="
                      nextStudyUnit ? navigate('learn', nextStudyUnit.id) : navigate('dashboard')
                    "
                  >
                    {{ nextStudyUnit ? '继续探索其他单元' : '返回学习概览'
                    }}<Icon name="arrow" :size="17" />
                  </button>
                </form>
                <div
                  v-if="feedback"
                  :class="['assessment-feedback', { passed: feedback.passed !== false }]"
                  role="status"
                >
                  <div class="feedback-heading">
                    <Icon :name="feedback.passed === false ? 'repeat' : 'check'" /><strong>{{
                      feedback.passed === false ? '再想一想，再试一次' : '这一步，你走过了'
                    }}</strong
                    ><span v-if="feedback.score !== undefined">{{ feedback.score }} 分</span>
                  </div>
                  <p class="prose">{{ feedback.feedback }}</p>
                  <button
                    v-if="feedback.passed !== false && unit.stage !== activeTab"
                    class="button primary"
                    type="button"
                    @click="nextStage"
                  >
                    {{ unit.stage === 'complete' ? '查看下次回看' : `进入${stageLabel(unit.stage)}`
                    }}<Icon name="arrow" :size="17" />
                  </button>
                </div>
              </section>
              <section class="tutor-panel">
                <div class="section-heading">
                  <h3><Icon name="sparkle" :size="19" />和导师一起想一想</h3>
                  <span class="pill">{{ settings?.mode === 'demo' ? '体验引导' : 'AI 导师' }}</span>
                </div>
                <p class="panel-intro">哪里卡住了？说说你的想法，导师会帮你找到继续思考的入口。</p>
                <div v-if="chatReply" class="tutor-reply prose" aria-live="polite">
                  {{ chatReply }}
                </div>
                <form class="chat-form" @submit.prevent="sendChat">
                  <label class="sr-only" for="chat-message">向导师提问</label
                  ><textarea
                    id="chat-message"
                    v-model="chatMessage"
                    rows="2"
                    maxlength="4000"
                    placeholder="例如：我这样理解对吗？这个方法还有什么适用边界？"
                    :disabled="!!busy"
                  ></textarea
                  ><button class="button primary" :disabled="!!busy || !chatMessage.trim()">
                    {{ busy === 'chat' ? '思考中…' : '一起思考' }}<Icon name="arrow" :size="17" />
                  </button>
                </form>
              </section>
              <details class="session-history">
                <summary>
                  <Icon name="history" :size="18" />学习足迹<span
                    >{{ unit.sessions.length }} 条记录</span
                  >
                </summary>
                <p v-if="!unit.sessions.length" class="panel-intro">
                  留下第一份理解，这里就会有你的学习足迹。
                </p>
                <article v-for="session in [...unit.sessions].reverse()" :key="session.id">
                  <div>
                    <strong>{{ activityLabel(session.kind) }}</strong
                    ><time>{{ date(session.created_at, true) }}</time
                    ><span v-if="session.score !== null">{{ session.score }} 分</span>
                  </div>
                  <p class="prose">{{ session.content }}</p>
                  <p class="session-feedback prose">{{ session.feedback }}</p>
                </article>
              </details>
            </div>
          </div>
        </template>

        <template v-else-if="view === 'reviews'">
          <div class="page-heading">
            <div>
              <p class="eyebrow">REVISIT & REMEMBER</p>
              <h1>温故，让理解常新。</h1>
              <p>先回忆，再回看。记忆的困难，也是一条值得看见的学习线索。</p>
            </div>
            <span class="large-count"
              >{{ reviews.length.toString().padStart(2, '0') }}<small>项待回看</small></span
            >
          </div>
          <section class="review-explainer">
            <Icon name="repeat" :size="27" />
            <div>
              <h3>不是再读一遍，而是再想一遍</h3>
              <p>
                完成实战、讲解与复盘后，知识点进入间隔复习。根据真实回忆表现调整间隔，遗忘时回到练习巩固。
              </p>
            </div>
          </section>
          <div v-if="!reviews.length" class="empty-state large-empty">
            <Icon name="leaf" :size="42" />
            <h2>今天，暂时没有到期的回看</h2>
            <p>去学一点，做一点。完成复盘后，复习会在合适的时候回来。</p>
            <button class="button primary" @click="navigate('learn')">
              继续我的学习<Icon name="arrow" :size="17" />
            </button>
          </div>
          <div v-else class="review-list">
            <article v-for="item in reviews" :key="item.id">
              <span class="review-list-icon"><Icon name="repeat" :size="24" /></span>
              <div>
                <p class="eyebrow">{{ item.goal_title }}</p>
                <h3>{{ item.title }}</h3>
                <p>{{ item.objective }}</p>
                <small
                  >已回看 {{ item.review_count }} 次 · {{ date(item.review_due_at) }} 到期</small
                >
              </div>
              <button class="button primary" @click="navigate('learn', item.id)">
                开始回忆<Icon name="arrow" :size="17" />
              </button>
            </article>
          </div>
          <section
            v-if="goals.some((g) => g.units.some((u) => u.review_due_at))"
            class="upcoming-reviews"
          >
            <div class="section-heading">
              <h2>接下来的回看</h2>
              <span class="muted">给成长留一点间隔</span>
            </div>
            <template v-for="goal in goals" :key="goal.id"
              ><div
                v-for="item in goal.units.filter(
                  (u) => u.review_due_at && new Date(u.review_due_at).getTime() > Date.now()
                )"
                :key="item.id"
                class="upcoming-row"
              >
                <Icon name="clock" :size="17" /><span
                  >{{ item.title }}<small>{{ goal.title }}</small></span
                ><time>{{ date(item.review_due_at, true) }}</time>
              </div></template
            >
          </section>
        </template>

        <template v-else-if="view === 'knowledge'">
          <div class="page-heading">
            <div>
              <p class="eyebrow">YOUR SECOND UNDERSTANDING</p>
              <h1>留下，属于你的理解。</h1>
              <p>把资料与亲身实践的发现放在一起。知识不只被收藏，也被再次使用。</p>
            </div>
            <div class="heading-actions">
              <button class="button secondary" :disabled="!!busy" @click="uploadInput?.click()">
                <Icon name="upload" :size="17" />{{
                  busy === 'import' ? '导入中…' : '导入资料'
                }}</button
              ><button class="button primary" @click="showNoteForm = !showNoteForm">
                <Icon name="plus" :size="17" />写一篇笔记</button
              ><input
                ref="uploadInput"
                class="sr-only"
                type="file"
                accept=".md,.txt,.pdf,.docx"
                aria-label="导入学习资料"
                @change="importFile"
              />
            </div>
          </div>
          <section v-if="showNoteForm" class="new-note-panel">
            <h3>记下一次新的理解</h3>
            <form @submit.prevent="createNote">
              <label for="note-title">笔记标题</label
              ><input
                id="note-title"
                v-model="noteForm.title"
                maxlength="200"
                required
                placeholder="这个发现，可以叫什么？"
              /><label for="note-content">笔记内容</label
              ><textarea
                id="note-content"
                v-model="noteForm.content"
                rows="6"
                maxlength="100000"
                required
                placeholder="写下原理、经验、例子与待解的问题。"
              ></textarea>
              <div class="form-footer">
                <button class="text-button" type="button" @click="showNoteForm = false">取消</button
                ><button
                  class="button primary"
                  :disabled="!!busy || !noteForm.title.trim() || !noteForm.content.trim()"
                >
                  {{ busy === 'note' ? '保存中…' : '存入知识库' }}<Icon name="check" :size="17" />
                </button>
              </div>
            </form>
          </section>
          <section class="knowledge-ask">
            <div>
              <span class="panel-eyebrow"
                ><Icon name="sparkle" :size="18" />让积累的知识，再帮你一次</span
              >
              <h3>向自己的知识库提问</h3>
              <p>从已导入资料和复盘笔记中寻找答案，并提供可回看的来源。</p>
            </div>
            <form @submit.prevent="askKnowledge">
              <label class="sr-only" for="knowledge-question">知识库问题</label
              ><input
                id="knowledge-question"
                v-model="knowledgeQuery"
                maxlength="4000"
                placeholder="例如：我在实践里发现了哪些适用边界？"
              /><button class="button primary" :disabled="!!busy || !knowledgeQuery.trim()">
                {{ busy === 'ask' ? '查找中…' : '寻找答案' }}<Icon name="arrow" :size="17" />
              </button>
            </form>
            <div v-if="knowledgeAnswer" class="knowledge-answer" aria-live="polite">
              <p class="prose">{{ knowledgeAnswer.answer }}</p>
              <div v-if="knowledgeAnswer.sources.length" class="source-list">
                <span class="eyebrow">答案来源</span
                ><button
                  v-for="source in knowledgeAnswer.sources"
                  :key="source.id"
                  class="source-card"
                  @click="selectedNote = source.id"
                >
                  <strong><Icon name="notes" :size="15" />{{ source.title }}</strong
                  ><span>{{ source.excerpt }}</span>
                </button>
              </div>
              <small v-else class="muted"
                >当前资料不足以支持这个问题。可以补充相关资料后再试。</small
              >
            </div>
          </section>
          <div class="section-heading knowledge-list-heading">
            <h2>
              我的知识沉淀 <span>{{ notes.length.toString().padStart(2, '0') }}</span>
            </h2>
            <label class="search-field"
              ><Icon name="search" :size="17" /><input
                v-model="noteSearch"
                aria-label="搜索知识笔记"
                placeholder="搜索笔记与资料"
            /></label>
          </div>
          <p class="import-hint">
            支持 Markdown、TXT、可提取文字的 PDF 与 Word（.docx），单个文件不超过 10
            MB。复盘笔记会自动加入。
          </p>
          <div v-if="!filteredNotes.length" class="empty-state large-empty">
            <Icon name="notes" :size="40" />
            <h2>{{ notes.length ? '还没有找到相关笔记' : '让你的第一个发现，在这里生根' }}</h2>
            <p>
              {{
                notes.length
                  ? '试试其他关键词，或查看全部知识沉淀。'
                  : '导入一份资料，或完成一次学习复盘。每篇笔记都是下次行动的起点。'
              }}
            </p>
            <button v-if="notes.length" class="button secondary" @click="noteSearch = ''">
              查看全部笔记
            </button>
          </div>
          <div v-else class="notes-grid">
            <article
              v-for="note in filteredNotes"
              :key="note.id"
              :class="['note-card', { expanded: selectedNote === note.id }]"
            >
              <div class="note-card-meta">
                <span class="pill">{{
                  note.source === 'reflection' || note.source === '复盘'
                    ? '实践沉淀'
                    : note.source === 'note'
                      ? '我的笔记'
                      : '学习资料'
                }}</span
                ><time>{{ date(note.created_at) }}</time
                ><button
                  class="icon-button muted"
                  :aria-label="`删除笔记 ${note.title}`"
                  :disabled="!!busy"
                  @click="deleteNote(note)"
                >
                  <Icon name="trash" :size="16" />
                </button>
              </div>
              <button
                class="note-title"
                :aria-expanded="selectedNote === note.id"
                @click="selectedNote = selectedNote === note.id ? null : note.id"
              >
                <h3>{{ note.title }}</h3>
              </button>
              <p class="prose note-content">
                {{
                  selectedNote === note.id
                    ? note.content
                    : note.content.slice(0, 180) + (note.content.length > 180 ? '…' : '')
                }}
              </p>
              <button
                class="text-button"
                @click="selectedNote = selectedNote === note.id ? null : note.id"
              >
                {{ selectedNote === note.id ? '收起笔记' : '回看完整笔记'
                }}<Icon name="arrow" :size="16" />
              </button>
            </article>
          </div>
        </template>

        <template v-else-if="view === 'settings'">
          <div class="page-heading">
            <div>
              <p class="eyebrow">THE WAY WE LEARN</p>
              <h1>一套有来处的学习方式。</h1>
              <p>让东方的学习智慧，与主动回忆、刻意练习和费曼讲解相遇。</p>
            </div>
            <span class="settings-leaf"><Icon name="leaf" :size="36" /></span>
          </div>
          <section class="provider-panel">
            <div>
              <span class="eyebrow">当前学习服务</span>
              <h3>
                {{
                  settings?.mode === 'demo'
                    ? '体验模式 · 无需模型密钥'
                    : `${settings?.provider || 'AI'} · ${settings?.model || '已配置模型'}`
                }}
              </h3>
              <p>
                {{
                  settings?.mode === 'demo'
                    ? '体验完整学习流程，使用预设教学内容与规则检查。规则反馈不能代替专业导师的概念与成果评估。'
                    : '学习路线、导师对话与开放题评估由已配置的模型提供。关键推进规则与复习记录仍由学习系统管理。'
                }}
              </p>
            </div>
            <span class="pill">{{
              settings?.mode === 'demo'
                ? '本地体验'
                : settings?.configured
                  ? '已配置'
                  : '配置需检查'
            }}</span>
          </section>
          <div class="principles-grid">
            <article v-for="(principle, i) in settings?.principles" :key="principle.name">
              <span class="principle-number">{{ String(i + 1).padStart(2, '0') }}</span>
              <h3>{{ principle.name }}</h3>
              <p>{{ principle.practice }}</p>
            </article>
          </div>
          <section class="settings-about">
            <h3>关于这个学习空间</h3>
            <p>
              DoKnow
              首版面向本地个人学习。学习目标、实战记录、复盘与资料保存在你的学习服务中。模型配置由服务端环境变量管理，界面不会展示或保存密钥。
            </p>
            <ul v-if="settings?.limitations.length">
              <li v-for="limitation in settings.limitations" :key="limitation">{{ limitation }}</li>
            </ul>
            <div class="about-signature">
              <strong>DoKnow</strong><span>Know. Do. Grow. · 知而后行，行而后知。</span>
            </div>
          </section>
        </template>
        <footer class="page-footer">
          <span>DoKnow · 知而后行，行而后知。</span><span>学习不可以已。</span>
        </footer>
      </main>
    </div>
  </div>
  <dialog ref="goalDialog" class="goal-dialog">
    <form @submit.prevent="createGoal">
      <div class="dialog-heading">
        <span class="panel-eyebrow"><Icon name="leaf" :size="18" />开始一段新的成长</span
        ><button
          class="icon-button"
          type="button"
          aria-label="关闭新建目标"
          :disabled="busy === 'goal'"
          @click="goalDialog?.close()"
        >
          <Icon name="close" />
        </button>
      </div>
      <h2>你希望，能做到什么？</h2>
      <p>具体一点。好的学习目标，是一个你想亲手解决的问题。</p>
      <div v-if="error" class="alert error" role="alert">{{ error }}</div>
      <label for="goal-title">我的学习目标</label
      ><input
        id="goal-title"
        ref="goalTitleInput"
        v-model="goalForm.title"
        maxlength="200"
        minlength="2"
        required
        placeholder="例如：学会用 Python 分析一份销售数据"
        :disabled="busy === 'goal'"
      /><label for="goal-motivation">为什么想学？<span class="muted">（可选）</span></label
      ><textarea
        id="goal-motivation"
        v-model="goalForm.motivation"
        rows="3"
        maxlength="2000"
        placeholder="希望解决什么问题？想在什么情境中使用？"
        :disabled="busy === 'goal'"
      ></textarea>
      <div class="form-columns">
        <div>
          <label for="goal-level">目前的基础</label
          ><select id="goal-level" v-model="goalForm.level" :disabled="busy === 'goal'">
            <option value="beginner">刚开始 · 初学者</option>
            <option value="intermediate">有基础 · 想学会应用</option>
            <option value="advanced">已熟悉 · 想深入探索</option>
          </select>
        </div>
        <div>
          <label for="goal-minutes">每天愿意投入</label
          ><select
            id="goal-minutes"
            v-model.number="goalForm.daily_minutes"
            :disabled="busy === 'goal'"
          >
            <option :value="10">10 分钟 · 一小步</option>
            <option :value="20">20 分钟 · 轻量练习</option>
            <option :value="30">30 分钟 · 稳步生长</option>
            <option :value="60">60 分钟 · 专注探索</option>
            <option :value="90">90 分钟 · 深入实践</option>
          </select>
        </div>
      </div>
      <div class="goal-form-note">
        <Icon name="sparkle" :size="18" /><span
          >路线将包含学习、练习、实战、讲解、复盘与间隔回看。每个单元都需要用实际表现验证。</span
        >
      </div>
      <button
        class="button primary full-width"
        :disabled="busy === 'goal' || goalForm.title.trim().length < 2"
      >
        {{ busy === 'goal' ? '正在设计学习路线…' : '生成我的学习路线'
        }}<Icon name="arrow" :size="18" />
      </button>
    </form>
  </dialog>
</template>
