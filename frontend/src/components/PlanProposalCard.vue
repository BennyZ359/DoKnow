<script setup lang="ts">
import { ref } from 'vue'
import { goalsApi } from '@/api/goals'
import type { PlanProposal } from '@/api/types'
import { useToastStore } from '@/stores/toast'
import { fmtRelative } from '@/utils/format'

const props = defineProps<{ proposal: PlanProposal; goalId: string }>()
const emit = defineEmits<{ resolved: [] }>()

const toast = useToastStore()
const busy = ref(false)

async function decide(accept: boolean): Promise<void> {
  busy.value = true
  try {
    const res = await goalsApi.confirmPlanAdjustment(props.goalId, accept)
    if (res.accepted) toast.success('已采纳建议，AI 正在重新规划学习路径…')
    else toast.info('已保留当前计划')
    emit('resolved')
  } catch (e) {
    toast.error(e instanceof Error ? e.message : '操作失败，请重试')
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="card proposal-card">
    <div class="row">
      <span class="proposal-icon">🐠</span>
      <div class="flex-1">
        <div class="row between">
          <strong>AI 学习管家建议调整计划</strong>
          <span class="muted small">{{ fmtRelative(proposal.proposed_at) }}</span>
        </div>
        <p class="mt-8">{{ proposal.reason }}</p>
        <div class="row mt-12">
          <button class="btn btn-primary btn-sm" type="button" :disabled="busy" @click="decide(true)">
            采纳调整
          </button>
          <button class="btn btn-ghost btn-sm" type="button" :disabled="busy" @click="decide(false)">
            暂不调整
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.proposal-card {
  border-color: #cfe0ff;
  background: linear-gradient(0deg, rgba(47, 123, 246, 0.04), rgba(47, 123, 246, 0.04)), var(--surface);
}

.proposal-icon {
  font-size: 26px;
  width: 44px;
  height: 44px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--accent-soft);
  border-radius: 12px;
  flex: none;
}

.proposal-card p {
  font-size: 13.5px;
  color: #3b4a66;
}
</style>
