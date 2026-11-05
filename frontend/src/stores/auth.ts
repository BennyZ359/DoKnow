import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { authApi } from '@/api/auth'
import { getToken, setToken } from '@/api/client'
import type { LoginRequest, RegisterRequest, User, UserProfile } from '@/api/types'

/** Session state: opaque token in localStorage, user/profile from /auth/me. */
export const useAuthStore = defineStore('auth', () => {
  const user = ref<User | null>(null)
  const profile = ref<UserProfile | null>(null)
  const ready = ref(false)

  const isAuthenticated = computed(() => !!getToken())
  const displayName = computed(
    () => user.value?.display_name || user.value?.email?.split('@')[0] || '学习者',
  )

  /** Restore the session from the persisted token (router guard awaits this). */
  async function init(): Promise<void> {
    if (ready.value) return
    if (!getToken()) {
      ready.value = true
      return
    }
    try {
      await fetchMe()
    } catch {
      setToken(null)
      user.value = null
      profile.value = null
    }
    ready.value = true
  }

  async function fetchMe(): Promise<void> {
    const me = await authApi.me()
    user.value = me.user
    profile.value = me.profile
  }

  async function login(body: LoginRequest): Promise<void> {
    const res = await authApi.login(body)
    setToken(res.token)
    user.value = res.user
    await fetchMe()
  }

  async function register(body: RegisterRequest): Promise<void> {
    const res = await authApi.register(body)
    setToken(res.token)
    user.value = res.user
    await fetchMe()
  }

  async function logout(): Promise<void> {
    try {
      await authApi.logout()
    } catch {
      // best effort — local state is cleared regardless
    }
    setToken(null)
    user.value = null
    profile.value = null
  }

  return { user, profile, ready, isAuthenticated, displayName, init, fetchMe, login, register, logout }
})
