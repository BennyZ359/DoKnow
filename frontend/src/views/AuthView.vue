<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useGoalStore } from '@/stores/goal'
import { useToastStore } from '@/stores/toast'

const router = useRouter()
const auth = useAuthStore()
const goalStore = useGoalStore()
const toast = useToastStore()

const mode = ref<'login' | 'register'>('login')
const form = reactive({ email: '', password: '', display_name: '' })
const busy = ref(false)
const error = ref('')

const isRegister = computed(() => mode.value === 'register')

function switchMode(next: 'login' | 'register'): void {
  mode.value = next
  error.value = ''
}

async function submit(): Promise<void> {
  error.value = ''
  if (!form.email.trim() || !form.password) {
    error.value = '请输入邮箱和密码'
    return
  }
  if (isRegister.value && form.password.length < 8) {
    error.value = '密码至少需要 8 位'
    return
  }
  busy.value = true
  try {
    if (isRegister.value) {
      await auth.register({
        email: form.email.trim(),
        password: form.password,
        display_name: form.display_name.trim() || undefined,
      })
      toast.success('欢迎加入 DoKnow，开始你的自主学习之旅！')
    } else {
      await auth.login({ email: form.email.trim(), password: form.password })
      toast.success('欢迎回来！')
    }
    void goalStore.loadDashboard().catch(() => {})
    router.push({ name: 'dashboard' })
  } catch (e) {
    error.value = e instanceof Error ? e.message : '操作失败，请重试'
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="auth-wrap">
    <div class="auth-card card">
      <div class="auth-brand">
        <span class="logo-dot" />
        <span class="auth-brand-name">DoKnow</span>
      </div>
      <p class="auth-tagline">全托管式 AI 自主学习系统 · 学 练 用 讲 温</p>

      <div class="tabs">
        <button class="tab" :class="{ active: mode === 'login' }" type="button" @click="switchMode('login')">
          登录
        </button>
        <button
          class="tab"
          :class="{ active: mode === 'register' }"
          type="button"
          @click="switchMode('register')"
        >
          注册
        </button>
      </div>

      <form @submit.prevent="submit">
        <div class="field">
          <label>邮箱</label>
          <input v-model="form.email" class="input" type="email" placeholder="you@example.com" autocomplete="email" />
        </div>
        <div v-if="isRegister" class="field">
          <label>昵称（可选）</label>
          <input v-model="form.display_name" class="input" placeholder="想被怎么称呼？" maxlength="120" />
        </div>
        <div class="field">
          <label>密码</label>
          <input
            v-model="form.password"
            class="input"
            type="password"
            placeholder="至少 8 位"
            :autocomplete="isRegister ? 'new-password' : 'current-password'"
          />
          <p v-if="isRegister" class="field-hint">至少 8 位，建议混合字母与数字</p>
        </div>

        <p v-if="error" class="form-error">{{ error }}</p>

        <button class="btn btn-primary btn-block btn-lg mt-16" type="submit" :disabled="busy">
          {{ busy ? '请稍候…' : isRegister ? '创建账号' : '登录' }}
        </button>
      </form>
    </div>
  </div>
</template>
