<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { api, ApiError } from '../api'
import type { CourseChange, CourseState, CourseUnit, Goal } from '../api'
import { readSaved, removeSaved, saveValue, storageWarning } from '../persistence'
import { acknowledgeWrite, pendingWrites, sendWrite } from '../writes'
import type { PendingWrite } from '../writes'
import Icon from './Icon.vue'

const props = defineProps<{ goalId: string }>()
const emit = defineEmits<{ close: []; saving: [value: boolean]; saved: [goal: Goal] }>()
const dialog = ref<HTMLDialogElement | null>(null)
const closeControl = ref<HTMLButtonElement | null>(null)
const firstControl = ref<HTMLSelectElement | null>(null)
const previewHeading = ref<HTMLHeadingElement | null>(null)
let returnFocus: HTMLElement | null = null
let disposed = false
const data = ref<CourseState | null>(null)
const preview = ref<CourseChange | null>(null)
const kind = ref<CourseChange['kind']>('regenerate')
const level = ref('intermediate')
const order = ref<string[]>([])
const busy = ref(false)
const loading = ref(false)
const conflict = ref(false)
const error = ref('')
const message = ref('')
const checked = ref(false)
const scope = `course:${props.goalId}`
const path = `/goals/${props.goalId}/course`
const previewKey = `course-preview:${props.goalId}`
const pending = computed(() => pendingWrites.value.filter((entry) => entry.scope === scope))
const movable = computed(() => data.value?.units.filter((unit) => !unit.retained) || [])
const ordered = computed(() => {
  let index = 0
  return (
    data.value?.units.map((unit) => {
      if (unit.retained) return unit
      const id = order.value[index++]
      return movable.value.find((item) => item.id === id) || unit
    }) || []
  )
})
const validAction = computed(
  () =>
    data.value &&
    !pending.value.length &&
    (kind.value === 'reorder'
      ? movable.value.length > 1 &&
        order.value.join() !== movable.value.map((unit) => unit.id).join()
      : movable.value.length > 0 &&
        (kind.value !== 'difficulty' || level.value !== data.value.goal.level))
)
const levelName = (value: string) =>
  ({ beginner: '入门', intermediate: '进阶', advanced: '高级' })[value] || value
const kindName = (value: string) =>
  ({ regenerate: '课程重生成', difficulty: '难度调整', reorder: '单元重排' })[value] || value

async function load() {
  loading.value = true
  try {
    data.value = await api<CourseState>(path)
    order.value = data.value.units.filter((unit) => !unit.retained).map((unit) => unit.id)
    level.value = data.value.goal.level === 'beginner' ? 'intermediate' : 'beginner'
  } finally {
    loading.value = false
  }
}

function clearPreview() {
  const id = preview.value?.id
  if (id) removeSaved(previewKey, (value) => value === id)
  preview.value = null
  checked.value = false
}

function showPreview(value: CourseChange) {
  preview.value = value
  saveValue(previewKey, value.id)
  checked.value = false
  conflict.value = !!value.applied_at || value.base_version !== data.value?.goal.course_version
  void nextTick(() => previewHeading.value?.focus())
}

function move(unit: CourseUnit, delta: number) {
  const index = order.value.indexOf(unit.id)
  const other = index + delta
  if (index < 0 || other < 0 || other >= order.value.length) return
  ;[order.value[index], order.value[other]] = [order.value[other]!, order.value[index]!]
  message.value = `已移动「${unit.title}」，已开始单元位置保持不变。`
}

async function refresh() {
  if (busy.value) return
  error.value = ''
  try {
    await load()
    clearPreview()
    conflict.value = false
    message.value = '已读取最新课程，请重新选择并预览。'
    await nextTick()
    firstControl.value?.focus()
  } catch (reason) {
    error.value = (reason as Error).message
  }
}

async function write(action: 'preview' | 'apply', existing?: PendingWrite) {
  if (
    busy.value ||
    (!existing && action === 'apply' && (!preview.value || !checked.value || conflict.value))
  )
    return
  busy.value = true
  emit('saving', true)
  error.value = ''
  message.value = ''
  try {
    const payload =
      existing?.payload ||
      (action === 'apply'
        ? { preview_id: preview.value!.id, confirmed: true }
        : {
            course_version: data.value!.goal.course_version,
            kind: kind.value,
            ...(kind.value === 'difficulty' ? { level: level.value } : {}),
            ...(kind.value === 'reorder' ? { unit_ids: [...order.value] } : {}),
          })
    const { result, entry } = await sendWrite<CourseChange | Goal>(
      `${path}/${action}`,
      payload,
      scope,
      action === 'preview' ? '生成课程预览' : '确认课程调整',
      existing
    )
    acknowledgeWrite(entry)
    if (action === 'preview') {
      showPreview(result as CourseChange)
      message.value = '预览已生成，课程尚未改变。请核对下方内容。'
    } else {
      clearPreview()
      emit('saved', result as Goal)
      message.value = '课程调整已保存，学习证据已保留。'
      busy.value = false
      emit('saving', false)
      await nextTick()
      closeControl.value?.focus()
      try {
        await load()
      } catch {
        error.value = '调整已保存，最新课程暂未同步。请稍后读取最新课程。'
      }
    }
  } catch (reason) {
    error.value = (reason as Error).message
    if (reason instanceof ApiError && reason.code === 'course_conflict') {
      conflict.value = true
      checked.value = false
    }
  } finally {
    busy.value = false
    if (!disposed) emit('saving', false)
  }
}

onMounted(async () => {
  returnFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null
  dialog.value?.showModal()
  try {
    await load()
    const id = readSaved(
      previewKey,
      (value): value is string => typeof value === 'string' && /^[a-zA-Z0-9-]{36}$/.test(value)
    )
    if (id) showPreview(await api<CourseChange>(`${path}/previews/${id}`))
    else {
      await nextTick()
      firstControl.value?.focus()
    }
  } catch (reason) {
    error.value = (reason as Error).message
  }
})

onBeforeUnmount(() => {
  disposed = true
  dialog.value?.close()
  if (returnFocus?.isConnected) returnFocus.focus()
})
</script>

<template>
  <dialog
    ref="dialog"
    class="goal-dialog course-editor"
    aria-labelledby="course-title"
    @cancel.prevent="!busy && emit('close')"
  >
    <div class="dialog-heading">
      <h2 id="course-title">调整学习课程</h2>
      <button
        class="icon-button"
        type="button"
        aria-label="关闭课程调整"
        ref="closeControl"
        :disabled="busy"
        @click="emit('close')"
      >
        <Icon name="close" />
      </button>
    </div>
    <p class="edit-impact">
      已保存聊天、学习提交或复习记录的单元会固定保留。只调整未开始部分；评价、笔记与复习安排保持原样。
    </p>
    <p class="draft-hint">
      只浏览过或仅有本地草稿的单元仍算未开始。替换后旧材料与草稿保留在旧单元，不会自动转入新课程。
    </p>
    <p v-if="storageWarning" class="alert" role="status">{{ storageWarning }}</p>
    <p v-if="error" class="alert error" role="alert">{{ error }}</p>
    <p v-if="message" class="alert" role="status">{{ message }}</p>
    <p v-if="loading" role="status">正在读取课程…</p>
    <div v-for="entry in pending" :key="entry.key" class="pending-operations">
      <p>{{ entry.label }}的结果尚未确认。使用原操作恢复，不会重复生成或调整。</p>
      <button
        class="button secondary"
        :disabled="busy || loading"
        @click="write(entry.path.endsWith('/apply') ? 'apply' : 'preview', entry)"
      >
        恢复{{ entry.label }}
      </button>
    </div>
    <button class="text-button" :disabled="busy || loading" @click="refresh">读取最新课程</button>
    <template v-if="data">
      <p>
        {{ data.goal.title }} · 课程版本 {{ data.goal.course_version }} · 后续难度：{{
          levelName(data.goal.level)
        }}
      </p>
      <form v-if="!preview" @submit.prevent="write('preview')">
        <label for="course-kind">调整方式</label>
        <select
          id="course-kind"
          ref="firstControl"
          v-model="kind"
          :disabled="busy || loading || !!pending.length"
        >
          <option value="regenerate">重新生成未开始课程</option>
          <option value="difficulty">调整后续难度</option>
          <option value="reorder">重排未开始单元</option>
        </select>
        <template v-if="kind === 'difficulty'">
          <label for="course-level">后续课程难度</label>
          <select id="course-level" v-model="level" :disabled="busy || loading || !!pending.length">
            <option value="beginner">入门</option>
            <option value="intermediate">进阶</option>
            <option value="advanced">高级</option>
          </select>
        </template>
        <ol class="course-units" aria-label="当前课程顺序">
          <li v-for="(item, index) in ordered" :key="item.id">
            <div>
              <strong>{{ index + 1 }}. {{ item.title }}</strong
              ><small>{{ item.retained ? '已开始 · 固定保留' : '未开始 · 可调整' }}</small>
              <p>{{ item.objective }}</p>
            </div>
            <div v-if="kind === 'reorder' && !item.retained" class="course-move">
              <button
                type="button"
                class="button secondary"
                :aria-label="`上移 ${item.title}`"
                :disabled="busy || !!pending.length || order.indexOf(item.id) === 0"
                @click="move(item, -1)"
              >
                上移
              </button>
              <button
                type="button"
                class="button secondary"
                :aria-label="`下移 ${item.title}`"
                :disabled="busy || !!pending.length || order.indexOf(item.id) === order.length - 1"
                @click="move(item, 1)"
              >
                下移
              </button>
            </div>
          </li>
        </ol>
        <p v-if="!movable.length" role="status">所有单元都已有学习记录，没有可调整的未开始单元。</p>
        <p v-else-if="kind === 'reorder' && movable.length < 2">至少需要两个未开始单元才能重排。</p>
        <button class="button primary" :disabled="busy || loading || !validAction">
          {{ busy ? '正在生成预览…' : '预览课程调整' }}
        </button>
      </form>
      <section v-else class="course-preview" aria-label="课程变更预览">
        <h3 ref="previewHeading" tabindex="-1">
          {{ kindName(preview.kind) }}：版本 {{ preview.base_version }} →
          {{ preview.course_version }}
        </h3>
        <p>
          后续难度：{{ levelName(preview.before.level) }} → {{ levelName(preview.after.level) }}
        </p>
        <div class="course-comparison">
          <section>
            <h4>调整前</h4>
            <ol>
              <li v-for="item in preview.before.units" :key="item.id">
                {{ item.title }}<small>{{ item.retained ? '固定保留' : '未开始' }}</small>
              </li>
            </ol>
          </section>
          <section>
            <h4>确认后</h4>
            <ol>
              <li v-for="item in preview.after.units" :key="item.id">
                {{ item.title
                }}<small>{{
                  item.retained
                    ? '固定保留'
                    : item.replaces
                      ? '新材料 · 旧单元归档'
                      : '保留材料 · 调整顺序'
                }}</small>
                <p>{{ item.objective }}</p>
                <details v-if="item.lesson">
                  <summary>查看新课程材料</summary>
                  <p>{{ item.lesson.explanation }}</p>
                  <pre>{{ item.lesson.example }}</pre>
                  <p>{{ item.lesson.question }}</p>
                  <h5>{{ item.project?.title }}</h5>
                  <p>{{ item.project?.brief }}</p>
                  <ul>
                    <li v-for="criterion in item.project?.criteria" :key="criterion">
                      {{ criterion }}
                    </li>
                  </ul>
                  <p>{{ item.teach?.prompt }}</p>
                </details>
              </li>
            </ol>
          </section>
        </div>
        <p v-if="conflict" role="alert">此预览已过期或已确认，请读取最新课程后重新预览。</p>
        <label class="course-confirm"
          ><input
            v-model="checked"
            type="checkbox"
            :disabled="busy || conflict || !!pending.length"
          />我已核对调整范围和新材料，确认保留已有学习证据。</label
        >
        <div class="course-actions">
          <button
            class="button secondary"
            :disabled="busy || !!pending.length"
            @click="clearPreview"
          >
            返回修改
          </button>
          <button
            class="button primary"
            :disabled="busy || !checked || conflict || !!pending.length"
            @click="write('apply')"
          >
            {{ busy ? '正在保存…' : '确认课程调整' }}
          </button>
        </div>
      </section>
      <section class="course-history" aria-label="课程变更记录">
        <h3>课程变更记录</h3>
        <p v-if="!data.history.length">还没有已确认的课程调整。</p>
        <details v-for="change in data.history" :key="change.id">
          <summary>
            版本 {{ change.base_version }} → {{ change.course_version }} ·
            {{ kindName(change.kind) }}
          </summary>
          <p>
            {{ new Date(change.applied_at!).toLocaleString('zh-CN') }} ·
            {{ levelName(change.before.level) }} → {{ levelName(change.after.level) }}
          </p>
          <h4>当时课程</h4>
          <ol>
            <li v-for="item in change.before.units" :key="item.id">
              <a :href="`#/learn/${item.id}`" @click="emit('close')"
                >{{ item.title }}（查看保留材料）</a
              >
            </li>
          </ol>
          <h4>调整结果</h4>
          <ol>
            <li v-for="item in change.after.units" :key="item.id">
              <a :href="`#/learn/${item.id}`" @click="emit('close')">{{ item.title }}</a
              ><small>{{ item.retained ? '固定保留' : item.replaces ? '替换材料' : '重排' }}</small>
            </li>
          </ol>
        </details>
      </section>
    </template>
  </dialog>
</template>

<style scoped>
.course-editor {
  width: min(900px, calc(100vw - 32px));
  max-width: 900px;
  overflow-wrap: anywhere;
}
.course-units {
  list-style: none;
  padding: 0;
}
.course-units > li {
  display: flex;
  gap: 12px;
  justify-content: space-between;
  padding: 14px 0;
  border-bottom: 1px solid #dce2d7;
}
.course-units > li > div {
  min-width: 0;
}
small {
  display: block;
  color: #566d56;
  margin: 4px 0;
}
.course-move,
.course-actions {
  display: flex;
  gap: 8px;
  align-items: center;
}
.course-comparison {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 24px;
}
.course-comparison > section {
  min-width: 0;
}
.course-comparison li {
  margin-bottom: 16px;
}
.course-comparison pre {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
.course-confirm {
  display: flex;
  gap: 10px;
  align-items: flex-start;
  margin: 20px 0;
}
.course-confirm input {
  width: 20px;
  min-width: 20px;
  margin: 4px 0 0;
}
.course-history {
  border-top: 1px solid #dce2d7;
  margin-top: 24px;
  padding-top: 16px;
}
.course-history details {
  margin: 16px 0;
}
summary {
  cursor: pointer;
}
@media (max-width: 620px) {
  .course-comparison {
    grid-template-columns: 1fr;
    gap: 8px;
  }
  .course-units > li {
    flex-direction: column;
  }
  .course-actions {
    flex-wrap: wrap;
  }
  .course-actions .button {
    flex: 1;
  }
}
</style>
