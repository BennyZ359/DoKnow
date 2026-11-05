<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useGoalStore } from '@/stores/goal'
import { useToastStore } from '@/stores/toast'
import { settingsApi, normalizeBaseUrl } from '@/api/settings'

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

/* ---------- 自定义模型配置（通用 OpenAI 兼容） ---------- */

interface ProviderPreset {
  value: string
  label: string
  baseUrl: string
  model: string
}

const PROVIDERS: ProviderPreset[] = [
  { value: 'openai', label: 'OpenAI', baseUrl: 'https://api.openai.com/v1', model: 'gpt-4o-mini' },
  { value: 'deepseek', label: 'DeepSeek', baseUrl: 'https://api.deepseek.com/v1', model: 'deepseek-chat' },
  { value: 'moonshot', label: 'Moonshot 月之暗面', baseUrl: 'https://api.moonshot.cn/v1', model: 'moonshot-v1-8k' },
  { value: 'qwen', label: '通义千问', baseUrl: 'https://dashscope.aliyuncs.com/compatible-mode/v1', model: 'qwen-plus' },
  { value: 'ollama', label: 'Ollama（本地）', baseUrl: 'http://localhost:11434/v1', model: 'qwen2.5' },
  { value: 'custom', label: '自定义', baseUrl: '', model: '' },
]

const MODEL_KEY = 'doknow_llm_cfg'
const llm = reactive({
  provider: 'openai',
  base_url: 'https://api.openai.com/v1',
  api_key: '',
  model: 'gpt-4o-mini',
})
const showModel = ref(false)

function onProviderChange(): void {
  const preset = PROVIDERS.find((p) => p.value === llm.provider)
  if (preset && preset.value !== 'custom') {
    llm.base_url = preset.baseUrl
    llm.model = preset.model
  }
}

function loadModelConfig(): void {
  try {
    const raw = localStorage.getItem(MODEL_KEY)
    if (raw) Object.assign(llm, JSON.parse(raw))
  } catch {
    /* ignore malformed cache */
  }
}

function persistModelConfig(): void {
  try {
    localStorage.setItem(MODEL_KEY, JSON.stringify({ ...llm }))
  } catch {
    /* storage unavailable */
  }
}

watch(llm, persistModelConfig, { deep: true })

/** Push the configured model to the backend (non-fatal if it fails). */
async function syncModelConfig(): Promise<void> {
  if (!llm.api_key.trim() && !llm.base_url.trim()) return
  try {
    await settingsApi.updateLlm({
      provider: llm.provider,
      base_url: normalizeBaseUrl(llm.base_url) || undefined,
      api_key: llm.api_key.trim() || undefined,
      model: llm.model.trim() || undefined,
    })
  } catch {
    /* 模型配置同步失败不阻塞登录，可稍后在设置里重试 */
  }
}

async function submit(): Promise<void> {
  if (busy.value) return
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
    persistModelConfig()
    void syncModelConfig()
    void goalStore.loadDashboard().catch(() => {})
    router.push({ name: 'dashboard' })
  } catch (e) {
    error.value = e instanceof Error ? e.message : '操作失败，请重试'
  } finally {
    busy.value = false
  }
}

/* ---------- 左侧：极光 + 实时知识图谱粒子 ---------- */

interface GraphNode {
  x: number
  y: number
  vx: number
  vy: number
  r: number
  core: boolean
  phase: number
}

const showcaseRef = ref<HTMLElement | null>(null)
const graphCanvas = ref<HTMLCanvasElement | null>(null)
let graphCtx: CanvasRenderingContext2D | null = null
let graphNodes: GraphNode[] = []
let rafId = 0
let graphObserver: ResizeObserver | null = null
let reducedMotion = false

function seedGraph(w: number, h: number): void {
  const count = Math.max(30, Math.min(64, Math.round((w * h) / 24000)))
  graphNodes = Array.from({ length: count }, () => ({
    x: Math.random() * w,
    y: Math.random() * h,
    vx: (Math.random() - 0.5) * 0.16,
    vy: (Math.random() - 0.5) * 0.16,
    r: 1.1 + Math.random() * 1.7,
    core: Math.random() < 0.14,
    phase: Math.random() * Math.PI * 2,
  }))
}

function paintGraph(now: number): void {
  const c = graphCanvas.value
  const ctx = graphCtx
  if (!c || !ctx) return
  const w = c.clientWidth
  const h = c.clientHeight
  const t = now / 1000
  ctx.clearRect(0, 0, w, h)
  for (const n of graphNodes) {
    n.x += n.vx
    n.y += n.vy
    if (n.x < -24) n.x = w + 24
    else if (n.x > w + 24) n.x = -24
    if (n.y < -24) n.y = h + 24
    else if (n.y > h + 24) n.y = -24
  }
  const linkDist = 140
  for (let i = 0; i < graphNodes.length; i++) {
    const a = graphNodes[i]
    for (let j = i + 1; j < graphNodes.length; j++) {
      const b = graphNodes[j]
      const dx = a.x - b.x
      const dy = a.y - b.y
      const d2 = dx * dx + dy * dy
      if (d2 < linkDist * linkDist) {
        const alpha = (1 - Math.sqrt(d2) / linkDist) * 0.22
        ctx.strokeStyle = `rgba(178, 200, 255, ${alpha.toFixed(3)})`
        ctx.lineWidth = 1
        ctx.beginPath()
        ctx.moveTo(a.x, a.y)
        ctx.lineTo(b.x, b.y)
        ctx.stroke()
      }
    }
  }
  for (const n of graphNodes) {
    if (n.core) {
      const pulse = 0.5 + Math.sin(t * 1.6 + n.phase) * 0.5
      ctx.fillStyle = `rgba(130, 175, 255, ${(0.1 + pulse * 0.12).toFixed(3)})`
      ctx.beginPath()
      ctx.arc(n.x, n.y, 5 + pulse * 4, 0, Math.PI * 2)
      ctx.fill()
      ctx.fillStyle = 'rgba(232, 241, 255, 0.95)'
    } else {
      ctx.fillStyle = 'rgba(214, 226, 250, 0.7)'
    }
    ctx.beginPath()
    ctx.arc(n.x, n.y, n.core ? 1.9 : n.r, 0, Math.PI * 2)
    ctx.fill()
  }
}

function graphLoop(now: number): void {
  paintGraph(now)
  rafId = requestAnimationFrame(graphLoop)
}

function setupGraph(): void {
  const c = graphCanvas.value
  const wrap = showcaseRef.value
  if (!c || !wrap) return
  const rect = wrap.getBoundingClientRect()
  if (rect.width < 2 || rect.height < 2) return
  const dpr = window.devicePixelRatio || 1
  c.width = Math.round(rect.width * dpr)
  c.height = Math.round(rect.height * dpr)
  graphCtx = c.getContext('2d')
  if (graphCtx) graphCtx.setTransform(dpr, 0, 0, dpr, 0, 0)
  seedGraph(rect.width, rect.height)
}

onMounted(() => {
  loadModelConfig()
  reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches
  setupGraph()
  if (reducedMotion) {
    paintGraph(performance.now())
  } else {
    rafId = requestAnimationFrame(graphLoop)
  }
  graphObserver = new ResizeObserver(() => setupGraph())
  if (showcaseRef.value) graphObserver.observe(showcaseRef.value)
})

onBeforeUnmount(() => {
  cancelAnimationFrame(rafId)
  graphObserver?.disconnect()
  graphObserver = null
  graphCtx = null
})
</script>

<template>
  <div class="auth">
    <!-- 左侧品牌区：极光 + 实时知识图谱 + 王阳明 -->
    <aside ref="showcaseRef" class="auth-showcase">
      <div class="showcase-orbs" aria-hidden="true">
        <span class="orb orb-a" />
        <span class="orb orb-b" />
        <span class="orb orb-c" />
      </div>
      <div class="showcase-grid" aria-hidden="true"></div>
      <canvas ref="graphCanvas" class="showcase-graph" aria-hidden="true"></canvas>
      <div class="showcase-vignette" aria-hidden="true"></div>

      <div class="showcase-inner">
        <div class="showcase-brand">
          <span class="logo-dot logo-dot--light" />
          <span class="showcase-brand-name">DoKnow</span>
        </div>

        <blockquote class="showcase-quote">
          <p class="quote-text">
            未有知而不行者。<br />
            知而不行，<span class="quote-em">只是未知</span>。
          </p>
          <footer class="quote-from">—— 王阳明 ·《传习录》</footer>
        </blockquote>
      </div>

      <div class="showcase-foot">
        <span class="foot-dot" aria-hidden="true"></span>
        <span>知行合一 · AI 学习管家全程陪伴</span>
      </div>
    </aside>

    <!-- 右侧表单区：悬浮卡片 -->
    <main class="auth-panel">
      <div class="auth-form-wrap">
        <div class="auth-mobile-brand">
          <span class="logo-dot" />
          <span class="auth-mobile-name">DoKnow</span>
        </div>

        <Transition name="auth-swap" mode="out-in">
          <div :key="mode" class="auth-head">
            <h1 class="auth-title">{{ isRegister ? '创建你的账号' : '欢迎回来' }}</h1>
            <p class="auth-sub">
              {{ isRegister ? '只需一分钟，开始你的自主学习之旅' : '登录后继续你的学习旅程' }}
            </p>
          </div>
        </Transition>

        <div class="seg" role="tablist" aria-label="登录或注册">
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
          <form :key="mode" class="auth-form" novalidate @submit.prevent="submit">
            <div class="field">
              <label for="auth-email">邮箱</label>
              <div class="input-ico">
                <svg class="ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="5" width="18" height="14" rx="3" /><path d="m4 7 8 6 8-6" /></svg>
                <input
                  id="auth-email"
                  v-model="form.email"
                  class="input"
                  type="email"
                  placeholder="you@example.com"
                  autocomplete="email"
                />
              </div>
            </div>

            <div v-if="isRegister" class="field">
              <label for="auth-name">怎么称呼你 <span class="opt">（可选）</span></label>
              <div class="input-ico">
                <svg class="ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8Z" /><path d="M5 20c0-3.3 3.1-5.5 7-5.5s7 2.2 7 5.5" /></svg>
                <input
                  id="auth-name"
                  v-model="form.display_name"
                  class="input"
                  type="text"
                  placeholder="想被怎么称呼？"
                  maxlength="120"
                  autocomplete="nickname"
                />
              </div>
            </div>

            <div class="field">
              <label for="auth-pass">密码</label>
              <div class="pass-wrap input-ico">
                <svg class="ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="5" y="11" width="14" height="9" rx="2.5" /><path d="M8 11V8a4 4 0 0 1 8 0v3" /></svg>
                <input
                  id="auth-pass"
                  v-model="form.password"
                  class="input"
                  :type="showPassword ? 'text' : 'password'"
                  :placeholder="isRegister ? '设置密码（至少 8 位）' : '请输入密码'"
                  :autocomplete="isRegister ? 'new-password' : 'current-password'"
                />
                <button
                  class="pass-toggle"
                  type="button"
                  :aria-label="showPassword ? '隐藏密码' : '显示密码'"
                  @click="showPassword = !showPassword"
                >
                  <svg v-if="showPassword" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M10.6 5.8A9.8 9.8 0 0 1 12 5.5c6 0 9.5 6.5 9.5 6.5a17.4 17.4 0 0 1-2.4 3.1" /><path d="M14.1 14.1a3 3 0 0 1-4.2-4.2" /><path d="M6.2 6.2A16 16 0 0 0 2.5 12S6 18.5 12 18.5c1.8 0 3.4-.6 4.8-1.4" /><path d="m3 3 18 18" /></svg>
                  <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12Z" /><circle cx="12" cy="12" r="3" /></svg>
                </button>
              </div>
              <p v-if="isRegister" class="field-hint">至少 8 位字符，建议混合字母、数字与符号</p>
            </div>

            <div v-if="error" class="form-error" role="alert">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M10.3 3.9 1.9 18a2 2 0 0 0 1.7 3h16.8a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z" /><path d="M12 9v4" /><path d="M12 17h.01" /></svg>
              <span>{{ error }}</span>
            </div>

            <button class="btn btn-primary btn-block btn-lg auth-submit" type="submit" :disabled="busy">
              <span v-if="busy" class="btn-spinner" aria-hidden="true" />
              {{ busy ? '请稍候…' : isRegister ? '创建账号' : '登录' }}
            </button>
          </form>
        </Transition>

        <!-- 自定义模型配置 -->
        <div class="model-box">
          <button class="model-toggle" type="button" :aria-expanded="showModel" @click="showModel = !showModel">
            <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
              <path d="M4 7h9M17 7h3M4 17h3M11 17h9" />
              <circle cx="15" cy="7" r="2.2" />
              <circle cx="9" cy="17" r="2.2" />
            </svg>
            <span>模型设置</span>
            <span class="model-badge" v-if="llm.api_key || llm.base_url">已配置</span>
            <svg class="chev" :class="{ open: showModel }" viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m6 9 6 6 6-6" /></svg>
          </button>

          <div v-if="showModel" class="model-panel">
            <p class="model-note">可选。配置任意 OpenAI 兼容模型，登录后 AI 功能将使用它。</p>
            <div class="field">
              <label for="llm-provider">提供商</label>
              <select id="llm-provider" v-model="llm.provider" class="input" @change="onProviderChange">
                <option v-for="p in PROVIDERS" :key="p.value" :value="p.value">{{ p.label }}</option>
              </select>
            </div>
            <div class="field">
              <label for="llm-base">Base URL</label>
              <input id="llm-base" v-model="llm.base_url" class="input" type="url" placeholder="https://api.example.com/v1" />
            </div>
            <div class="field">
              <label for="llm-key">API Key</label>
              <input id="llm-key" v-model="llm.api_key" class="input" type="password" placeholder="sk-…" autocomplete="off" />
            </div>
            <div class="field">
              <label for="llm-model">模型名称</label>
              <input id="llm-model" v-model="llm.model" class="input" type="text" placeholder="gpt-4o-mini / deepseek-chat" />
            </div>
          </div>
        </div>

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

/* ---------- 左侧品牌区：极光 + 实时知识图谱 ---------- */

.auth-showcase {
  position: relative;
  isolation: isolate;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  gap: 40px;
  padding: 44px 56px 40px;
  color: #fff;
  background: linear-gradient(158deg, #0d1636 0%, #141f4d 46%, #2b2067 100%);
}

.showcase-orbs {
  position: absolute;
  inset: 0;
  z-index: 0;
  pointer-events: none;
  overflow: hidden;
}

.orb {
  position: absolute;
  border-radius: 50%;
  filter: blur(90px);
  opacity: 0.42;
  animation: orbFloat 18s ease-in-out infinite;
}

.orb-a {
  width: 420px;
  height: 420px;
  right: -90px;
  top: -110px;
  background: radial-gradient(circle, rgba(47, 123, 246, 0.75), rgba(47, 123, 246, 0) 70%);
}

.orb-b {
  width: 360px;
  height: 360px;
  left: -120px;
  bottom: -90px;
  background: radial-gradient(circle, rgba(109, 63, 209, 0.8), rgba(109, 63, 209, 0) 70%);
  animation-delay: -6s;
}

.orb-c {
  width: 240px;
  height: 240px;
  right: 26%;
  bottom: 14%;
  background: radial-gradient(circle, rgba(18, 165, 165, 0.6), rgba(18, 165, 165, 0) 70%);
  opacity: 0.32;
  animation-delay: -11s;
}

@keyframes orbFloat {
  0%, 100% { transform: translate(0, 0) scale(1); }
  50% { transform: translate(26px, -30px) scale(1.06); }
}

.showcase-grid {
  position: absolute;
  inset: 0;
  z-index: 0;
  pointer-events: none;
  background-image:
    linear-gradient(rgba(255, 255, 255, 0.045) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255, 255, 255, 0.045) 1px, transparent 1px);
  background-size: 46px 46px;
  -webkit-mask-image: radial-gradient(ellipse 90% 70% at 50% 42%, rgba(0, 0, 0, 0.9), transparent 78%);
  mask-image: radial-gradient(ellipse 90% 70% at 50% 42%, rgba(0, 0, 0, 0.9), transparent 78%);
}

.showcase-graph {
  position: absolute;
  inset: 0;
  z-index: 1;
  width: 100%;
  height: 100%;
  pointer-events: none;
}

.showcase-vignette {
  position: absolute;
  inset: 0;
  z-index: 1;
  pointer-events: none;
  background: radial-gradient(120% 92% at 50% 44%, transparent 42%, rgba(7, 11, 28, 0.6) 100%);
}

.showcase-inner {
  position: relative;
  z-index: 2;
  display: flex;
  flex-direction: column;
  gap: 56px;
  max-width: 560px;
}

.showcase-brand {
  display: flex;
  align-items: center;
  gap: 10px;
}

.showcase-brand-name {
  font-size: 20px;
  font-weight: 700;
  letter-spacing: 0.2px;
}

.showcase-quote {
  margin: 0;
  padding: 0;
  border: 0;
}

.quote-text {
  margin: 0;
  font-family: 'Songti SC', 'Noto Serif SC', 'Source Han Serif SC', Georgia, serif;
  font-size: 40px;
  line-height: 1.5;
  font-weight: 600;
  letter-spacing: 1px;
  color: #f3f6ff;
}

.quote-em {
  background: linear-gradient(90deg, #9dbdff, #d3b8ff);
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
}

.quote-from {
  margin-top: 26px;
  font-size: 15px;
  letter-spacing: 0.5px;
  color: rgba(200, 212, 240, 0.55);
}

.showcase-foot {
  position: relative;
  z-index: 2;
  display: flex;
  align-items: center;
  gap: 10px;
  padding-top: 18px;
  border-top: 1px solid rgba(255, 255, 255, 0.1);
  font-size: 13px;
  color: rgba(200, 212, 240, 0.55);
}

.foot-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #4ade80;
  box-shadow: 0 0 0 4px rgba(74, 222, 128, 0.15);
}

/* ---------- 右侧表单区：悬浮卡片 ---------- */

.auth-panel {
  display: grid;
  place-items: center;
  padding: 40px 28px;
  background:
    radial-gradient(900px 640px at 88% -8%, rgba(47, 123, 246, 0.09), transparent 60%),
    radial-gradient(760px 600px at -6% 108%, rgba(109, 63, 209, 0.09), transparent 58%),
    var(--bg);
}

.auth-form-wrap {
  position: relative;
  width: 100%;
  max-width: 408px;
  padding: 34px 32px 30px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 20px;
  box-shadow: 0 1px 2px rgba(16, 24, 40, 0.04), 0 10px 34px rgba(16, 24, 40, 0.07);
}

.auth-form-wrap::before {
  content: '';
  position: absolute;
  top: 0;
  left: 24px;
  right: 24px;
  height: 2px;
  border-radius: 2px;
  background: linear-gradient(90deg, transparent, rgba(47, 123, 246, 0.55), rgba(109, 63, 209, 0.55), transparent);
}

.auth-mobile-brand {
  display: none;
  align-items: center;
  justify-content: center;
  gap: 10px;
  margin-bottom: 20px;
  font-size: 18px;
  font-weight: 700;
}

.auth-mobile-name {
  font-size: 19px;
  font-weight: 700;
}

.auth-head {
  text-align: center;
  margin-bottom: 22px;
}

.auth-title {
  margin: 0;
  font-size: 25px;
  font-weight: 800;
  letter-spacing: -0.3px;
  color: var(--text);
}

.auth-sub {
  margin: 8px 0 0;
  font-size: 14px;
  color: var(--muted);
}

.seg {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 4px;
  padding: 4px;
  margin-bottom: 22px;
  background: #edf1f6;
  border: 1px solid var(--border);
  border-radius: 12px;
}

.seg-btn {
  appearance: none;
  border: 0;
  background: transparent;
  height: 38px;
  border-radius: 9px;
  font-size: 14px;
  font-weight: 600;
  font-family: inherit;
  color: var(--muted);
  cursor: pointer;
  transition: background 0.18s ease, color 0.18s ease, box-shadow 0.18s ease;
}

.seg-btn:hover {
  color: var(--text);
}

.seg-btn.active {
  background: var(--surface);
  color: var(--accent);
  font-weight: 700;
  box-shadow: 0 1px 4px rgba(16, 24, 40, 0.1);
}

.field {
  margin-bottom: 16px;
}

.field label {
  display: block;
  margin-bottom: 7px;
  font-size: 13px;
  font-weight: 600;
  color: var(--text);
}

.opt {
  margin-left: 4px;
  font-size: 12px;
  font-weight: 500;
  color: var(--muted);
}

.input-ico {
  position: relative;
}

.input-ico .ico {
  position: absolute;
  left: 13px;
  top: 50%;
  transform: translateY(-50%);
  width: 18px;
  height: 18px;
  color: var(--muted);
  pointer-events: none;
  transition: color 0.18s ease;
}

.input-ico:focus-within .ico {
  color: var(--accent);
}

.auth-form .input,
.model-panel .input {
  width: 100%;
  height: 46px;
  padding-left: 42px;
  border-radius: 11px;
  font-size: 14.5px;
}

.model-panel .input {
  padding-left: 12px;
  height: 42px;
  font-size: 13.5px;
}

.auth-form .pass-wrap .input {
  padding-right: 44px;
}

select.input {
  padding-left: 12px;
  appearance: none;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%2379818f' stroke-width='2' stroke-linecap='round'%3E%3Cpath d='m6 9 6 6 6-6'/%3E%3C/svg%3E");
  background-repeat: no-repeat;
  background-position: right 12px center;
  background-size: 16px;
}

.pass-toggle {
  position: absolute;
  right: 6px;
  top: 50%;
  transform: translateY(-50%);
  display: grid;
  place-items: center;
  width: 34px;
  height: 34px;
  border: none;
  border-radius: 8px;
  background: transparent;
  color: var(--muted);
  cursor: pointer;
  transition: color 0.15s ease, background 0.15s ease;
}

.pass-toggle:hover {
  color: var(--text);
  background: #f1f4f8;
}

.pass-toggle svg {
  width: 19px;
  height: 19px;
}

.field-hint {
  margin-top: 8px;
  font-size: 12.5px;
  color: var(--muted);
}

.form-error {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  margin: 4px 0 14px;
  padding: 11px 13px;
  border-radius: 11px;
  font-size: 13px;
  line-height: 1.5;
  background: var(--danger-soft);
  border: 1px solid rgba(209, 60, 60, 0.16);
  color: var(--danger);
}

.form-error svg {
  flex: 0 0 auto;
  width: 16px;
  height: 16px;
  margin-top: 2px;
}

.auth-submit {
  margin-top: 22px;
  height: 50px;
  border: 0;
  border-radius: 12px;
  font-size: 15px;
  font-weight: 700;
  letter-spacing: 0.2px;
  gap: 10px;
  color: #fff;
  background: linear-gradient(135deg, #2f7bf6 0%, #5d4bdd 55%, #6d3fd1 100%);
  box-shadow: 0 6px 18px rgba(47, 123, 246, 0.3);
  transition: transform 0.16s ease, box-shadow 0.16s ease, filter 0.16s ease;
}

.auth-submit:hover:not(:disabled) {
  filter: brightness(1.04);
  transform: translateY(-1px);
  box-shadow: 0 9px 24px rgba(47, 123, 246, 0.38);
}

.auth-submit:active:not(:disabled) {
  transform: translateY(0);
  box-shadow: 0 4px 12px rgba(47, 123, 246, 0.3);
}

.auth-submit:disabled {
  cursor: not-allowed;
  opacity: 0.75;
  box-shadow: 0 4px 12px rgba(47, 123, 246, 0.25);
}

.btn-spinner {
  width: 17px;
  height: 17px;
  border-radius: 50%;
  border: 2px solid rgba(255, 255, 255, 0.4);
  border-top-color: #fff;
  animation: spin 0.7s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

/* ---------- 模型配置 ---------- */

.model-box {
  margin-top: 20px;
  border-top: 1px solid var(--border);
  padding-top: 14px;
}

.model-toggle {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 6px 2px;
  border: none;
  background: none;
  font-family: inherit;
  font-size: 13px;
  font-weight: 600;
  color: var(--muted);
  cursor: pointer;
  transition: color 0.15s ease;
}

.model-toggle:hover {
  color: var(--text);
}

.model-toggle .chev {
  margin-left: auto;
  transition: transform 0.18s ease;
}

.model-toggle .chev.open {
  transform: rotate(180deg);
}

.model-badge {
  padding: 1px 8px;
  border-radius: 999px;
  background: var(--success-soft);
  color: var(--success);
  font-size: 11px;
  font-weight: 600;
}

.model-panel {
  margin-top: 14px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.model-note {
  margin: 0;
  font-size: 12px;
  line-height: 1.5;
  color: var(--muted);
}

.model-panel .field {
  margin-bottom: 0;
}

.model-panel label {
  font-size: 12px;
  margin-bottom: 5px;
}

.auth-terms {
  margin: 18px 0 0;
  text-align: center;
  font-size: 12.5px;
  line-height: 1.6;
  color: var(--muted);
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
  transform: translateY(-4px);
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
    padding: 32px 20px;
  }

  .auth-mobile-brand {
    display: inline-flex;
  }

  .auth-form-wrap {
    max-width: 420px;
    padding: 30px 24px 26px;
  }
}

@media (prefers-reduced-motion: reduce) {
  .orb {
    animation: none !important;
  }
}
</style>
