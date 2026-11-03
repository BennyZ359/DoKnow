<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { api } from '../api'
import type { Settings } from '../api'

interface Check {
  name: string
  status: 'ok' | 'warning' | 'error' | 'pending'
  detail: string
  action: string
}
interface Report {
  status: string
  mode: string
  database: string
  checks: Check[]
  read_only: boolean
}
const emit = defineEmits<{ settings: [Settings] }>()
const report = ref<Report | null>(null)
const busy = ref(false)
const error = ref('')
const checkedAt = ref('')
const names: Record<string, string> = { backend: '后端服务', mode: '运行模式', database: '数据库' }
const labels = { ok: '正常', warning: '需留意', error: '需处理', pending: '待初始化' }
let controller: AbortController | null = null
let disposed = false

async function refresh() {
  if (busy.value) return
  busy.value = true
  error.value = ''
  controller = new AbortController()
  const timer = window.setTimeout(() => controller?.abort(), 8000)
  try {
    const [diagnostics, settings] = await Promise.allSettled([
      api<Report>('/diagnostics', { signal: controller.signal }),
      api<Settings>('/settings', { signal: controller.signal }),
    ])
    if (disposed) return
    if (settings.status === 'fulfilled') emit('settings', settings.value)
    if (diagnostics.status === 'rejected') throw diagnostics.reason
    report.value = diagnostics.value
    checkedAt.value = new Date().toLocaleTimeString()
    if (settings.status === 'rejected')
      error.value = '运行状态已更新，模型说明未能同步，请再次刷新。'
  } catch {
    if (!disposed) {
      report.value = null
      checkedAt.value = ''
      error.value =
        '无法读取运行状态。请在项目目录运行 .\\doknow.ps1 diagnose，处理故障后再次刷新。'
    }
  } finally {
    window.clearTimeout(timer)
    if (!disposed) busy.value = false
  }
}
onMounted(refresh)
onUnmounted(() => {
  disposed = true
  controller?.abort()
})
</script>

<template>
  <section class="runtime-panel" aria-labelledby="runtime-heading" :aria-busy="busy">
    <div class="runtime-heading">
      <div>
        <h2 id="runtime-heading">运行状态</h2>
        <p>只读检查，不升级数据库，也不调用模型。前端页面已加载。</p>
      </div>
      <button class="button secondary" :aria-disabled="busy" @click="refresh">
        {{ busy ? '正在检查…' : '刷新运行状态' }}
      </button>
    </div>
    <p v-if="error" role="alert" class="runtime-error">{{ error }}</p>
    <p role="status" aria-live="polite">
      {{
        busy
          ? '正在读取最新状态…'
          : checkedAt
            ? `已于 ${checkedAt} 检查；状态可能随服务变化。`
            : '尚未获得当前状态。'
      }}
    </p>
    <dl v-if="report && !busy" class="runtime-checks">
      <div v-for="check in report.checks" :key="check.name">
        <dt>
          {{ names[check.name] || check.name }}
          <span :class="['runtime-badge', check.status]">{{ labels[check.status] }}</span>
        </dt>
        <dd>
          {{ check.detail }}
          <p v-if="check.action">{{ check.action }}</p>
        </dd>
      </div>
    </dl>
    <details class="runtime-help">
      <summary>服务无法连接时如何处理</summary>
      <ol>
        <li>在项目目录运行 <code>.\doknow.ps1 diagnose</code> 查看依赖、端口与数据库检查。</li>
        <li>按提示安装缺失依赖，或选择空闲端口。已有学习数据先备份再重启。</li>
        <li>
          运行 <code>.\doknow.ps1 start</code>，返回页面刷新状态。需要停止时运行
          <code>.\doknow.ps1 stop</code>。
        </li>
      </ol>
      <p>
        独立体验可使用
        <code>start --demo</code>；其数据库单独保存。配置已填写不代表模型连通性已验证。
      </p>
    </details>
  </section>
</template>

<style scoped>
.runtime-panel {
  padding: 24px;
  margin-bottom: 24px;
  border: 1px solid var(--line);
  border-radius: 16px;
  background: white;
  overflow-wrap: anywhere;
}
.runtime-heading {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 20px;
}
h2 {
  margin: 0;
  font-size: 20px;
}
p,
dd,
li,
summary {
  line-height: 1.8;
}
.runtime-panel p {
  margin: 8px 0;
}
.runtime-heading button {
  flex-shrink: 0;
}
.runtime-checks {
  margin: 16px 0;
}
.runtime-checks > div {
  padding: 14px 0;
  border-top: 1px solid var(--line);
}
dt {
  font-weight: 600;
}
dd {
  margin: 8px 0 0;
}
.runtime-badge {
  display: inline-block;
  margin-left: 8px;
  font-size: 12px;
  padding: 2px 8px;
  border-radius: 6px;
  background: #edf3ec;
}
.runtime-badge.error,
.runtime-error {
  color: #9c3025;
}
.runtime-badge.warning,
.runtime-badge.pending {
  color: #78500a;
  background: #fff3d6;
}
summary {
  cursor: pointer;
  font-weight: 600;
}
ol {
  padding-left: 22px;
}
code {
  font-size: 0.9em;
  white-space: normal;
}
button[aria-disabled='true'] {
  opacity: 0.7;
  cursor: wait;
}
@media (max-width: 600px) {
  .runtime-panel {
    padding: 18px;
  }
  .runtime-heading {
    align-items: flex-start;
    flex-direction: column;
    gap: 10px;
  }
}
</style>
