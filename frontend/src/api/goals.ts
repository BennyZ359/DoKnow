import { http } from './client'
import type {
  Goal,
  GoalActivateResponse,
  GoalCreate,
  GoalCreateResponse,
  KnowledgePoint,
  LearningPath,
  OverviewResponse,
  PlanAdjustConfirmResponse,
  PlanProposal,
} from './types'

export interface GoalListResponse {
  goals: Goal[]
}

export interface GoalKnowledgeResponse {
  points: KnowledgePoint[]
}

export interface GoalPathResponse {
  path: LearningPath | null
}

export interface PlanAdjustmentResponse {
  proposal: PlanProposal | null
}

/** /goals — 目标 CRUD + 知识系统总览 + 计划调整 human-in-the-loop. */
export const goalsApi = {
  list: () => http.get<GoalListResponse>('/goals'),
  create: (body: GoalCreate) => http.post<GoalCreateResponse>('/goals', body),
  get: (goalId: string) => http.get<Goal>(`/goals/${goalId}`),
  update: (goalId: string, body: Partial<GoalCreate> & { status?: string }) =>
    http.patch<Goal>(`/goals/${goalId}`, body),
  activate: (goalId: string) => http.post<GoalActivateResponse>(`/goals/${goalId}/activate`),

  overview: (goalId: string) => http.get<OverviewResponse>(`/goals/${goalId}/overview`),
  knowledge: (goalId: string) => http.get<GoalKnowledgeResponse>(`/goals/${goalId}/knowledge`),
  path: (goalId: string) => http.get<GoalPathResponse>(`/goals/${goalId}/path`),

  getPlanAdjustment: (goalId: string) =>
    http.get<PlanAdjustmentResponse>(`/goals/${goalId}/plan-adjustment`),
  confirmPlanAdjustment: (goalId: string, accept: boolean) =>
    http.post<PlanAdjustConfirmResponse>(`/goals/${goalId}/plan-adjustment/confirm`, { accept }),
  triggerManagerCycle: (goalId: string) =>
    http.post<{ ok: boolean; queued: boolean }>(`/goals/${goalId}/manager/cycle`, undefined),
}
