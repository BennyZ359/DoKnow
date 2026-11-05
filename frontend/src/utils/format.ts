import type {
  Difficulty,
  GoalStatus,
  MasteryState,
  ReviewStatus,
  SourceStatus,
  TaskStatus,
  TaskType,
} from '@/api/types'

// ---------- dates / numbers ----------

export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '—'
  return `${d.getFullYear()} 年 ${d.getMonth() + 1} 月 ${d.getDate()} 日`
}

export function fmtDateTime(iso: string | null | undefined): string {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '—'
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getMonth() + 1}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

export function fmtRelative(iso: string | null | undefined): string {
  if (!iso) return ''
  const t = new Date(iso).getTime()
  if (Number.isNaN(t)) return ''
  const diff = Date.now() - t
  if (diff < 60_000) return '刚刚'
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)} 分钟前`
  if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)} 小时前`
  if (diff < 7 * 86_400_000) return `${Math.floor(diff / 86_400_000)} 天前`
  return fmtDateTime(iso)
}

export function fmtMinutes(minutes: number | null | undefined): string {
  if (minutes == null) return ''
  if (minutes < 60) return `${minutes} 分钟`
  const h = Math.floor(minutes / 60)
  const m = minutes % 60
  return m ? `${h} 小时 ${m} 分` : `${h} 小时`
}

export function fmtPercent(v: number | null | undefined): string {
  if (v == null) return '0%'
  return `${Math.round(v * 100)}%`
}

export function fmtBytes(bytes: number | null | undefined): string {
  if (bytes == null) return ''
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(1)} KB`
  if (bytes < 1024 ** 3) return `${(bytes / 1024 ** 2).toFixed(1)} MB`
  return `${(bytes / 1024 ** 3).toFixed(2)} GB`
}

// ---------- domain labels ----------

const TASK_TYPE_LABEL: Record<TaskType, string> = {
  STUDY: '学',
  PRACTICE: '练',
  EXPLAIN: '讲',
}

const TASK_TYPE_HINT: Record<TaskType, string> = {
  STUDY: '学习课程内容',
  PRACTICE: '做练习巩固',
  EXPLAIN: '用自己的话讲出来',
}

const TASK_STATUS_LABEL: Record<TaskStatus, string> = {
  NOT_STARTED: '未开始',
  IN_PROGRESS: '进行中',
  COMPLETED: '已完成',
  SKIPPED: '已跳过',
  EXPIRED: '已过期',
}

const REVIEW_STATUS_LABEL: Record<ReviewStatus, string> = {
  PENDING: '未到期',
  DUE: '待温习',
  COMPLETED: '已完成',
  SKIPPED: '已跳过',
}

const MASTERY_LABEL: Record<MasteryState, string> = {
  NOT_STARTED: '未开始',
  IN_PROGRESS: '学习中',
  COMPLETED: '已学完',
  REVIEW_REQUIRED: '待巩固',
  MASTERED: '已掌握',
}

const DIFFICULTY_LABEL: Record<Difficulty, string> = {
  BEGINNER: '入门',
  INTERMEDIATE: '进阶',
  ADVANCED: '高阶',
}

const GOAL_STATUS_LABEL: Record<GoalStatus, string> = {
  DRAFT: '草稿',
  ACTIVE: '进行中',
  PAUSED: '已暂停',
  COMPLETED: '已完成',
  ARCHIVED: '已归档',
}

const SOURCE_STATUS_LABEL: Record<SourceStatus, string> = {
  UPLOADED: '已上传',
  PARSING: '解析中',
  PARSED: '已解析',
  FAILED: '解析失败',
}

export const taskTypeLabel = (t: TaskType | null | undefined): string =>
  t ? TASK_TYPE_LABEL[t] : '任务'
export const taskTypeHint = (t: TaskType | null | undefined): string =>
  t ? TASK_TYPE_HINT[t] : ''
export const taskStatusLabel = (s: TaskStatus | null | undefined): string =>
  s ? TASK_STATUS_LABEL[s] : ''
export const reviewStatusLabel = (s: ReviewStatus | null | undefined): string =>
  s ? REVIEW_STATUS_LABEL[s] : ''
export const masteryLabel = (s: MasteryState | null | undefined): string =>
  s ? MASTERY_LABEL[s] : '未开始'
export const difficultyLabel = (d: Difficulty | null | undefined): string =>
  d ? DIFFICULTY_LABEL[d] : ''
export const goalStatusLabel = (s: GoalStatus | null | undefined): string =>
  s ? GOAL_STATUS_LABEL[s] : ''
export const sourceStatusLabel = (s: SourceStatus | null | undefined): string =>
  s ? SOURCE_STATUS_LABEL[s] : ''

/** Badge color class per mastery state. */
export function masteryClass(s: MasteryState | null | undefined): string {
  switch (s) {
    case 'MASTERED':
      return 'is-success'
    case 'REVIEW_REQUIRED':
      return 'is-warning'
    case 'IN_PROGRESS':
      return 'is-info'
    case 'COMPLETED':
      return 'is-info'
    default:
      return 'is-muted'
  }
}

/** Badge class per task/review status. */
export function statusClass(status: string | null | undefined): string {
  switch (status) {
    case 'COMPLETED':
    case 'PUBLISHED':
    case 'ACTIVE':
    case 'PARSED':
      return 'is-success'
    case 'IN_PROGRESS':
    case 'DUE':
    case 'PARSING':
      return 'is-warning'
    case 'SKIPPED':
    case 'PAUSED':
    case 'PENDING':
      return 'is-muted'
    case 'EXPIRED':
    case 'FAILED':
      return 'is-danger'
    default:
      return 'is-info'
  }
}
