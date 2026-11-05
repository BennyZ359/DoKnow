import { http } from './client'
import type { Review, ReviewCompleteResponse, Task } from './types'

export interface TaskListResponse {
  tasks: Task[]
}

export interface GenerateTasksResponse {
  created: number
  tasks: Task[]
}

export interface ReviewListResponse {
  reviews: Review[]
}

export interface TaskListQuery extends Record<string, string | number | boolean | undefined> {
  goal_id?: string
  day?: string // ISO date, default today
  status?: string
}

export interface ReviewListQuery extends Record<string, string | number | boolean | undefined> {
  status?: string
  knowledge_point_id?: string
}

/** /tasks + /reviews — 每日任务（学练讲）与温习. */
export const tasksApi = {
  list: (query: TaskListQuery = {}) => http.get<TaskListResponse>('/tasks', query),
  generate: (goalId: string) =>
    http.post<GenerateTasksResponse>('/tasks/generate', undefined, { goal_id: goalId }),
  start: (taskId: string) => http.post<Task>(`/tasks/${taskId}/start`),
  complete: (taskId: string) => http.post<Task>(`/tasks/${taskId}/complete`),
  skip: (taskId: string) => http.post<Task>(`/tasks/${taskId}/skip`),
  createExplain: (goalId: string, knowledgePointId: string) =>
    http.post<Task>('/tasks/explain', undefined, {
      goal_id: goalId,
      knowledge_point_id: knowledgePointId,
    }),

  listReviews: (query: ReviewListQuery = {}) => http.get<ReviewListResponse>('/reviews', query),
  completeReview: (reviewId: string, score: number) =>
    http.post<ReviewCompleteResponse>(`/reviews/${reviewId}/complete`, { score }),
  skipReview: (reviewId: string) => http.post<{ ok: boolean }>(`/reviews/${reviewId}/skip`),
}
