import { createRouter, createWebHistory } from 'vue-router'
import { getToken, setToken, setUnauthorizedHandler } from '@/api/client'
import { useAuthStore } from '@/stores/auth'
import AppShell from '@/components/AppShell.vue'

const routes = [
  {
    path: '/login',
    name: 'auth',
    component: () => import('@/views/AuthView.vue'),
    meta: { public: true },
  },
  {
    path: '/',
    component: AppShell,
    children: [
      { path: '', name: 'dashboard', component: () => import('@/views/DashboardView.vue') },
      { path: 'goals/new', name: 'goal-new', component: () => import('@/views/GoalNewView.vue') },
      { path: 'goals/:goalId', name: 'goal', component: () => import('@/views/GoalView.vue') },
      {
        path: 'goals/:goalId/sources',
        name: 'sources',
        component: () => import('@/views/SourcesView.vue'),
      },
      {
        path: 'courses/:courseId',
        name: 'course',
        component: () => import('@/views/CourseView.vue'),
      },
      {
        path: 'courses/:courseId/lessons/:lessonId',
        name: 'lesson',
        component: () => import('@/views/LessonView.vue'),
      },
      { path: 'tasks', name: 'tasks', component: () => import('@/views/TasksView.vue') },
      {
        path: 'practice/:kpId',
        name: 'practice',
        component: () => import('@/views/PracticeView.vue'),
      },
      { path: 'profile', name: 'profile', component: () => import('@/views/ProfileView.vue') },
    ],
  },
  { path: '/:pathMatch(.*)*', redirect: '/' },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

// 401 from any API call → drop the session and return to the login screen.
setUnauthorizedHandler(() => {
  setToken(null)
  if (router.currentRoute.value.name !== 'auth') void router.push({ name: 'auth' })
})

router.beforeEach(async (to) => {
  const auth = useAuthStore()
  await auth.init()
  const hasToken = !!getToken()
  if (!to.meta.public && !hasToken) return { name: 'auth' }
  if (to.name === 'auth' && hasToken) return { name: 'dashboard' }
})

export default router
