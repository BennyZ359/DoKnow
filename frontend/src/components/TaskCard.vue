<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { coursesApi } from '@/api/courses'
import { tasksApi } from '@/api/tasks'
import type { MasteryState, Task } from '@/api/types'
import { useToastStore } from '@/stores/toast'
import { fmtDate, fmtMinutes, masteryLabel, statusClass, taskStatusLabel, taskTypeLabel } from '@/utils/format'

const props = defineProps<{ task: Task }>()
const emit = defineEmits<{ updated: [] }>()

const router = useRouter()
const toast = useToastStore()

const busy = ref<string | null>(null)
const explainOpen = ref(false)
const explainText = ref('')
const explainResult = ref<Record<string, unknown> | null>(null)

const openable = computed(
  () => props.task.status === 'NOT_STARTED' || props.task.status === 'IN_PROGRESS',
)
const type = computed(() => props.task.task_type ?? 'STUDY')
const openLabel = computed(() =>
  ({ STUDY: '去学习', PRACTICE: '去练习', EXPLAIN: '写讲解' })[type.value],
)

/** Human-readable bits of the (opaque) explain-assessment output. */
const feedback = computed(() => {
  const r = explainResult.value
  if (!r) return []
  const parts: string[] = []
  if (typeof r.score === 'number') parts.push(`得分 ${Math.round((r as { score: number }).score * 100)} 分`)
  if (typeof r.mastery_state === 'string') parts.push(`掌握状态：${masteryLabel(r.mastery_state as MasteryState)}`)
  for (const key of ['feedback', 'comment', 'suggestion', '评语', '建议']) {
    const v = r[key]
    if (typeof v === 'string' && v.trim()) parts.push(v.trim())
  }
  return parts
})

function fail(e: unknown): void {
  toast.error(e instanceof Error ? e.message : '操作失败，请重试')
}

async function open(): Promise<void> {
  if (type.value === 'EXPLAIN') {
    explainOpen.value = !explainOpen.value
    void tasksApi.start(props.task.id).catch(() => {})
    return
  }
  // fire-and-forget: entering the material marks the task IN_PROGRESS
  void tasksApi.start(props.task.id).catch(() => {})
  if (type.value === 'STUDY' && props.task.course_id) {
    router.push({
      name: 'course',
      params: { courseId: props.task.course_id },
      query: { task: props.task.id },
    })
  } else if (type.value === 'PRACTICE' && props.task.knowledge_point_id) {
    router.push({
      name: 'practice',
      params: { kpId: props.task.knowledge_point_id },
      query: { goal: props.task.goal_id, task: props.task.id },
    })
  } else {
    router.push({ name: 'goal', params: { goalId: props.task.goal_id } })
  }
}

async function complete(): Promise<void> {
  busy.value = 'complete'
  try {
    await tasksApi.complete(props.task.id)
    toast.success('任务已完成，继续保持！')
    emit('updated')
  } catch (e) {
    fail(e)
  } finally {
    busy.value = null
  }
}

async function skip(): Promise<void> {
  busy.value = 'skip'
  try {
    await tasksApi.skip(props.task.id)
    toast.info('已跳过该任务')
    emit('updated')
  } catch (e) {
    fail(e)
  } finally {
    busy.value = null
  }
}

async function submitExplanation(): Promise<void> {
  const text = explainText.value.trim()
  if (text.length < 20) {
    toast.error('讲解至少写 20 个字，用自己的话讲讲看')
    return
  }
  busy.value = 'explain'
  try {
    explainResult.value = await coursesApi.explain(props.task.id, text)
    toast.success('讲解已提交，AI 已完成评估')
    emit('updated')
  } catch (e) {
    fail(e)
  } finally {
    busy.value = null
  }
}
</script>

<template>
  <div class="row-item task-card" :class="{ 'is-done': task.status === 'COMPLETED' || task.status === 'SKIPPED' }">
    <span class="type-chip" :class="type">{{ taskTypeLabel(task.task_type) }}</span>
    <div class="row-main">
      <div class="row-title">
        {{ task.title }}
        <span v-if="task.est_minutes" class="muted small">· 约 {{ fmtMinutes(task.est_minutes) }}</span>
        <span v-if="task.due_at" class="muted small">· 截止 {{ fmtDate(task.due_at) }}</span>
      </div>
      <div class="row-desc">{{ task.instructions }}</div>

      <!-- 讲：inline explanation editor -->
      <div v-if="explainOpen" class="explain-box">
        <textarea
          v-model="explainText"
          class="textarea"
          rows="5"
          placeholder="假设面向一位刚入门的朋友，用自己的话完整解释这个知识点（150-400 字）"
          :disabled="busy === 'explain'"
        />
        <div class="row mt-8">
          <button
            class="btn btn-primary btn-sm"
            type="button"
            :disabled="busy === 'explain'"
            @click="submitExplanation"
          >
            {{ busy === 'explain' ? 'AI 评估中…' : '提交讲解' }}
          </button>
          <button class="btn btn-ghost btn-sm" type="button" @click="explainOpen = false">收起</button>
        </div>
        <div v-if="feedback.length" class="feedback-box">
          <div v-for="(line, i) in feedback" :key="i">{{ line }}</div>
        </div>
      </div>
    </div>
    <div class="row-side">
      <span class="badge" :class="statusClass(task.status)">{{ taskStatusLabel(task.status) }}</span>
      <template v-if="openable">
        <button class="btn btn-soft btn-sm" type="button" @click="open">{{ openLabel }}</button>
        <button
          class="btn btn-primary btn-sm"
          type="button"
          :disabled="busy === 'complete'"
          @click="complete"
        >
          完成
        </button>
        <button
          class="btn btn-ghost btn-sm"
          type="button"
          :disabled="busy === 'skip'"
          @click="skip"
        >
          跳过
        </button>
      </template>
    </div>
  </div>
</template>

<style scoped>
.task-card.is-done {
  opacity: 0.62;
}

.explain-box {
  margin-top: 12px;
}

.feedback-box {
  margin-top: 10px;
  padding: 10px 14px;
  border-radius: 8px;
  background: var(--accent-soft);
  font-size: 13px;
  color: #2c3e5d;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
</style>
