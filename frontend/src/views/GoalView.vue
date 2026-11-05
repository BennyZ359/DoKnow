<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { goalsApi } from '@/api/goals'
import { tasksApi } from '@/api/tasks'
import EmptyState from '@/components/EmptyState.vue'
import ProgressBar from '@/components/ProgressBar.vue'
import Spinner from '@/components/Spinner.vue'
import type { OverviewResponse } from '@/api/types'
import { useToastStore } from '@/stores/toast'
import {
  difficultyLabel,
  fmtDate,
  fmtMinutes,
  fmtPercent,
  goalStatusLabel,
  masteryClass,
  masteryLabel,
  statusClass,
} from '@/utils/format'

const route = useRoute()
const router = useRouter()
const toast = useToastStore()

const goalId = computed(() => route.params.goalId as string)

const loading = ref(true)
const overview = ref<OverviewResponse | null>(null)
const tab = ref<'path' | 'points' | 'courses'>('path')
const cycling = ref(false)
const explainBusy = ref<string | null>(null)

let pollTimer: ReturnType<typeof setInterval> | undefined
let pollCount = 0

const goal = computed(() => overview.value?.goal ?? null)
const building = computed(() => overview.value !== null && !overview.value.knowledge_system_built)
const path = computed(() => overview.value?.path ?? null)
const points = computed(() => overview.value?.knowledge_points ?? [])
const courses = computed(() => overview.value?.courses ?? [])

async function load(silent = false): Promise<void> {
  if (!silent) loading.value = true
  try {
    overview.value = await goalsApi.overview(goalId.value)
    // 知识体系仍在搭建时轮询，直到 AI 完成或长时间未果
    if (building.value) {
      schedulePoll()
    } else {
      stopPoll()
    }
  } catch (e) {
    toast.error(e instanceof Error ? e.message : '加载失败')
  } finally {
    loading.value = false
  }
}

function schedulePoll(): void {
  if (pollTimer || pollCount > 60) return
  pollTimer = setInterval(() => {
    pollCount++
    if (!building.value) {
      stopPoll()
      toast.success('知识体系搭建完成！')
      void load(true)
    } else {
      void load(true)
    }
  }, 5000)
}

function stopPoll(): void {
  if (pollTimer) clearInterval(pollTimer)
  pollTimer = undefined
  pollCount = 0
}

async function managerCycle(): Promise<void> {
  cycling.value = true
  try {
    await goalsApi.triggerManagerCycle(goalId.value)
    toast.success('已请管家分析当前学习状态，稍后可在首页看到动态')
  } catch (e) {
    toast.error(e instanceof Error ? e.message : '操作失败')
  } finally {
    cycling.value = false
  }
}

async function explainKp(kpId: string): Promise<void> {
  explainBusy.value = kpId
  try {
    await tasksApi.createExplain(goalId.value, kpId)
    toast.success('已创建讲解任务——用自己的话讲一遍，才算真正掌握')
    router.push({ name: 'tasks' })
  } catch (e) {
    toast.error(e instanceof Error ? e.message : '创建失败')
  } finally {
    explainBusy.value = null
  }
}

onMounted(() => void load())
onUnmounted(stopPoll)
</script>

<template>
  <div>
    <div v-if="loading" class="card"><Spinner /></div>

    <template v-else-if="goal">
      <div class="page-header">
        <div>
          <div class="row">
            <h1 class="page-title">{{ goal.title }}</h1>
            <span class="badge" :class="statusClass(goal.status)">{{ goalStatusLabel(goal.status) }}</span>
          </div>
          <p class="page-sub">
            <template v-if="goal.target_level">{{ goal.target_level }} · </template>
            <template v-if="goal.deadline">截止 {{ fmtDate(goal.deadline) }} · </template>
            进度 {{ fmtPercent(goal.progress) }}
          </p>
        </div>
        <div class="row wrap">
          <button class="btn btn-ghost btn-sm" type="button" :disabled="cycling" @click="managerCycle">
            {{ cycling ? '分析中…' : '🐠 让管家看看' }}
          </button>
          <RouterLink class="btn btn-ghost btn-sm" :to="{ name: 'sources', params: { goalId: goal.id } }">
            参考资料
          </RouterLink>
          <RouterLink class="btn btn-soft btn-sm" :to="{ name: 'tasks' }">今日任务</RouterLink>
        </div>
      </div>

      <div class="card">
        <ProgressBar :value="goal.progress" />
        <div v-if="building" class="building-banner">
          <span class="spinner-inline" /> AI 正在搭建知识体系、规划学习路径并生成课程，完成后自动刷新…
        </div>
      </div>

      <div class="tabs mt-16">
        <button class="tab" :class="{ active: tab === 'path' }" type="button" @click="tab = 'path'">
          学习路径 {{ path ? `· ${path.nodes.length}` : '' }}
        </button>
        <button class="tab" :class="{ active: tab === 'points' }" type="button" @click="tab = 'points'">
          知识点 · {{ points.length }}
        </button>
        <button class="tab" :class="{ active: tab === 'courses' }" type="button" @click="tab = 'courses'">
          课程 · {{ courses.length }}
        </button>
      </div>

      <!-- 学习路径 -->
      <div v-if="tab === 'path'">
        <div v-if="path && path.nodes.length" class="row-list">
          <div v-for="node in path.nodes" :key="node.order" class="row-item">
            <span class="seq-chip">{{ node.sequence }}</span>
            <div class="row-main">
              <div class="row-title">
                {{ node.knowledge_point?.name ?? '综合评估' }}
                <span v-if="node.knowledge_point" class="muted small">
                  · {{ difficultyLabel(node.knowledge_point.difficulty) }}
                </span>
              </div>
              <div class="row-desc">
                <template v-if="node.reason">{{ node.reason }}</template>
                <template v-if="node.est_minutes"> · 约 {{ fmtMinutes(node.est_minutes) }}</template>
              </div>
            </div>
            <div class="row-side">
              <span
                v-if="node.mastery?.mastery_state"
                class="badge"
                :class="masteryClass(node.mastery.mastery_state)"
              >
                {{ masteryLabel(node.mastery.mastery_state) }}
              </span>
              <span v-else class="badge is-muted">未开始</span>
            </div>
          </div>
        </div>
        <div v-else class="card">
          <EmptyState
            icon="🧭"
            title="学习路径还在规划中"
            :hint="building ? 'AI 正在分析知识依赖关系，稍等片刻' : '知识体系尚未搭建，请稍后刷新'"
          />
        </div>
      </div>

      <!-- 知识点 -->
      <div v-else-if="tab === 'points'">
        <div v-if="points.length" class="grid-cards">
          <div v-for="p in points" :key="p.id" class="card card-hover kp-card">
            <div class="row between">
              <strong>{{ p.name }}</strong>
              <span class="badge is-muted">{{ difficultyLabel(p.difficulty) }}</span>
            </div>
            <p class="muted small mt-4">{{ p.description ?? '暂无简介' }}</p>
            <p class="muted small mt-8">约 {{ fmtMinutes(p.est_minutes) }}<template v-if="p.tags.length"> · {{ p.tags.join(' / ') }}</template></p>
            <div class="row mt-12">
              <RouterLink
                class="btn btn-soft btn-sm"
                :to="{ name: 'practice', params: { kpId: p.id }, query: { goal: goal.id } }"
              >
                练一练
              </RouterLink>
              <button
                class="btn btn-ghost btn-sm"
                type="button"
                :disabled="explainBusy === p.id"
                @click="explainKp(p.id)"
              >
                {{ explainBusy === p.id ? '创建中…' : '讲一讲' }}
              </button>
            </div>
          </div>
        </div>
        <div v-else class="card">
          <EmptyState icon="🧩" title="知识点还在抽取中" :hint="building ? 'AI 正在拆解你的目标' : '稍后刷新看看'" />
        </div>
      </div>

      <!-- 课程 -->
      <div v-else>
        <div v-if="courses.length" class="grid-cards">
          <RouterLink
            v-for="c in courses"
            :key="c.id"
            class="card card-hover course-card"
            :to="{ name: 'course', params: { courseId: c.id } }"
          >
            <div class="row between">
              <strong>{{ c.title }}</strong>
              <span class="badge" :class="statusClass(c.status)">{{ c.status === 'PUBLISHED' ? '已发布' : (c.status ?? '生成中') }}</span>
            </div>
            <p class="muted small mt-4">{{ c.description ?? 'AI 生成的配套课程' }}</p>
            <p class="muted small mt-8">约 {{ fmtMinutes(c.total_est_minutes) }}</p>
          </RouterLink>
        </div>
        <div v-else class="card">
          <EmptyState
            icon="📚"
            title="课程还在生成中"
            :hint="building ? '知识体系完成后，AI 会按路径生成课程' : '暂无已发布课程，稍后刷新'"
          />
        </div>
      </div>
    </template>

    <div v-else class="card">
      <EmptyState icon="🤔" title="目标不存在或无权访问">
        <RouterLink class="btn btn-primary" :to="{ name: 'dashboard' }">回到首页</RouterLink>
      </EmptyState>
    </div>
  </div>
</template>

<style scoped>
.building-banner {
  margin-top: 12px;
  padding: 10px 14px;
  border-radius: 8px;
  background: var(--accent-soft);
  color: var(--accent-strong);
  font-size: 13px;
  display: flex;
  align-items: center;
  gap: 10px;
}

.spinner-inline {
  width: 14px;
  height: 14px;
  border: 2px solid rgba(47, 123, 246, 0.25);
  border-top-color: var(--accent);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
  flex: none;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

.seq-chip {
  width: 30px;
  height: 30px;
  flex: none;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 10px;
  background: var(--accent-soft);
  color: var(--accent);
  font-weight: 600;
  font-size: 13px;
}

.kp-card,
.course-card {
  color: inherit;
  display: block;
}

.kp-card:hover,
.course-card:hover {
  color: inherit;
}
</style>
