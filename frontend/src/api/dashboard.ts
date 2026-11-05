import { http } from './client'
import type { DashboardResponse } from './types'

/** GET /dashboard — 首页聚合：今日任务、待温习、管家消息、计划建议. */
export const dashboardApi = {
  get: () => http.get<DashboardResponse>('/dashboard'),
}
