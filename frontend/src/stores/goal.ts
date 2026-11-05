import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { dashboardApi } from '@/api/dashboard'
import { goalsApi } from '@/api/goals'
import type { DashboardResponse, Goal } from '@/api/types'

/**
 * Shared goal state: the dashboard aggregate (active goal, today's tasks,
 * due reviews, manager feed) plus the full goal list. Views read from here
 * so navigation between 首页/任务/目标 keeps context without refetching.
 */
export const useGoalStore = defineStore('goal', () => {
  const dashboard = ref<DashboardResponse | null>(null)
  const goals = ref<Goal[]>([])
  const loadingDashboard = ref(false)

  const activeGoal = computed<Goal | null>(() => dashboard.value?.goal ?? null)
  const activeGoalId = computed<string | null>(() => activeGoal.value?.id ?? null)

  async function loadDashboard(): Promise<DashboardResponse> {
    loadingDashboard.value = true
    try {
      dashboard.value = await dashboardApi.get()
      return dashboard.value
    } finally {
      loadingDashboard.value = false
    }
  }

  async function loadGoals(): Promise<Goal[]> {
    goals.value = (await goalsApi.list()).goals
    return goals.value
  }

  /** Ensure a dashboard is present (e.g. arriving at /tasks directly). */
  async function ensureDashboard(): Promise<void> {
    if (!dashboard.value) await loadDashboard()
  }

  function reset(): void {
    dashboard.value = null
    goals.value = []
  }

  return {
    dashboard,
    goals,
    loadingDashboard,
    activeGoal,
    activeGoalId,
    loadDashboard,
    loadGoals,
    ensureDashboard,
    reset,
  }
})
