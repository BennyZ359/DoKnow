export type Stage = 'learn' | 'practice' | 'project' | 'teach' | 'reflect' | 'review' | 'complete'
export interface Session {
  id: string
  unit_id: string
  kind: string
  content: string
  feedback: string
  score: number | null
  created_at: string
}
export interface Unit {
  id: string
  title: string
  objective: string
  position: number
  stage: Stage
  mastery: number
  review_due_at: string | null
  review_count: number
  completed_at: string | null
  goal_id?: string
  goal_title?: string
}
export interface FullUnit extends Unit {
  goal_id: string
  goal_title: string
  lesson: { explanation: string; example: string; question: string }
  practice: { question: string; options: string[]; explanation?: string }
  project: { title: string; brief: string; criteria: string[] }
  teach: { prompt: string; checklist: string[] }
  sessions: Session[]
}
export interface Goal {
  id: string
  title: string
  motivation: string
  level: string
  daily_minutes: number
  created_at: string
  units: Unit[]
  progress: number
}
export interface Dashboard {
  goals: Goal[]
  reviews_due: number
  total_sessions: number
  knowledge_count: number
  recent_activity: Session[]
}
export interface Note {
  id: string
  title: string
  content: string
  source: string
  created_at: string
}
export interface Settings {
  mode: string
  provider: string
  model: string
  configured: boolean
  principles: { name: string; practice: string }[]
  limitations: string[]
}
export interface Submission {
  unit: Unit
  feedback: string
  score?: number
  passed?: boolean
}
export interface KnowledgeAnswer {
  answer: string
  sources: { id: string; title: string; excerpt: string }[]
  mode: string
}

export class ApiError extends Error {
  constructor(
    message: string,
    public status = 0,
    public code = ''
  ) {
    super(message)
  }
}

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const controller = new AbortController()
  const timeout = window.setTimeout(() => controller.abort(), 90_000)
  try {
    const response = await fetch(`/api${path}`, {
      ...options,
      signal: options.signal || controller.signal,
      headers: {
        ...(options.body && !(options.body instanceof FormData)
          ? { 'Content-Type': 'application/json' }
          : {}),
        ...options.headers,
      },
    })
    if (!response.ok) {
      const data = await response.json().catch(() => null)
      if (controller.signal.aborted)
        throw new ApiError('等待服务响应已超时，请确认上次操作后重试。')
      const detail = data?.detail
      const message =
        typeof detail === 'string'
          ? detail
          : Array.isArray(detail)
            ? detail.map((entry: { msg?: string }) => entry.msg || '请检查输入内容').join('；')
            : '操作没有完成，请稍后重试。'
      throw new ApiError(message, response.status, typeof data?.code === 'string' ? data.code : '')
    }
    if (response.status === 204) return undefined as T
    return (await response.json()) as T
  } catch (error) {
    if (error instanceof ApiError) throw error
    throw new ApiError('连接中断、等待超时或服务响应不完整。请检查连接后重试。')
  } finally {
    window.clearTimeout(timeout)
  }
}

export const post = <T>(path: string, body: unknown) =>
  api<T>(path, { method: 'POST', body: JSON.stringify(body) })
