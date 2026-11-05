<script setup lang="ts">
/**
 * Right-hand planning panel for the knowledge-graph home (the ~1/3 column).
 *
 * Presentational: receives the active goal's loaded data and emits intents
 * (focus a node, generate tasks, request an explanation, refresh). Shows the
 * selected knowledge-point detail on top, then the learning path, today's
 * tasks, spaced-review counts and any AI plan proposal.
 */
import { computed } from 'vue'
import PlanProposalCard from '@/components/PlanProposalCard.vue'
import ProgressBar from '@/components/ProgressBar.vue'
import TaskCard from '@/components/TaskCard.vue'
import type { KnowledgePoint, LearningPath, MasteryState, PlanProposal, Task } from '@/api/types'
import {
  difficultyLabel,
  fmtMinutes,
  fmtPercent,
  goalStatusLabel,
  masteryClass,
  masteryLabel,
  statusClass,
} from '@/utils/format'

const props = defineProps<{
  goal: import('@/api/types').Goal
  path: LearningPath | null
  points: KnowledgePoint[]
  selectedPoint: KnowledgePoint | null
  todayTasks: Task[]
  dueReviewCount: number
  proposal: PlanProposal | null
  building: boolean
  generatingTasks: boolean
}>()

const emit = defineEmits<{
  (e: 'select-node', code: string): void
  (e: 'refresh'): void
  (e: 'generate-tasks'): void
  (e: 'explain', code: string): void
}>()

const KNOWLEDGE_TYPE_LABEL: Record<string, string> = {
  CONCEPT: '概念',
  FACT: '事实',
  PROCEDURE: '流程',
  PRINCIPLE: '原理',
  SKILL: '技能',
}

const METHOD_LABEL: Record<string, string> = {
  STUDY: '学',
  PRACTICE: '练',
  APPLY: '用',
  EXPLAIN: '讲',
  REVIEW: '温',
}

const nameByCode = computed(() => Object.fromEntries(props.points.map((p) => [p.code, p.name])))
const pathNodes = computed(() => (props.path ? [...props.path.nodes].sort((a, b) => a.order - b.order) : []))
const masteredCount = computed(
  () => pathNodes.value.filter((n) => n.mastery?.mastery_state === 'MASTERED').length,
)
const visibleTasks = computed(() => props.todayTasks.filter((t) => t.status === 'NOT_STARTED' || t.status === 'IN_PROGRESS').slice(0, 3))
const doneToday = computed(() => props.todayTasks.filter((t) => t.status === 'COMPLETED').length)
</script>

<template>
  <aside class="kg-panel">
    <!-- goal header -->
    <div class="panel-goal">
      <div class="row between">
        <h2 class="panel-goal-title">{{ goal.title }}</h2>
        <span class="badge" :class="statusClass(goal.status)">{{ goalStatusLabel(goal.status) }}</span>
      </div>
      <ProgressBar class="mt-12" :value="goal.progress" />
      <div class="row between muted small mt-8">
        <span>整体进度 {{ fmtPercent(goal.progress) }}</span>
        <span v-if="path">路径 {{ masteredCount }}/{{ pathNodes.length }} 已掌握</span>
      </div>
    </div>

    <!-- selected node detail -->
    <div v-if="selectedPoint" class="kg-node-detail">
      <div class="row between">
        <strong>{{ selectedPoint.name }}</strong>
        <span class="badge is-info">{{ KNOWLEDGE_TYPE_LABEL[selectedPoint.knowledge_type] ?? selectedPoint.knowledge_type }}</span>
      </div>
      <div class="row wrap gap-6 mt-8">
        <span class="badge is-muted">{{ difficultyLabel(selectedPoint.difficulty) }}</span>
        <span class="badge is-muted" v-if="selectedPoint.est_minutes">约 {{ fmtMinutes(selectedPoint.est_minutes) }}</span>
        <span class="badge is-muted" v-for="m in selectedPoint.recommended_methods" :key="m">
          {{ METHOD_LABEL[m] ?? m }}
        </span>
      </div>
      <p v-if="selectedPoint.description" class="muted small mt-8">{{ selectedPoint.description }}</p>
      <div v-if="selectedPoint.prerequisites.length" class="mt-12 small">
        <span class="muted">前置：</span>
        <span v-for="code in selectedPoint.prerequisites" :key="code" class="prereq-chip" @click="emit('select-node', code)">
          {{ nameByCode[code] ?? code }}
        </span>
      </div>
      <button class="btn btn-primary btn-sm btn-block mt-12" type="button" @click="emit('explain', selectedPoint.code)">
        生成讲解任务
      </button>
    </div>

    <!-- AI plan proposal -->
    <PlanProposalCard v-if="proposal" :proposal="proposal" :goal-id="goal.id" @resolved="emit('refresh')" />

    <!-- building hint -->
    <div v-if="building && !points.length" class="card">
      <div class="row">
        <span class="building-dot" />
        <div class="flex-1">
          <strong>AI 正在搭建知识体系…</strong>
          <p class="muted small mt-4">知识图谱会在几秒到几十秒内出现，可稍后回到本页查看。</p>
        </div>
      </div>
    </div>

    <!-- learning path -->
    <section v-if="pathNodes.length" class="panel-section">
      <h3 class="panel-title">学习路径 <span class="muted small">{{ path?.title }}</span></h3>
      <ol class="path-list">
        <li
          v-for="node in pathNodes"
          :key="node.knowledge_point?.code ?? node.sequence"
          class="path-node"
          :class="{ done: node.mastery?.mastery_state === 'MASTERED' }"
          @click="node.knowledge_point && emit('select-node', node.knowledge_point.code)"
        >
          <span class="path-num">{{ node.order }}</span>
          <span class="path-main">
            <span class="path-name">{{ node.knowledge_point?.name ?? node.sequence }}</span>
            <span class="muted small">约 {{ fmtMinutes(node.est_minutes) }}</span>
          </span>
          <span class="badge" :class="masteryClass((node.mastery?.mastery_state ?? null) as MasteryState | null)">
            {{ masteryLabel((node.mastery?.mastery_state ?? null) as MasteryState | null) }}
          </span>
        </li>
      </ol>
    </section>

    <!-- today tasks -->
    <section class="panel-section">
      <div class="row between">
        <h3 class="panel-title">今日任务</h3>
        <RouterLink class="small" :to="{ name: 'tasks' }">查看全部</RouterLink>
      </div>
      <p v-if="todayTasks.length" class="muted small mb-8">
        共 {{ todayTasks.length }} 个 · 已完成 {{ doneToday }}
      </p>
      <div v-if="visibleTasks.length" class="row-list">
        <TaskCard v-for="t in visibleTasks" :key="t.id" :task="t" @updated="emit('refresh')" />
      </div>
      <div v-else class="card">
        <p class="muted small mb-8">今天还没有安排任务。</p>
        <button class="btn btn-primary btn-sm" type="button" :disabled="generatingTasks" @click="emit('generate-tasks')">
          {{ generatingTasks ? '生成中…' : '生成今日任务' }}
        </button>
      </div>
    </section>

    <!-- reviews -->
    <section class="panel-section">
      <div class="row between">
        <h3 class="panel-title">温习</h3>
        <RouterLink class="small" :to="{ name: 'tasks' }">去温习</RouterLink>
      </div>
      <p class="muted small">{{ dueReviewCount ? `${dueReviewCount} 个知识点待温习` : '暂无到期温习' }}</p>
    </section>
  </aside>
</template>

<style scoped>
.panel-goal-title {
  font-size: 17px;
  font-weight: 700;
}

.panel-section {
  margin-top: 22px;
}

.panel-title {
  font-size: 14.5px;
  font-weight: 600;
  display: flex;
  align-items: baseline;
  gap: 6px;
}

.gap-6 {
  gap: 6px;
}

.prereq-chip {
  display: inline-block;
  margin: 2px 4px 2px 0;
  padding: 2px 9px;
  border-radius: 999px;
  background: #eef1f6;
  color: var(--text);
  font-size: 12px;
  cursor: pointer;
}

.prereq-chip:hover {
  color: var(--accent);
  background: var(--accent-soft);
}

.path-list {
  list-style: none;
  margin: 12px 0 0;
  padding: 0;
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.path-node {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 9px 12px;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--surface);
  cursor: pointer;
  transition: all 0.15s ease;
}

.path-node:hover {
  border-color: var(--border-strong);
  box-shadow: var(--shadow);
}

.path-node.done {
  opacity: 0.72;
}

.path-num {
  width: 26px;
  height: 26px;
  flex: none;
  display: grid;
  place-items: center;
  border-radius: 50%;
  background: var(--accent-soft);
  color: var(--accent);
  font-size: 12.5px;
  font-weight: 700;
}

.path-node.done .path-num {
  background: var(--success-soft);
  color: var(--success);
}

.path-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}

.path-name {
  font-size: 13.5px;
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.building-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: var(--accent);
  animation: pulse 1.2s ease-in-out infinite;
  flex: none;
  margin-right: 4px;
}
</style>
