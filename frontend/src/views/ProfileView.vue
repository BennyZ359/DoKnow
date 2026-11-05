<script setup lang="ts">
import { onMounted, reactive, ref, watch } from 'vue'
import { authApi } from '@/api/auth'
import { settingsApi } from '@/api/settings'
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

/* ---------- 模型设置（全局，作用于所有 AI 功能） ---------- */

interface ProviderPreset {
  value: string
  label: string
  baseUrl: string
  model: string
}

const PROVIDERS: ProviderPreset[] = [
  { value: 'openai', label: 'OpenAI', baseUrl: 'https://api.openai.com/v1', model: 'gpt-4o-mini' },
  { value: 'deepseek', label: 'DeepSeek', baseUrl: 'https://api.deepseek.com/v1', model: 'deepseek-chat' },
  { value: 'moonshot', label: 'Moonshot 月之暗面', baseUrl: 'https://api.moonshot.cn/v1', model: 'moonshot-v1-8k' },
  { value: 'qwen', label: '通义千问', baseUrl: 'https://dashscope.aliyuncs.com/compatible-mode/v1', model: 'qwen-plus' },
  { value: 'ollama', label: 'Ollama（本地）', baseUrl: 'http://host.docker.internal:11434/v1', model: 'qwen2.5' },
  { value: 'custom', label: '自定义', baseUrl: '', model: '' },
]

const llm = reactive({ provider: 'openai', base_url: 'https://api.openai.com/v1', api_key: '', model: 'gpt-4o-mini' })
const llmBusy = ref(false)
const llmConfigured = ref(false)
const keyHint = ref('')

function onProviderChange(): void {
  const preset = PROVIDERS.find((p) => p.value === llm.provider)
  if (preset && preset.value !== 'custom') {
    llm.base_url = preset.baseUrl
    llm.model = preset.model
  }
}

async function loadLlm(): Promise<void> {
  try {
    const res = await settingsApi.getLlm()
    llmConfigured.value = res.configured
    const f = res.fields ?? {}
    if (f.provider) llm.provider = String(f.provider)
    if (f.base_url) llm.base_url = String(f.base_url)
    if (f.model) llm.model = String(f.model)
    keyHint.value = f.api_key_hint ? String(f.api_key_hint) : ''
  } catch {
    /* 未配置或暂时不可用，保持空表单 */
  }
}

async function saveLlm(): Promise<void> {
  if (!llm.base_url.trim() && !llm.api_key.trim()) {
    toast.error('请至少填写 Base URL 或 API Key')
    return
  }
  llmBusy.value = true
  try {
    const res = await settingsApi.updateLlm({
      provider: llm.provider,
      base_url: llm.base_url.trim() || undefined,
      api_key: llm.api_key.trim() || undefined,
      model: llm.model.trim() || undefined,
    })
    llmConfigured.value = res.configured
    keyHint.value = (res.fields?.api_key_hint as string) ?? ''
    llm.api_key = ''
    toast.success('模型已保存，所有 AI 功能将使用该配置')
  } catch (e) {
    toast.error(e instanceof Error ? e.message : '保存失败，请重试')
  } finally {
    llmBusy.value = false
  }
}

async function resetLlm(): Promise<void> {
  llmBusy.value = true
  try {
    await settingsApi.clearLlm()
    llmConfigured.value = false
    keyHint.value = ''
    llm.api_key = ''
    toast.info('已清除模型配置，恢复使用默认模型')
  } catch (e) {
    toast.error(e instanceof Error ? e.message : '操作失败，请重试')
  } finally {
    llmBusy.value = false
  }
}

onMounted(loadLlm)
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

    <!-- 模型设置 -->
    <div class="card model-card">
      <div class="row between">
        <div>
          <h2 class="model-title">模型设置</h2>
          <p class="page-sub">配置任意 OpenAI 兼容模型，所有 AI 功能（知识图谱、课程、任务、讲解）都会使用它</p>
        </div>
        <span class="badge" :class="llmConfigured ? 'is-success' : 'is-muted'">
          {{ llmConfigured ? '已配置' : '未配置' }}
        </span>
      </div>

      <div class="field mt-16">
        <label>提供商</label>
        <select v-model="llm.provider" class="select" @change="onProviderChange">
          <option v-for="p in PROVIDERS" :key="p.value" :value="p.value">{{ p.label }}</option>
        </select>
      </div>

      <div class="field">
        <label>请求地址（Base URL）</label>
        <input v-model="llm.base_url" class="input" type="url" placeholder="https://api.example.com/v1" />
      </div>

      <div class="field">
        <label>API Key</label>
        <input v-model="llm.api_key" class="input" type="password" placeholder="sk-…" autocomplete="off" />
        <p class="field-hint">
          {{ keyHint ? `当前已保存 ${keyHint}，留空则保持不变` : '填写你的密钥' }}
        </p>
      </div>

      <div class="field">
        <label>模型名称</label>
        <input v-model="llm.model" class="input" type="text" placeholder="gpt-4o-mini / deepseek-chat / qwen-plus" />
      </div>

      <div class="row">
        <button class="btn btn-primary" type="button" :disabled="llmBusy" @click="saveLlm">
          {{ llmBusy ? '保存中…' : '保存模型配置' }}
        </button>
        <button v-if="llmConfigured" class="btn btn-danger" type="button" :disabled="llmBusy" @click="resetLlm">
          恢复默认
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.model-card {
  margin-top: 20px;
}

.model-title {
  font-size: 17px;
  font-weight: 700;
  margin: 0 0 4px;
}
</style>
