<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { api } from '../api'
import type { FullNote, Note } from '../api'
import Icon from './Icon.vue'

const props = defineProps<{ notes: Note[]; busy: boolean; selected: string | null }>()
const emit = defineEmits<{
  'update:selected': [value: string | null]
  edit: [note: Note]
  delete: [note: Note]
}>()
const search = ref('')
const tag = ref('')
const source = ref('')
const originals = ref<Record<string, FullNote['original']>>({})
const openOriginal = ref<string | null>(null)
const loadingOriginal = ref('')
const error = ref('')
const sourceKind = (note: Note) =>
  ['note', 'reflection'].includes(note.source) ? note.source : 'import'
const sourceLabel = (note: Note) =>
  ({ note: '我的笔记', reflection: '实践沉淀', import: '学习资料' })[sourceKind(note)]
const date = (value: string) =>
  new Intl.DateTimeFormat('zh-CN', { month: 'numeric', day: 'numeric' }).format(new Date(value))
const tags = computed(() => {
  const values = new Map<string, string>()
  for (const note of props.notes)
    for (const value of note.tags) {
      if (!values.has(value.toLowerCase())) values.set(value.toLowerCase(), value)
    }
  return [...values.values()].sort((a, b) => a.localeCompare(b, 'zh-CN'))
})
const filtered = computed(() =>
  props.notes.filter(
    (note) =>
      `${note.title} ${note.content} ${note.tags.join(' ')}`
        .toLowerCase()
        .includes(search.value.trim().toLowerCase()) &&
      (!tag.value || note.tags.some((value) => value.toLowerCase() === tag.value.toLowerCase())) &&
      (!source.value || sourceKind(note) === source.value)
  )
)
const exportUrl = computed(
  () =>
    '/api/knowledge/export?' +
    new URLSearchParams({ q: search.value, tag: tag.value, source: source.value }).toString()
)

function resetFilters() {
  search.value = ''
  tag.value = ''
  source.value = ''
}
function toggle(note: Note) {
  emit('update:selected', props.selected === note.id ? null : note.id)
}
async function showOriginal(note: Note) {
  if (openOriginal.value === note.id) {
    openOriginal.value = null
    return
  }
  error.value = ''
  loadingOriginal.value = note.id
  try {
    const detail = await api<FullNote>(`/knowledge/${note.id}`)
    originals.value[note.id] = detail.original
    openOriginal.value = note.id
  } catch (reason) {
    error.value = (reason as Error).message
  } finally {
    loadingOriginal.value = ''
  }
}
watch(
  () => props.selected,
  (id) => {
    if (id && !filtered.value.some((note) => note.id === id)) resetFilters()
  }
)
</script>

<template>
  <section aria-label="知识笔记管理">
    <div class="section-heading knowledge-list-heading">
      <h2>
        我的知识沉淀 <span>{{ notes.length.toString().padStart(2, '0') }}</span>
      </h2>
      <label class="search-field"
        ><Icon name="search" :size="17" /><input
          v-model="search"
          maxlength="4000"
          aria-label="搜索知识笔记"
          placeholder="搜索标题、正文与标签"
      /></label>
    </div>
    <div class="knowledge-filters">
      <label
        >标签筛选<select v-model="tag">
          <option value="">全部标签</option>
          <option v-for="value in tags" :key="value" :value="value">{{ value }}</option>
        </select></label
      >
      <label
        >来源筛选<select v-model="source">
          <option value="">全部来源</option>
          <option value="note">我的笔记</option>
          <option value="reflection">实践沉淀</option>
          <option value="import">学习资料</option>
        </select></label
      >
      <span class="muted" aria-live="polite">{{ filtered.length }} / {{ notes.length }} 篇</span>
      <a class="button secondary" :href="exportUrl" download>导出筛选结果 Markdown</a>
    </div>
    <p class="import-hint">
      支持 Markdown、TXT、可提取文字的 PDF 与 Word（.docx），单个文件不超过 10
      MB。复盘笔记会自动加入；导出包含正文与保留的原始记录。
    </p>
    <div v-if="error" class="alert error" role="alert">{{ error }}</div>
    <div v-if="!filtered.length" class="empty-state large-empty">
      <Icon name="notes" :size="40" />
      <h2>{{ notes.length ? '还没有找到相关笔记' : '让你的第一个发现，在这里生根' }}</h2>
      <p>
        {{
          notes.length
            ? '试试其他关键词或筛选条件。'
            : '导入一份资料，或完成一次学习复盘。每篇笔记都是下次行动的起点。'
        }}
      </p>
      <button v-if="notes.length" class="button secondary" @click="resetFilters">
        查看全部笔记
      </button>
    </div>
    <div v-else class="notes-grid">
      <article
        v-for="note in filtered"
        :key="note.id"
        :class="['note-card', { expanded: selected === note.id }]"
      >
        <div class="note-card-meta">
          <span class="pill">{{ sourceLabel(note) }}</span
          ><time :datetime="note.updated_at"
            >{{ date(note.updated_at) }}{{ note.version > 1 ? ' 更新' : '' }}</time
          >
          <button
            class="icon-button muted"
            :aria-label="`删除笔记 ${note.title}`"
            :disabled="busy"
            @click="emit('delete', note)"
          >
            <Icon name="trash" :size="16" />
          </button>
        </div>
        <button class="note-title" :aria-expanded="selected === note.id" @click="toggle(note)">
          <h3>{{ note.title }}</h3>
        </button>
        <div v-if="note.tags.length" class="note-tags" aria-label="笔记标签">
          <button v-for="value in note.tags" :key="value" class="pill" @click="tag = value">
            {{ value }}
          </button>
        </div>
        <p class="prose note-content">
          {{
            selected === note.id
              ? note.content
              : note.content.slice(0, 180) + (note.content.length > 180 ? '…' : '')
          }}
        </p>
        <div class="note-actions">
          <button class="text-button" @click="toggle(note)">
            {{ selected === note.id ? '收起笔记' : '回看完整笔记' }}
          </button>
          <button
            class="text-button"
            :aria-label="`编辑笔记 ${note.title}`"
            :disabled="busy"
            @click="emit('edit', note)"
          >
            编辑
          </button>
          <a
            class="text-button"
            :href="`/api/knowledge/${note.id}/export`"
            download
            :aria-label="`导出笔记 ${note.title}`"
            >导出 Markdown</a
          >
          <button
            class="text-button"
            :aria-expanded="openOriginal === note.id"
            :disabled="!!loadingOriginal"
            @click="showOriginal(note)"
          >
            {{ openOriginal === note.id ? '收起原始记录' : '查看原始记录' }}
          </button>
        </div>
        <div
          v-if="openOriginal === note.id && originals[note.id]"
          class="original-record"
          aria-label="原始记录"
        >
          <p class="draft-hint">首次编辑前保留的记录，只读。后续整理不会改写这份内容。</p>
          <strong>{{ originals[note.id].title }}</strong>
          <p class="prose">{{ originals[note.id].content }}</p>
        </div>
      </article>
    </div>
  </section>
</template>
