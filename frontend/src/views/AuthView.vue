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
const showPassword = ref(false)

const isRegister = computed(() => mode.value === 'register')

function switchMode(next: 'login' | 'register'): void {
  if (mode.value === next) return
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
  <div class="auth">
    <!-- 左侧品牌区 -->
    <aside class="auth-showcase">
      <div class="showcase-orbs" aria-hidden="true">
        <span class="orb orb-a" />
        <span class="orb orb-b" />
        <span class="orb orb-c" />
      </div>

      <svg class="showcase-graph" viewBox="0 0 320 240" aria-hidden="true">
        <g stroke="rgba(255,255,255,0.18)" stroke-width="1.4">
          <line x1="60" y1="60" x2="150" y2="40" />
          <line x1="150" y1="40" x2="240" y2="80" />
          <line x1="60" y1="60" x2="110" y2="150" />
          <line x1="110" y1="150" x2="150" y2="40" />
          <line x1="110" y1="150" x2="220" y2="170" />
          <line x1="220" y1="170" x2="240" y2="80" />
          <line x1="150" y1="40" x2="220" y2="170" />
        </g>
        <g fill="rgba(255,255,255,0.85)">
          <circle cx="60" cy="60" r="5" />
          <circle cx="150" cy="40" r="7" />
          <circle cx="240" cy="80" r="5" />
          <circle cx="110" cy="150" r="6" />
          <circle cx="220" cy="170" r="5" />
        </g>
      </svg>

      <div class="showcase-inner">
        <div class="showcase-brand">
          <span class="logo-dot logo-dot--light" />
          <span class="showcase-brand-name">DoKnow</span>
        </div>

        <h1 class="showcase-title">把「想学」<br />变成「<span class="grad">学会</span>」</h1>
        <p class="showcase-sub">
          输入一个学习目标，AI 为你搭建知识体系、规划路径、生成课程，并每天陪你
          学·练·讲·温，直到真正掌握。
        </p>

        <ul class="showcase-features">
          <li><span class="feat-ico">🧠</span><span><b>学</b> · 搭建知识图谱，规划最优路径</span></li>
          <li><span class="feat-ico">✍️</span><span><b>练</b> · 智能出题，即时批改巩固</span></li>
          <li><span class="feat-ico">🚀</span><span><b>用</b> · 真实场景任务，学以致用</span></li>
          <li><span class="feat-ico">🗣️</span><span><b>讲</b> · 用自己的话讲出来，暴露盲区</span></li>
          <li><span class="feat-ico">🌱</span><span><b>温</b> · 间隔复习，对抗遗忘曲线</span></li>
        </ul>
      </div>

      <p class="showcase-foot">AI 学习管家全程陪伴 · 知行合一</p>
    </aside>

    <!-- 右侧表单区 -->
    <main class="auth-panel">
      <div class="auth-form-wrap">
        <div class="auth-mobile-brand">
          <span class="logo-dot" />
          <span class="auth-mobile-name">DoKnow</span>
        </div>

        <Transition name="auth-swap" mode="out-in">
          <div :key="mode">
            <h2 class="auth-title">{{ isRegister ? '创建你的账号' : '欢迎回来' }}</h2>
            <p class="auth-sub">
              {{ isRegister ? '几秒钟开始你的第一段 AI 自主学习' : '登录以继续你的学习计划' }}
            </p>
          </div>
        </Transition>

        <div class="seg" role="tablist">
          <button
            class="seg-btn"
            :class="{ active: mode === 'login' }"
            type="button"
            role="tab"
            :aria-selected="mode === 'login'"
            @click="switchMode('login')"
          >
            登录
          </button>
          <button
            class="seg-btn"
            :class="{ active: mode === 'register' }"
            type="button"
            role="tab"
            :aria-selected="mode === 'register'"
            @click="switchMode('register')"
          >
            注册
          </button>
        </div>

        <Transition name="auth-swap" mode="out-in">
          <form :key="mode" @submit.prevent="submit" novalidate>
            <div class="field">
              <label for="auth-email">邮箱</label>
              <input
                id="auth-email"
                v-model="form.email"
                class="input"
                type="email"
                placeholder="you@example.com"
                autocomplete="email"
              />
            </div>

            <div v-if="isRegister" class="field">
              <label for="auth-name">昵称<span class="opt">（可选）</span></label>
              <input
                id="auth-name"
                v-model="form.display_name"
                class="input"
                placeholder="想被怎么称呼？"
                maxlength="120"
              />
            </div>

            <div class="field">
              <label for="auth-pass">密码</label>
              <div class="pass-wrap">
                <input
                  id="auth-pass"
                  v-model="form.password"
                  class="input"
                  :type="showPassword ? 'text' : 'password'"
                  placeholder="至少 8 位"
                  :autocomplete="isRegister ? 'new-password' : 'current-password'"
                />
                <button
                  class="pass-toggle"
                  type="button"
                  :aria-label="showPassword ? '隐藏密码' : '显示密码'"
                  @click="showPassword = !showPassword"
                >
                  <svg v-if="!showPassword" viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12Z" />
                    <circle cx="12" cy="12" r="3" />
                  </svg>
                  <svg v-else viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12Z" />
                    <circle cx="12" cy="12" r="3" />
                    <line x1="4" y1="20" x2="20" y2="4" />
                  </svg>
                </button>
              </div>
              <p v-if="isRegister" class="field-hint">至少 8 位，建议混合字母与数字</p>
            </div>

            <p v-if="error" class="form-error" role="alert">
              <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
                <circle cx="12" cy="12" r="10" />
                <line x1="12" y1="8" x2="12" y2="12" />
                <line x1="12" y1="16" x2="12.01" y2="16" />
              </svg>
              {{ error }}
            </p>

            <button class="btn btn-primary btn-block btn-lg auth-submit" type="submit" :disabled="busy">
              <span v-if="busy" class="btn-spinner" aria-hidden="true" />
              {{ busy ? '请稍候…' : isRegister ? '创建账号' : '登录' }}
            </button>
          </form>
        </Transition>

        <p class="auth-terms">
          登录或注册即表示你同意 DoKnow 的服务条款与隐私政策。
        </p>
      </div>
    </main>
  </div>
</template>

<style scoped>
.auth {
  min-height: 100vh;
  display: grid;
  grid-template-columns: minmax(0, 1.05fr) minmax(0, 1fr);
}

/* ---------- 左侧品牌区 ---------- */

.auth-showcase {
  position: relative;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  padding: 48px 56px;
  color: #fff;
  background: linear-gradient(160deg, #101a3a 0%, #1b2a63 55%, #3a2a86 100%);
}

.showcase-orbs {
  position: absolute;
  inset: 0;
  pointer-events: none;
}

.orb {
  position: absolute;
  border-radius: 50%;
  filter: blur(70px);
  opacity: 0.5;
  animation: float 14s ease-in-out infinite;
}

.orb-a {
  width: 360px;
  height: 360px;
  background: #2f7bf6;
  top: -80px;
  right: -60px;
}

.orb-b {
  width: 300px;
  height: 300px;
  background: #6d3fd1;
  bottom: -60px;
  left: -40px;
  animation-delay: -5s;
}

.orb-c {
  width: 200px;
  height: 200px;
  background: #12a5a5;
  top: 40%;
  left: 40%;
  opacity: 0.32;
  animation-delay: -9s;
}

@keyframes float {
  0%, 100% { transform: translate(0, 0) scale(1); }
  50% { transform: translate(24px, -28px) scale(1.06); }
}

.showcase-graph {
  position: absolute;
  right: 40px;
  bottom: 90px;
  width: 300px;
  opacity: 0.9;
  animation: drift 18s ease-in-out infinite;
}

@keyframes drift {
  0%, 100% { transform: translateY(0); }
  50% { transform: translateY(-12px); }
}

.showcase-inner {
  position: relative;
  z-index: 1;
  max-width: 460px;
}

.showcase-brand {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 40px;
}

.logo-dot--light::after {
  background: #1b2a63;
}

.showcase-brand-name {
  font-size: 20px;
  font-weight: 700;
  letter-spacing: 0.2px;
}

.showcase-title {
  font-size: 40px;
  line-height: 1.2;
  font-weight: 700;
  letter-spacing: -0.5px;
  margin: 0;
}

.showcase-title .grad {
  background: linear-gradient(90deg, #7fb2ff, #c9a6ff);
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
}

.showcase-sub {
  margin-top: 18px;
  font-size: 15px;
  line-height: 1.7;
  color: rgba(255, 255, 255, 0.78);
}

.showcase-features {
  list-style: none;
  margin: 36px 0 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.showcase-features li {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 14.5px;
  color: rgba(255, 255, 255, 0.82);
}

.feat-ico {
  width: 34px;
  height: 34px;
  flex: none;
  display: grid;
  place-items: center;
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.1);
  border: 1px solid rgba(255, 255, 255, 0.14);
  font-size: 17px;
}

.showcase-features b {
  color: #fff;
  font-weight: 600;
}

.showcase-foot {
  position: relative;
  z-index: 1;
  font-size: 13px;
  color: rgba(255, 255, 255, 0.5);
}

/* ---------- 右侧表单区 ---------- */

.auth-panel {
  display: grid;
  place-items: center;
  padding: 48px 32px;
  background: var(--bg);
}

.auth-form-wrap {
  width: 100%;
  max-width: 400px;
}

.auth-mobile-brand {
  display: none;
  align-items: center;
  gap: 8px;
  margin-bottom: 28px;
}

.auth-mobile-name {
  font-size: 19px;
  font-weight: 700;
}

.auth-title {
  font-size: 26px;
  font-weight: 700;
  letter-spacing: -0.3px;
  margin: 0;
}

.auth-sub {
  margin-top: 8px;
  color: var(--muted);
  font-size: 14.5px;
}

.seg {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 4px;
  padding: 4px;
  margin: 28px 0 24px;
  background: #eaeef4;
  border-radius: 12px;
}

.seg-btn {
  padding: 9px 0;
  border: none;
  border-radius: 9px;
  background: transparent;
  font-size: 14px;
  font-weight: 500;
  font-family: inherit;
  color: var(--muted);
  cursor: pointer;
  transition: all 0.18s ease;
}

.seg-btn:hover {
  color: var(--text);
}

.seg-btn.active {
  background: var(--surface);
  color: var(--accent);
  font-weight: 600;
  box-shadow: 0 1px 3px rgba(16, 24, 40, 0.1);
}

.opt {
  color: var(--muted);
  font-weight: 400;
  font-size: 12px;
}

.pass-wrap {
  position: relative;
}

.pass-wrap .input {
  padding-right: 44px;
}

.pass-toggle {
  position: absolute;
  right: 6px;
  top: 50%;
  transform: translateY(-50%);
  width: 32px;
  height: 32px;
  display: grid;
  place-items: center;
  border: none;
  background: transparent;
  color: var(--muted);
  border-radius: 8px;
  cursor: pointer;
  transition: color 0.15s ease, background 0.15s ease;
}

.pass-toggle:hover {
  color: var(--text);
  background: #f0f3f8;
}

.form-error {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  margin: 4px 0 0;
  padding: 11px 14px;
  border-radius: var(--radius-sm);
  background: var(--danger-soft);
  color: var(--danger);
  font-size: 13px;
}

.form-error svg {
  flex: none;
  margin-top: 2px;
}

.auth-submit {
  margin-top: 22px;
  height: 48px;
  font-size: 15px;
  gap: 10px;
}

.btn-spinner {
  width: 16px;
  height: 16px;
  border-radius: 50%;
  border: 2px solid rgba(255, 255, 255, 0.45);
  border-top-color: #fff;
  animation: spin 0.7s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.auth-terms {
  margin-top: 22px;
  text-align: center;
  font-size: 12.5px;
  color: var(--muted);
  line-height: 1.6;
}

/* 模式切换过渡 */
.auth-swap-enter-active,
.auth-swap-leave-active {
  transition: opacity 0.18s ease, transform 0.18s ease;
}

.auth-swap-enter-from {
  opacity: 0;
  transform: translateY(6px);
}

.auth-swap-leave-to {
  opacity: 0;
  transform: translateY(-6px);
}

/* ---------- 响应式 ---------- */

@media (max-width: 900px) {
  .auth {
    grid-template-columns: 1fr;
  }

  .auth-showcase {
    display: none;
  }

  .auth-panel {
    min-height: 100vh;
    background: var(--bg);
  }

  .auth-mobile-brand {
    display: flex;
    justify-content: center;
  }

  .auth-form-wrap {
    max-width: 420px;
  }
}
</style>
