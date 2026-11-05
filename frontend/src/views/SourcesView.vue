<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { sourcesApi } from '@/api/sources'
import type { ParseBackend } from '@/api/sources'
import type { Source } from '@/api/types'
import EmptyState from '@/components/EmptyState.vue'
import Spinner from '@/components/Spinner.vue'
import { useToastStore } from '@/stores/toast'
import { fmtBytes, fmtDateTime, statusClass, sourceStatusLabel } from '@/utils/format'

const route = useRoute()
const toast = useToastStore()

const goalId = computed(() => route.params.goalId as string)

const loading = ref(true)
const sources = ref<Source[]>([])
const uploading = ref(false)
const fileInput = ref<HTMLInputElement | null>(null)
const backend = ref<'' | ParseBackend>('')

const hasPending = computed(() =>
  sources.value.some((s) => s.status === 'PARSING' || s.status === 'UPLOADED'),
)

let pollTimer: ReturnType<typeof setInterval> | undefined

async function load(silent = false): Promise<void> {
  if (!silent) loading.value = true
  try {
    sources.value = (await sourcesApi.list(goalId.value)).sources
  } catch (e) {
    toast.error(e instanceof Error ? e.message : '加载失败')
  } finally {
    loading.value = false
  }
}

function schedulePoll(): void {
  if (pollTimer) return
  pollTimer = setInterval(() => {
    if (!hasPending.value) {
      stopPoll()
      void load(true)
      return
    }
    void load(true)
  }, 4000)
}

function stopPoll(): void {
  if (pollTimer) clearInterval(pollTimer)
  pollTimer = undefined
}

function pickFile(): void {
  fileInput.value?.click()
}

async function onFileChange(e: Event): Promise<void> {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  uploading.value = true
  try {
    await sourcesApi.upload(goalId.value, file, backend.value || undefined)
    toast.success('已上传，Docling/MinerU 解析完成后可被 AI 引用')
    input.value = ''
    await load(true)
    schedulePoll()
  } catch (err) {
    toast.error(err instanceof Error ? err.message : '上传失败')
  } finally {
    uploading.value = false
  }
}

onMounted(() => {
  void load().then(schedulePoll)
})
onUnmounted(stopPoll)
</script>

<template>
  <div>
    <div class="page-header">
      <div>
        <p class="page-sub" style="margin: 0 0 4px">
          <RouterLink :to="{ name: 'goal', params: { goalId: goalId } }">返回目标</RouterLink>
        </p>
        <h1 class="page-title">参考资料</h1>
        <p class="page-sub">上传 PDF / Word / PPT / Markdown，AI 解析后用于定制你的知识体系与课程</p>
      </div>
    </div>

    <div class="card">
      <div class="row wrap between">
        <div class="row wrap">
          <input
            ref="fileInput"
            type="file"
            class="file-hidden"
            accept=".pdf,.docx,.pptx,.md,.markdown,.html,.htm"
            @change="onFileChange"
          />
          <button class="btn btn-primary" type="button" :disabled="uploading" @click="pickFile">
            {{ uploading ? '上传解析中…' : '＋ 上传文件' }}
          </button>
          <select v-model="backend" class="select" style="width: 160px">
            <option value="">解析引擎 · 自动</option>
            <option value="docling">Docling</option>
            <option value="mineru">MinerU</option>
          </select>
        </div>
        <span class="muted small">支持 PDF、DOCX、PPTX、Markdown、HTML</span>
      </div>
    </div>

    <div class="section">
      <div v-if="loading" class="card"><Spinner /></div>

      <template v-else>
        <div v-if="sources.length" class="row-list">
          <div v-for="s in sources" :key="s.id" class="row-item" style="align-items: flex-start">
            <span class="type-chip STUDY">📄</span>
            <div class="row-main">
              <div class="row-title">{{ s.filename }}</div>
              <div class="row-desc">
                <span class="badge" :class="statusClass(s.status)">{{ sourceStatusLabel(s.status) }}</span>
                <template v-if="s.parser_backend"> · {{ s.parser_backend }}</template>
                <template v-if="s.size_bytes"> · {{ fmtBytes(s.size_bytes) }}</template>
                <template v-if="s.created_at"> · {{ fmtDateTime(s.created_at) }}</template>
              </div>
              <p v-if="s.error" class="small mt-4" style="color: var(--danger)">{{ s.error.message }}</p>
              <p v-else-if="s.excerpt" class="muted small mt-4">{{ s.excerpt.slice(0, 160) }}…</p>
            </div>
          </div>
        </div>
        <div v-else class="card">
          <EmptyState
            icon="🗄️"
            title="还没有上传资料"
            hint="把你在学的文档丢进来，AI 建体系、出题、写课程时都会参考它们"
          />
        </div>
      </template>
    </div>
  </div>
</template>

<style scoped>
.file-hidden {
  display: none;
}
</style>
