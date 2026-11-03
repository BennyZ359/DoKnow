<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { api, ApiError } from '../api'
import { draftFromRecord, editPayload, editScope, sameDraft, validEditDraft } from '../editing'
import type { EditDraft, EditTarget, EditableRecord } from '../editing'
import { readSaved, saveValue, storageWarning } from '../persistence'
import { pendingWrites, sendWrite } from '../writes'
import type { PendingWrite } from '../writes'
import Icon from './Icon.vue'

const props = defineProps<{ target: EditTarget }>()
const emit = defineEmits<{
  close: []
  saving: [value: boolean]
  saved: [record: EditableRecord, entry: PendingWrite]
}>()
const dialog = ref<HTMLDialogElement | null>(null)
const titleInput = ref<HTMLInputElement | null>(null)
const draft = ref<EditDraft | null>(null)
const latest = ref<EditableRecord | null>(null)
const loading = ref(false)
const saving = ref(false)
const conflict = ref(false)
const missing = ref(false)
const error = ref('')
const message = ref('')
const scope = editScope(props.target)
const path = `/${props.target.kind}/${props.target.id}`
const isNote = props.target.kind === 'knowledge'
const pending = computed(() => pendingWrites.value.filter((entry) => entry.scope === scope))
const original = computed(() =>
  latest.value && 'original' in latest.value ? latest.value.original : null
)
const hasChanges = computed(
  () =>
    draft.value &&
    latest.value &&
    Object.keys(editPayload(props.target, draft.value, latest.value)).length > 1
)
const minimumTitle = computed(() => (latest.value?.title === draft.value?.title ? 1 : 2))
const minimumContent = computed(() =>
  latest.value && 'content' in latest.value && latest.value.content === draft.value?.content
    ? 1
    : 10
)

watch(
  draft,
  (value) => {
    if (value) saveValue('draft:' + scope, value)
  },
  { deep: true, flush: 'sync' }
)

async function loadLatest() {
  loading.value = true
  error.value = ''
  try {
    latest.value = await api<EditableRecord>(path)
    if (!draft.value) draft.value = draftFromRecord(latest.value)
    if (draft.value.version !== latest.value.version) conflict.value = true
  } catch (reason) {
    error.value = (reason as Error).message
    if (reason instanceof ApiError && reason.status === 404) missing.value = true
  } finally {
    loading.value = false
  }
}

function reconcile(useLatest: boolean) {
  if (!latest.value || !draft.value) return
  if (useLatest) draft.value = draftFromRecord(latest.value)
  else draft.value.version = latest.value.version
  conflict.value = false
  error.value = ''
  message.value = useLatest
    ? '已采用最新内容，可以继续编辑。'
    : '已保留你的修改。再次保存会用上方内容更新这条记录。'
}

async function save(existing?: PendingWrite) {
  if (!draft.value || saving.value || (!existing && (conflict.value || missing.value))) return
  const snapshot = { ...draft.value }
  saving.value = true
  emit('saving', true)
  error.value = ''
  message.value = ''
  try {
    const { result, entry } = await sendWrite<EditableRecord>(
      path,
      existing?.payload || editPayload(props.target, snapshot, latest.value || undefined),
      scope,
      isNote ? `编辑笔记 · ${snapshot.title}` : `编辑目标 · ${snapshot.title}`,
      existing,
      'PATCH',
      snapshot
    )
    emit('saved', result, entry)
    if (sameDraft(draft.value, entry.draft)) emit('close')
    else {
      await loadLatest()
      message.value = '上次保存已确认，后来输入的修改仍然保留。请核对最新内容后继续。'
    }
  } catch (reason) {
    if (reason instanceof ApiError && reason.code === 'edit_conflict') {
      conflict.value = true
      await loadLatest()
      if (!error.value) error.value = reason.message
    } else {
      error.value = (reason as Error).message
      if (reason instanceof ApiError && [404, 410].includes(reason.status)) missing.value = true
    }
  } finally {
    saving.value = false
    emit('saving', false)
  }
}

onMounted(async () => {
  dialog.value?.showModal()
  draft.value = readSaved('draft:' + scope, validEditDraft)
  if (draft.value) message.value = '已恢复此页面的编辑草稿。'
  await loadLatest()
  await nextTick()
  titleInput.value?.focus()
})
</script>

<template>
  <dialog
    ref="dialog"
    class="goal-dialog record-editor"
    aria-labelledby="editor-title"
    @cancel.prevent="!saving && emit('close')"
  >
    <form @submit.prevent="save()">
      <div class="dialog-heading">
        <h2 id="editor-title">{{ isNote ? '编辑知识笔记' : '编辑目标信息' }}</h2>
        <button
          type="button"
          class="icon-button"
          aria-label="关闭编辑"
          :disabled="saving"
          @click="emit('close')"
        >
          <Icon name="close" />
        </button>
      </div>
      <p v-if="isNote" class="edit-impact">
        标题、正文和标签会更新笔记与资料问答。原始记录单独保留，学习历史与评价保持原样。
      </p>
      <p v-else class="edit-impact">
        只修改目标名称、学习动机和每日时间。已有课程、难度、单元顺序、学习进度及历史记录保持原样；每日时间是后续学习的时间参考，不会重排课程或改变复习日期。
      </p>
      <p class="draft-hint">
        编辑草稿保存在此浏览器，关闭后可重新打开继续。保存会检查版本，防止覆盖其他页面的修改。
      </p>
      <div v-if="storageWarning" class="alert" role="status">{{ storageWarning }}</div>
      <div v-if="error" class="alert error" role="alert">{{ error }}</div>
      <div v-if="message" class="alert" role="status">{{ message }}</div>
      <div v-for="entry in pending" v-show="!saving" :key="entry.key" class="pending-operations">
        <p>这次保存结果尚未确认。可以使用原操作确认，避免重复保存。</p>
        <button
          type="button"
          class="button secondary"
          :disabled="saving || loading"
          @click="save(entry)"
        >
          确认上次保存
        </button>
      </div>
      <p v-if="loading" role="status">正在读取最新记录…</p>
      <template v-if="draft">
        <label for="edit-title">{{ isNote ? '笔记标题' : '目标标题' }}</label>
        <input
          id="edit-title"
          ref="titleInput"
          v-model="draft.title"
          :minlength="minimumTitle"
          maxlength="200"
          required
          :disabled="saving"
        />
        <template v-if="isNote">
          <label for="edit-content">笔记正文</label>
          <textarea
            id="edit-content"
            v-model="draft.content"
            rows="9"
            :minlength="minimumContent"
            maxlength="1000000"
            required
            :disabled="saving"
          ></textarea>
          <label for="edit-tags">标签</label>
          <input
            id="edit-tags"
            v-model="draft.tags"
            :disabled="saving"
            aria-describedby="tag-help"
            placeholder="例如：Python, 函数, 待实践"
          />
          <p id="tag-help" class="draft-hint">
            用逗号分隔，最多 20 个标签，每个不超过 40 个字符；清空可移除全部标签。
          </p>
        </template>
        <template v-else>
          <label for="edit-motivation">学习动机（可选）</label>
          <textarea
            id="edit-motivation"
            v-model="draft.motivation"
            rows="3"
            maxlength="4000"
            :disabled="saving"
          ></textarea>
          <label for="edit-minutes">每日学习时间（分钟）</label>
          <input
            id="edit-minutes"
            v-model.number="draft.daily_minutes"
            type="number"
            min="10"
            max="180"
            step="1"
            required
            :disabled="saving"
          />
        </template>
        <section v-if="conflict" class="edit-conflict" aria-label="编辑冲突" role="alert">
          <h3>其他页面已修改这条记录</h3>
          <p>你的输入已保留。先对照最新内容，再选择采用它，或把需要合并的内容补进上方表单。</p>
          <template v-if="latest && latest.version !== draft.version">
            <p>最新版本 {{ latest.version }} · {{ latest.title }}</p>
            <p class="prose">{{ 'content' in latest ? latest.content : latest.motivation }}</p>
            <p v-if="'tags' in latest">标签：{{ latest.tags.join('、') || '无' }}</p>
            <p v-else>每日学习时间：{{ latest.daily_minutes }} 分钟</p>
            <div class="edit-actions">
              <button type="button" class="button secondary" @click="reconcile(true)">
                使用最新内容
              </button>
              <button type="button" class="button secondary" @click="reconcile(false)">
                已核对，保留我的修改
              </button>
            </div>
          </template>
          <button
            v-else
            type="button"
            class="button secondary"
            :disabled="loading"
            @click="loadLatest"
          >
            读取最新内容
          </button>
        </section>
        <details v-if="original" class="original-record">
          <summary>查看原始记录（只读）</summary>
          <strong>{{ original.title }}</strong>
          <p class="prose">{{ original.content }}</p>
        </details>
        <div class="form-footer">
          <button type="button" class="text-button" :disabled="saving" @click="emit('close')">
            关闭，保留草稿
          </button>
          <button
            class="button primary"
            :disabled="saving || loading || conflict || missing || !hasChanges"
          >
            {{ saving ? '保存中…' : '保存修改' }}
          </button>
        </div>
      </template>
      <button
        v-else-if="!loading && !missing"
        type="button"
        class="button secondary"
        @click="loadLatest"
      >
        重新读取
      </button>
    </form>
  </dialog>
</template>
