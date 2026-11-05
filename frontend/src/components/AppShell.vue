<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useGoalStore } from '@/stores/goal'
import { useToastStore } from '@/stores/toast'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const goalStore = useGoalStore()
const toast = useToastStore()

const navItems = computed(() => {
  const items: { label: string; to: string; name: string }[] = [
    { label: '首页', to: '/', name: 'dashboard' },
    { label: '今日任务', to: '/tasks', name: 'tasks' },
  ]
  if (goalStore.activeGoalId) {
    items.push({
      label: '学习目标',
      to: `/goals/${goalStore.activeGoalId}`,
      name: 'goal',
    })
  }
  items.push({ label: '设置', to: '/profile', name: 'profile' })
  return items
})

async function onLogout(): Promise<void> {
  await auth.logout()
  goalStore.reset()
  toast.info('已退出登录')
  router.push({ name: 'auth' })
}
</script>

<template>
  <div class="shell">
    <header class="shell-header">
      <RouterLink class="logo" to="/">
        <span class="logo-dot" />
        DoKnow
      </RouterLink>
      <nav class="shell-nav">
        <RouterLink
          v-for="item in navItems"
          :key="item.name"
          class="shell-link"
          :class="{ active: route.name === item.name }"
          :to="item.to"
        >
          {{ item.label }}
        </RouterLink>
      </nav>
      <div class="shell-user">
        <RouterLink class="btn btn-soft btn-sm" :to="{ name: 'goal-new' }">+ 新目标</RouterLink>
        <span class="shell-user-name">{{ auth.displayName }}</span>
        <button class="btn btn-ghost btn-sm" type="button" @click="onLogout">退出</button>
      </div>
    </header>
    <main class="shell-main" :class="{ 'shell-main--fluid': route.name === 'dashboard' }">
      <RouterView />
    </main>
  </div>
</template>
