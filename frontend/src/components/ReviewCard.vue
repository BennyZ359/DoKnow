<script setup lang="ts">
import { ref } from 'vue'
import { tasksApi } from '@/api/tasks'
import type { Review } from '@/api/types'
import { useToastStore } from '@/stores/toast'
import { fmtDate, statusClass, reviewStatusLabel } from '@/utils/format'

const props = defineProps<{ review: Review; kpName?: string }>()
const emit = defineEmits<{ updated: [] }>()

const toast = useToastStore()
const busy = ref(false)

const outcomes = [
  { label: '记得牢', score: 0.9, cls: 'btn-primary' },
  { label: '有点模糊', score: 0.5, cls: 'btn-ghost' },
  { label: '想不起来了', score: 0.2, cls: 'btn-danger' },
]

const actionable = () => props.review.status === 'PENDING' || props.review.status === 'DUE'

async function complete(score: number): Promise<void> {
  busy.value = true
  try {
    const res = await tasksApi.completeReview(props.review.id, score)
    if (res.already_completed) toast.info('这条温习之前已完成过啦')
    else if (score >= 0.5) toast.success('很棒！已按遗忘曲线安排下一次温习')
    else toast.info('没关系，温习节奏已重置，从第 1 天重新开始')
    emit('updated')
  } catch (e) {
    toast.error(e instanceof Error ? e.message : '操作失败，请重试')
  } finally {
    busy.value = false
  }
}

async function skip(): Promise<void> {
  busy.value = true
  try {
    await tasksApi.skipReview(props.review.id)
    toast.info('已跳过这条温习')
    emit('updated')
  } catch (e) {
    toast.error(e instanceof Error ? e.message : '操作失败，请重试')
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="row-item">
    <span class="type-chip review-chip">温</span>
    <div class="row-main">
      <div class="row-title">{{ kpName ?? '知识点温习' }}</div>
      <div class="row-desc">
        <template v-if="review.review_type === 'WEAKNESS'">薄弱点巩固</template>
        <template v-else>遗忘曲线温习</template>
        <template v-if="review.due_at"> · 应于 {{ fmtDate(review.due_at) }} 温习</template>
        <template v-if="review.interval_days"> · 当前间隔 {{ review.interval_days }} 天</template>
      </div>
    </div>
    <div class="row-side">
      <span class="badge" :class="statusClass(review.status)">{{ reviewStatusLabel(review.status) }}</span>
      <template v-if="actionable()">
        <button
          v-for="o in outcomes"
          :key="o.label"
          class="btn btn-sm"
          :class="o.cls"
          type="button"
          :disabled="busy"
          @click="complete(o.score)"
        >
          {{ o.label }}
        </button>
        <button class="btn btn-ghost btn-sm" type="button" :disabled="busy" @click="skip">跳过</button>
      </template>
    </div>
  </div>
</template>

<style scoped>
.review-chip {
  background: var(--success-soft);
  color: var(--success);
}
</style>
