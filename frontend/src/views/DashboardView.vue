<script setup lang="ts">
/**
 * Knowledge-graph home (miroFish-style).
 *
 * Post-login landing:
 * - no active goal → a single prominent goal input; creating + activating a
 *   goal kicks off the AI knowledge-system build;
 * - active goal → full-bleed layout: a 3D force-directed knowledge graph on
 *   the left (~2/3) and a planning panel on the right (~1/3).
 *
 * Graph nodes come from `/goals/{id}/knowledge` (each point carries its
 * prerequisite `code`s) and edges are derived from those prerequisites;
 * node colour reflects mastery state from `/goals/{id}/path`.
 */
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { goalsApi } from '@/api/goals'
import { tasksApi } from '@/api/tasks'
import type { Goal, KnowledgePoint, LearningPath, OverviewResponse } from '@/api/types'
import KnowledgeGraph3D from '@/components/KnowledgeGraph3D.vue'
import type { KgLink, KgNode } from '@/components/graph-types'
import PlanningPanel from '@/components/PlanningPanel.vue'
import { difficultyLabel, fmtMinutes, masteryLabel } from '@/utils/format'
import { useGoalStore } from '@/stores/goal'
import { useToastStore } from '@/stores/toast'

const goalStore = useGoalStore()
const toast = useToastStore()

const activeGoal = computed(() => goalStore.activeGoal)
const dashboard = computed(() => goalStore.dashboard)

const points = ref<KnowledgePoint[]>([])
const path = ref<LearningPath | null>(null)
const built = ref(true)
const loading = ref(true)
const creating = ref(false)
const generatingTasks = ref(false)
const goalInput = ref('')
const selectedCode = ref<string | null>(null)

const graphNodes = ref<KgNode[]>([])
const graphLinks = ref<KgLink[]>([])

let pollTimer: number | null = null
let pollTries = 0

const building = computed(() => !points.value.length && !built.value)

const selectedPoint = computed(
  () => points.value.find((p) => p.code === selectedCode.value) ?? null,
)

const draftGoals = computed(() => goalStore.goals.filter((g) => g.status === 'DRAFT'))
const dueReviewCount = computed(() => dashboard.value?.due_reviews.length ?? 0)
const planProposal = computed(() => dashboard.value?.plan_proposal ?? null)

// ---- graph building helpers ----

const MASTERY_COLOR: Record<string, string> = {
  MASTERED: '#1f9d63',
  COMPLETED: '#2f7bf6',
  IN_PROGRESS: '#2f7bf6',
  REVIEW_REQUIRED: '#e8930c',
  NOT_STARTED: '#8a93a3',
}

const TYPE_COLOR: Record<string, string> = {
  CONCEPT: '#6d3fd1',
  FACT: '#12a5a5',
  PROCEDURE: '#2f7bf6',
  PRINCIPLE: '#e8930c',
  SKILL: '#1f9d63',
}

const DIFFICULTY_SIZE: Record<string, number> = {
  BEGINNER: 4,
  INTERMEDIATE: 5.5,
  ADVANCED: 7.2,
}

const KNOWLEDGE_TYPE_LABEL: Record<string, string> = {
  CONCEPT: '概念',
  FACT: '事实',
  PROCEDURE: '流程',
  PRINCIPLE: '原理',
  SKILL: '技能',
}

function buildGraph(): void {
  const masteryByCode = new Map<string, string>()
  for (const node of path.value?.nodes ?? []) {
    if (node.knowledge_point && node.mastery?.mastery_state) {
      masteryByCode.set(node.knowledge_point.code, node.mastery.mastery_state)
    }
  }

  graphNodes.value = points.value.map((p) => {
    const mastery = masteryByCode.get(p.code)
    const color = mastery
      ? (MASTERY_COLOR[mastery] ?? '#8a93a3')
      : (TYPE_COLOR[p.knowledge_type] ?? '#8a93a3')
    return {
      id: p.code,
      name: p.name,
      color,
      size: DIFFICULTY_SIZE[p.difficulty] ?? 5,
      label:
        `${p.name}\n${KNOWLEDGE_TYPE_LABEL[p.knowledge_type] ?? p.knowledge_type}` +
        ` · ${difficultyLabel(p.difficulty)} · ${masteryLabel(mastery as never)}` +
        (p.est_minutes ? ` · 约 ${fmtMinutes(p.est_minutes)}` : ''),
    }
  })

  const codes = new Set(points.value.map((p) => p.code))
  const links: KgLink[] = []
  for (const p of points.value) {
    for (const pre of p.prerequisites) {
      if (pre !== p.code && codes.has(pre)) links.push({ source: pre, target: p.code })
    }
  }
  graphLinks.value = links
}

async function loadGraphData(): Promise<void> {
  const goalId = goalStore.activeGoalId
  if (!goalId) return
  const [knowledgeRes, pathRes, overviewRes] = await Promise.all([
    goalsApi.knowledge(goalId).catch(() => ({ points: [] as KnowledgePoint[] })),
    goalsApi.path(goalId).catch(() => ({ path: null as LearningPath | null })),
    goalsApi.overview(goalId).catch(() => null as OverviewResponse | null),
  ])
  points.value = knowledgeRes.points
  path.value = pathRes.path
  built.value = overviewRes
    ? overviewRes.knowledge_system_built || knowledgeRes.points.length > 0
    : true
  buildGraph()
  if (building.value) schedulePoll()
}

function schedulePoll(): void {
  if (pollTimer !== null) return
  pollTimer = window.setTimeout(async () => {
    pollTimer = null
    if (pollTries >= 15) return
    pollTries += 1
    await loadGraphData()
  }, 8000)
}

async function load(): Promise<void> {
  loading.value = true
  try {
    await goalStore.ensureDashboard()
    await goalStore.loadGoals()
    if (goalStore.activeGoalId) {
      await loadGraphData()
    }
  } catch (e) {
    toast.error(e instanceof Error ? e.message : '加载失败，请刷新重试')
  } finally {
    loading.value = false
  }
}

// ---- hero actions ----

const EXAMPLES = ['两周入门 SQL 数据分析', '三个月通过日语 N3', '从零掌握 Python 机器学习', '系统学习宏观经济学']

async function createGoal(): Promise<void> {
  const title = goalInput.value.trim()
  if (!title) return
  creating.value = true
  try {
    const res = await goalsApi.create({ title })
    await goalsApi.activate(res.id)
    goalInput.value = ''
    selectedCode.value = null
    pollTries = 0
    toast.success('目标已创建，AI 正在搭建知识体系')
    await load()
  } catch (e) {
    toast.error(e instanceof Error ? e.message : '创建失败，请重试')
  } finally {
    creating.value = false
  }
}

async function activateExisting(goal: Goal): Promise<void> {
  creating.value = true
  try {
    await goalsApi.activate(goal.id)
    selectedCode.value = null
    pollTries = 0
    await load()
  } catch (e) {
    toast.error(e instanceof Error ? e.message : '切换目标失败')
  } finally {
    creating.value = false
  }
}

// ---- panel actions ----

function selectNode(code: string | null): void {
  selectedCode.value = code
}

async function generateTasks(): Promise<void> {
  const goalId = goalStore.activeGoalId
  if (!goalId) return
  generatingTasks.value = true
  try {
    const res = await tasksApi.generate(goalId)
    toast.success(res.created > 0 ? `已生成 ${res.created} 个任务` : '任务已就绪')
    await goalStore.loadDashboard()
  } catch (e) {
    toast.error(e instanceof Error ? e.message : '生成失败，请重试')
  } finally {
    generatingTasks.value = false
  }
}

async function requestExplain(code: string): Promise<void> {
  const goalId = goalStore.activeGoalId
  const point = points.value.find((p) => p.code === code)
  if (!goalId || !point) return
  try {
    await tasksApi.createExplain(goalId, point.id)
    toast.success('讲解任务已创建，去今日任务完成它')
    await goalStore.loadDashboard()
  } catch (e) {
    toast.error(e instanceof Error ? e.message : '创建失败，请重试')
  }
}

onMounted(load)

watch(
  () => goalStore.activeGoalId,
  () => {
    pollTries = 0
    selectedCode.value = null
    void load()
  },
)

onBeforeUnmount(() => {
  if (pollTimer !== null) window.clearTimeout(pollTimer)
  pollTimer = null
})
</script>

<template>
  <!-- no active goal: goal input hero -->
  <div v-if="!activeGoal" class="kg-hero">
    <div class="kg-hero-inner">
      <h1 class="kg-hero-title">想学会什么？</h1>
      <p class="kg-hero-sub">告诉 DoKnow 你的学习目标，AI 会为你搭建知识体系、规划路径、安排每天的学·练·讲。</p>

      <form class="kg-goal-form" @submit.prevent="createGoal">
        <input
          v-model="goalInput"
          class="kg-goal-input"
          type="text"
          placeholder="例如：两周入门 SQL 数据分析"
          :disabled="creating"
        />
        <button class="btn btn-primary btn-lg" type="submit" :disabled="creating || !goalInput.trim()">
          {{ creating ? '创建中…' : '开始学习' }}
        </button>
      </form>

      <div class="kg-chips">
        <button
          v-for="ex in EXAMPLES"
          :key="ex"
          class="kg-chip"
          type="button"
          :disabled="creating"
          @click="goalInput = ex"
        >
          {{ ex }}
        </button>
      </div>

      <div v-if="draftGoals.length" class="kg-switch">
        <span>或继续已有目标：</span>
        <button
          v-for="g in draftGoals.slice(0, 4)"
          :key="g.id"
          class="link-btn"
          type="button"
          :disabled="creating"
          @click="activateExisting(g)"
        >
          {{ g.title }}
        </button>
        <RouterLink :to="{ name: 'goal-new' }">新建详细目标</RouterLink>
      </div>
      <div v-else class="kg-switch">
        <RouterLink :to="{ name: 'goal-new' }">填写更详细的学习目标（时间、水平、截止）</RouterLink>
      </div>
    </div>
  </div>

  <!-- active goal: 3D knowledge graph + planning panel -->
  <div v-else class="kg-home">
    <div class="kg-canvas">
      <KnowledgeGraph3D
        :nodes="graphNodes"
        :links="graphLinks"
        :selected-id="selectedCode"
        @select="selectNode"
      />

      <div v-if="graphNodes.length" class="kg-hint">
        拖动旋转 · 滚轮缩放 · 点击节点查看详情
      </div>

      <div v-if="graphNodes.length" class="kg-legend">
        <span class="kg-legend-item"><i class="kg-legend-dot" style="background:#1f9d63" />已掌握</span>
        <span class="kg-legend-item"><i class="kg-legend-dot" style="background:#2f7bf6" />学习中</span>
        <span class="kg-legend-item"><i class="kg-legend-dot" style="background:#e8930c" />待巩固</span>
        <span class="kg-legend-item"><i class="kg-legend-dot" style="background:#8a93a3" />未开始</span>
      </div>

      <div v-if="building && !graphNodes.length" class="kg-empty">
        <div class="card" style="max-width: 380px; text-align: center">
          <div class="row" style="justify-content: center; gap: 8px">
            <span class="building-dot" />
            <strong>AI 正在搭建知识图谱…</strong>
          </div>
          <p class="muted small mt-8">
            目标「{{ activeGoal.title }}」的知识体系正在生成，完成后会自动出现 3D 图谱。
          </p>
        </div>
      </div>

      <div v-else-if="!graphNodes.length && !loading" class="kg-empty">
        <div class="card" style="max-width: 380px; text-align: center">
          <strong>知识图谱暂未生成</strong>
          <p class="muted small mt-8">请确认已在后端配置可用的 LLM API Key，然后重新激活目标。</p>
        </div>
      </div>
    </div>

    <PlanningPanel
      :goal="activeGoal"
      :path="path"
      :points="points"
      :selected-point="selectedPoint"
      :today-tasks="dashboard?.today_tasks ?? []"
      :due-review-count="dueReviewCount"
      :proposal="planProposal"
      :building="building"
      :generating-tasks="generatingTasks"
      @select-node="selectNode"
      @refresh="goalStore.loadDashboard()"
      @generate-tasks="generateTasks"
      @explain="requestExplain"
    />
  </div>
</template>

<style scoped>
.link-btn {
  background: none;
  border: none;
  padding: 0;
  color: var(--accent);
  font-size: 13px;
  cursor: pointer;
  margin: 0 6px 0 2px;
}

.link-btn:hover:not(:disabled) {
  text-decoration: underline;
}

.link-btn:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.building-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: var(--accent);
  animation: pulse 1.2s ease-in-out infinite;
  flex: none;
  display: inline-block;
}
</style>
