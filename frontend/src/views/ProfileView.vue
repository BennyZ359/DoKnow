<script setup lang="ts">
import { reactive, ref, watch } from 'vue'
import { authApi } from '@/api/auth'
import type { ProfileUpdate, UserProfile } from '@/api/types'
import { useAuthStore } from '@/stores/auth'
import { useToastStore } from '@/stores/toast'

const auth = useAuthStore()
const toast = useToastStore()

const busy = ref(false)
const form = reactive({
  learning_style: '',
  preferred_method: '',
  daily_time_budget_minutes: '' as string,
  weekly_target_hours: '' as string,
  timezone: '',
})

const STYLE_OPTIONS = ['', '视觉型', '听觉型', '读写型', '动手实践型']
const METHOD_OPTIONS: { value: string; label: string }[] = [
  { value: '', label: '未设置' },
  { value: 'STUDY', label: '多学（读课程）' },
  { value: 'PRACTICE', label: '多练（做题）' },
  { value: 'EXPLAIN', label: '多讲（复述）' },
  { value: 'REVIEW', label: '多温习' },
]

watch(
  () => auth.profile,
  (p: UserProfile | null) => sync(p),
  { immediate: true },
)

function sync(p: UserProfile | null): void {
  if (!p) return
  form.learning_style = p.learning_style ?? ''
  form.preferred_method = p.preferred_method ?? ''
  form.daily_time_budget_minutes = p.daily_time_budget_minutes != null ? String(p.daily_time_budget_minutes) : ''
  form.weekly_target_hours = p.weekly_target_hours != null ? String(p.weekly_target_hours) : ''
  form.timezone = p.timezone ?? ''
}

async function save(): Promise<void> {
  const patch: ProfileUpdate = {
    learning_style: form.learning_style || null,
    preferred_method: form.preferred_method || null,
    timezone: form.timezone || null,
  }
  const daily = Number(form.daily_time_budget_minutes)
  if (form.daily_time_budget_minutes !== '') {
    if (!Number.isFinite(daily) || daily < 10 || daily > 600) {
      toast.error('每日学习时长需在 10-600 分钟之间')
      return
    }
    patch.daily_time_budget_minutes = daily
  }
  const weekly = Number(form.weekly_target_hours)
  if (form.weekly_target_hours !== '') {
    if (!Number.isFinite(weekly) || weekly < 0.5 || weekly > 80) {
      toast.error('每周目标小时数需在 0.5-80 之间')
      return
    }
    patch.weekly_target_hours = weekly
  }

  busy.value = true
  try {
    await authApi.updateMe(patch)
    await auth.fetchMe()
    toast.success('已保存，AI 安排任务时会参考你的偏好')
  } catch (e) {
    toast.error(e instanceof Error ? e.message : '保存失败，请重试')
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div style="max-width: 620px; margin: 0 auto">
    <div class="page-header">
      <div>
        <h1 class="page-title">个人设置</h1>
        <p class="page-sub">学习偏好会进入用户画像，影响任务安排与课程风格</p>
      </div>
    </div>

    <div class="card">
      <div class="field">
        <label>邮箱</label>
        <input class="input" :value="auth.user?.email ?? ''" disabled />
      </div>

      <div class="field">
        <label>学习风格</label>
        <select v-model="form.learning_style" class="select">
          <option v-for="opt in STYLE_OPTIONS" :key="opt" :value="opt">
            {{ opt || '未设置' }}
          </option>
        </select>
      </div>

      <div class="field">
        <label>偏好的学习方式</label>
        <select v-model="form.preferred_method" class="select">
          <option v-for="opt in METHOD_OPTIONS" :key="opt.value" :value="opt.value">
            {{ opt.label }}
          </option>
        </select>
      </div>

      <div class="row wrap" style="gap: 16px">
        <div class="field flex-1">
          <label>每日学习时长（分钟）</label>
          <input v-model="form.daily_time_budget_minutes" class="input" type="number" min="10" max="600" placeholder="如 45" />
        </div>
        <div class="field flex-1">
          <label>每周目标（小时）</label>
          <input v-model="form.weekly_target_hours" class="input" type="number" min="0.5" max="80" step="0.5" placeholder="如 5" />
        </div>
      </div>

      <div class="field">
        <label>时区</label>
        <input v-model="form.timezone" class="input" placeholder="如 Asia/Shanghai" />
        <p class="field-hint">用于安排每日任务与温习的时间点</p>
      </div>

      <button class="btn btn-primary" type="button" :disabled="busy" @click="save">
        {{ busy ? '保存中…' : '保存' }}
      </button>
    </div>
  </div>
</template>
