<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { tasksApi } from '@/api/tasks'
import { goalsApi } from '@/api/goals'
import EmptyState from '@/components/EmptyState.vue'
import ReviewCard from '@/components/ReviewCard.vue'
import Spinner from '@/components/Spinner.vue'
import TaskCard from '@/components/TaskCard.vue'
import type { Review, Task, TaskType } from '@/api/types'
import { useGoalStore } from '@/stores/goal'
import { useToastStore } from '@/stores/toast'

const goalStore = useGoalStore()
const toast = useToastStore()

const loading = ref(true)
const generating = ref(false)
const scope = ref<'today' | 'all'>('today')
const tasks = ref<Task[]>([])
const reviews = ref<Review[]>([])
const kpNames = ref<Record<string, string>>({})

const goal = computed(() => goalStore.activeGoal)
const todayIso = () => new Date().toISOString().slice(0, 10)

const typeGroups = computed<
  { key: TaskType | 'OTHER'; label: string; chip: string; items: Task[] }[]
>(() => {
  const defs: { key: TaskType | 'OTHER'; label: string; chip: string }[] = [
    { key: 'STUDY', label: '学习任务', chip: '学' },
    { key: 'PRACTICE', label: '练习任务', chip: '练' },
    { key: 'EXPLAIN', label: '讲解任务', chip: '讲' },
    { key: 'OTHER', label: '其他任务', chip: '任' },
  ]
  return defs
    .map((d) => ({
      ...d,
      items: tasks.value.filter((t) => (t.task_type ?? 'OTHER') === d.key),
    }))
    .filter((g) => g.items.length > 0)
})

const dueReviews = computed(() => reviews.value.filter((r) => r.status === 'DUE'))
const upcomingReviews = computed(() => reviews.value.filter((r) => r.status === 'PENDING'))

async function load(): Promise<void> {
  loading.value = true
  try {
    await goalStore.ensureDashboard()
    const goalId = goalStore.activeGoalId
    if (!goalId) {
      loading.value = false
      return
    }
    const [taskRes, reviewRes] = await Promise.all([
      tasksApi.list({ goal_id: goalId, ...(scope.value === 'today' ? { day: todayIso() } : {}) }),
      tasksApi.listReviews(),
    ])
    tasks.value = taskRes.tasks
    reviews.value = reviewRes.reviews
    void loadKpNames(goalId)
  } catch (e) {
    toast.error(e instanceof Error ? e.message : '加载失败，请刷新重试')
  } finally {
    loading.value = false
  }
}

async function loadKpNames(goalId: string): Promise<void> {
  try {
    const points = (await goalsApi.knowledge(goalId)).points
    kpNames.value = Object.fromEntries(points.map((p) => [p.id, p.name]))
  } catch {
    // 知识体系可能仍在搭建
  }
}

async function generate(): Promise<void> {
  const goalId = goalStore.activeGoalId
  if (!goalId) return
  generating.value = true
  try {
    const res = await tasksApi.generate(goalId)
    toast.success(res.created > 0 ? `已生成 ${res.created} 个任务` : '任务已就绪')
    scope.value = 'today'
    await load()
  } catch (e) {
    toast.error(e instanceof Error ? e.message : '生成失败，请重试')
  } finally {
    generating.value = false
  }
}

onMounted(load)
</script>

<template>
  <div>
    <div class="page-header">
      <div>
        <h1 class="page-title">今日任务</h1>
        <p class="page-sub" v-if="goal">{{ goal.title }}</p>
      </div>
      <div class="row wrap">
        <div class="tabs" style="margin: 0; border: none">
          <button class="tab" :class="{ active: scope === 'today' }" type="button" @click="scope = 'today'; load()">
            今日
          </button>
          <button class="tab" :class="{ active: scope === 'all' }" type="button" @click="scope = 'all'; load()">
            全部
          </button>
        </div>
        <button class="btn btn-soft btn-sm" type="button" :disabled="generating || !goal" @click="generate">
          {{ generating ? '生成中…' : '生成任务' }}
        </button>
      </div>
    </div>

    <div v-if="loading" class="card"><Spinner /></div>

    <template v-else-if="!goal">
      <div class="card">
        <EmptyState icon="🎯" title="还没有进行中的学习目标" hint="创建目标后，AI 才能为你安排每天的任务">
          <RouterLink class="btn btn-primary" :to="{ name: 'goal-new' }">创建学习目标</RouterLink>
        </EmptyState>
      </div>
    </template>

    <template v-else>
      <div v-if="tasks.length">
        <div v-for="group in typeGroups" :key="group.key" class="section">
          <div class="section-head">
            <h2 class="section-title">
              <span class="type-chip" :class="group.key">{{ group.chip }}</span>
              {{ group.label }}
              <span class="muted small">{{ group.items.length }}</span>
            </h2>
          </div>
          <div class="row-list">
            <TaskCard v-for="t in group.items" :key="t.id" :task="t" @updated="load" />
          </div>
        </div>
      </div>

      <div v-else class="card">
        <EmptyState icon="🗓️" title="这里还没有任务" hint="点击「生成任务」，AI 会按学习路径与掌握度安排学·练·讲">
          <button class="btn btn-primary" type="button" :disabled="generating" @click="generate">
            {{ generating ? '生成中…' : '生成任务' }}
          </button>
        </EmptyState>
      </div>

      <!-- 温习 -->
      <div class="section">
        <div class="section-head">
          <h2 class="section-title">待温习 <span class="muted small">{{ dueReviews.length }}</span></h2>
        </div>
        <div v-if="dueReviews.length" class="row-list">
          <ReviewCard
            v-for="r in dueReviews"
            :key="r.id"
            :review="r"
            :kp-name="kpNames[r.knowledge_point_id]"
            @updated="load"
          />
        </div>
        <p v-else class="muted small">暂无到期温习。</p>
      </div>

      <div v-if="upcomingReviews.length" class="section">
        <div class="section-head">
          <h2 class="section-title">即将温习 <span class="muted small">{{ upcomingReviews.length }}</span></h2>
        </div>
        <div class="row-list">
          <ReviewCard
            v-for="r in upcomingReviews"
            :key="r.id"
            :review="r"
            :kp-name="kpNames[r.knowledge_point_id]"
            @updated="load"
          />
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.type-chip.OTHER {
  background: #eef1f6;
  color: var(--muted);
}
</style>
