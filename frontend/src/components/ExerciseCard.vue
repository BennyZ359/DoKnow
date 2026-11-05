<script setup lang="ts">
import { computed, ref } from 'vue'
import { coursesApi } from '@/api/courses'
import type { AttemptResponse, Exercise } from '@/api/types'
import { useToastStore } from '@/stores/toast'
import { difficultyLabel } from '@/utils/format'

const props = defineProps<{ exercise: Exercise; goalId: string }>()
const emit = defineEmits<{ attempted: [result: AttemptResponse] }>()

const toast = useToastStore()

const selected = ref<string | null>(null)
const text = ref('')
const busy = ref(false)
const result = ref<AttemptResponse | null>(null)

const isChoice = computed(() => props.exercise.options.length > 0)
const submitted = computed(() => result.value !== null)

async function submit(): Promise<void> {
  if (isChoice.value && !selected.value) {
    toast.error('先选择一个答案')
    return
  }
  if (!isChoice.value && !text.value.trim()) {
    toast.error('先写下你的答案')
    return
  }
  busy.value = true
  try {
    result.value = await coursesApi.attempt(
      props.exercise.id,
      props.goalId,
      isChoice.value ? { choice: selected.value! } : { text: text.value.trim() },
    )
    if (result.value.status === 'graded') {
      if (result.value.is_correct) toast.success('答对了！这个点你掌握得不错')
      else toast.info('答错了，回顾一下课程内容再试试')
    } else {
      toast.success('已提交，AI 批改中，稍后可在掌握度里看到结果')
    }
    emit('attempted', result.value)
  } catch (e) {
    toast.error(e instanceof Error ? e.message : '提交失败，请重试')
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="card exercise-card">
    <div class="row between mb-8">
      <div class="row-title">{{ exercise.prompt }}</div>
      <span v-if="exercise.difficulty" class="badge is-muted">{{ difficultyLabel(exercise.difficulty) }}</span>
    </div>

    <!-- 选择题 -->
    <div v-if="isChoice" class="options">
      <label
        v-for="opt in exercise.options"
        :key="opt"
        class="option"
        :class="{ picked: selected === opt, right: submitted && result?.is_correct && selected === opt, dim: submitted && selected !== opt }"
      >
        <input v-model="selected" type="radio" :value="opt" :disabled="submitted" />
        <span>{{ opt }}</span>
      </label>
    </div>

    <!-- 主观题 -->
    <textarea
      v-else
      v-model="text"
      class="textarea"
      rows="4"
      placeholder="写下你的答案（AI 会自动批改）"
      :disabled="submitted"
    />

    <!-- 提交 / 结果 -->
    <div class="row mt-12">
      <button
        v-if="!submitted"
        class="btn btn-primary"
        type="button"
        :disabled="busy"
        @click="submit"
      >
        {{ busy ? '提交中…' : '提交答案' }}
      </button>
      <template v-else>
        <span v-if="result?.status === 'graded'" class="badge" :class="result?.is_correct ? 'is-success' : 'is-danger'">
          {{ result?.is_correct ? '答对了' : '答错了' }}
        </span>
        <span v-else class="badge is-info">AI 批改中</span>
        <span class="muted small">掌握度已更新，可继续练习其他知识点</span>
      </template>
    </div>
  </div>
</template>

<style scoped>
.exercise-card {
  padding: 18px 20px;
}

.exercise-card .row-title {
  font-size: 14.5px;
  font-weight: 600;
  white-space: pre-wrap;
}

.options {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 10px;
}

.option {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 14px;
  border: 1px solid var(--border-strong);
  border-radius: 10px;
  cursor: pointer;
  transition: all 0.15s ease;
  font-size: 14px;
}

.option:hover:not(.dim) {
  border-color: var(--accent);
  background: var(--accent-soft);
}

.option.picked {
  border-color: var(--accent);
  background: var(--accent-soft);
}

.option.right {
  border-color: var(--success);
  background: var(--success-soft);
}

.option.dim {
  opacity: 0.55;
}

.option input {
  accent-color: var(--accent);
}
</style>
