<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { coursesApi } from '@/api/courses'
import { goalsApi } from '@/api/goals'
import EmptyState from '@/components/EmptyState.vue'
import ExerciseCard from '@/components/ExerciseCard.vue'
import Spinner from '@/components/Spinner.vue'
import type { Exercise, KnowledgePoint } from '@/api/types'
import { useToastStore } from '@/stores/toast'
import { difficultyLabel } from '@/utils/format'

const route = useRoute()
const router = useRouter()
const toast = useToastStore()

const kpId = computed(() => route.params.kpId as string)
const goalId = computed(() => (route.query.goal as string | undefined) ?? null)

const loading = ref(true)
const regenerating = ref(false)
const exercises = ref<Exercise[]>([])
const kp = ref<KnowledgePoint | null>(null)

async function load(): Promise<void> {
  if (!goalId.value) {
    toast.error('缺少目标上下文，请从知识点列表进入练习')
    router.replace({ name: 'dashboard' })
    return
  }
  loading.value = true
  try {
    const [res, points] = await Promise.all([
      coursesApi.exercises(kpId.value, goalId.value),
      goalsApi.knowledge(goalId.value),
    ])
    exercises.value = res.exercises
    kp.value = points.points.find((p) => p.id === kpId.value) ?? null
  } catch (e) {
    toast.error(e instanceof Error ? e.message : '练习加载失败')
  } finally {
    loading.value = false
  }
}

async function regenerate(): Promise<void> {
  if (!goalId.value || !exercises.value.length) return
  regenerating.value = true
  try {
    const res = await coursesApi.regenerateExercises(exercises.value[0].id, goalId.value, {
      requirement: '换一批角度不同的练习题，覆盖同一知识点的不同侧面',
      count: 3,
    })
    exercises.value = res.exercises
    toast.success('新的一组练习已生成')
  } catch (e) {
    toast.error(e instanceof Error ? e.message : '生成失败，请重试')
  } finally {
    regenerating.value = false
  }
}

onMounted(load)
</script>

<template>
  <div style="max-width: 760px; margin: 0 auto">
    <div class="page-header">
      <div>
        <p class="page-sub" style="margin: 0 0 4px">
          <RouterLink
            v-if="goalId"
            :to="{ name: 'goal', params: { goalId: goalId } }"
          >返回目标</RouterLink>
        </p>
        <h1 class="page-title">练 · {{ kp?.name ?? '知识点' }}</h1>
        <p v-if="kp" class="page-sub">
          {{ difficultyLabel(kp.difficulty) }}
          <template v-if="kp.tags.length"> · {{ kp.tags.join(' / ') }}</template>
        </p>
      </div>
      <button
        class="btn btn-soft btn-sm"
        type="button"
        :disabled="regenerating || !exercises.length"
        @click="regenerate"
      >
        {{ regenerating ? 'AI 出题中…' : '再来一组' }}
      </button>
    </div>

    <div v-if="loading" class="card">
      <Spinner />
      <p class="muted small text-center">首次进入时 AI 会现做一批题，通常需要几十秒…</p>
    </div>

    <template v-else>
      <div v-if="exercises.length" class="row-list">
        <ExerciseCard
          v-for="ex in exercises"
          :key="ex.id"
          :exercise="ex"
          :goal-id="goalId!"
          @attempted="() => {}"
        />
      </div>
      <div v-else class="card">
        <EmptyState icon="✏️" title="暂无练习题" hint="AI 出题失败或仍在生成，稍后再来试试">
          <button class="btn btn-ghost" type="button" @click="load">重新加载</button>
        </EmptyState>
      </div>
    </template>
  </div>
</template>
