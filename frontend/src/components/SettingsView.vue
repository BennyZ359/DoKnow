<script setup lang="ts">
import { nextTick, onMounted, ref } from 'vue'
import Icon from './Icon.vue'
import RuntimeStatus from './RuntimeStatus.vue'
import type { Settings } from '../api'
defineProps<{ settings: Settings | null }>()
const emit = defineEmits<{ settings: [Settings] }>()
const heading = ref<HTMLElement | null>(null)
onMounted(async () => {
  await nextTick()
  heading.value?.focus({ preventScroll: true })
})
</script>
<template>
  <div class="page-heading">
    <div>
      <p class="eyebrow">THE WAY WE LEARN</p>
      <h1 ref="heading" tabindex="-1">一套有来处的学习方式。</h1>
      <p>让东方的学习智慧，与主动回忆、刻意练习和费曼讲解相遇。</p>
    </div>
    <span class="settings-leaf"><Icon name="leaf" :size="36" /></span>
  </div>
  <RuntimeStatus @settings="emit('settings', $event)" />
  <section v-if="settings" class="provider-panel">
    <div>
      <span class="eyebrow">当前学习服务</span>
      <h3>
        {{
          settings?.mode === 'demo'
            ? '体验模式 · 无需模型密钥'
            : `${settings?.provider || 'AI'} · ${settings?.model || '已配置模型'}`
        }}
      </h3>
      <p>
        {{
          settings?.mode === 'demo'
            ? '体验完整学习流程，使用预设教学内容与规则检查。规则反馈不能代替专业导师的概念与成果评估。'
            : '学习路线、导师对话与开放题评估由已配置的模型提供。关键推进规则与复习记录仍由学习系统管理。'
        }}
      </p>
    </div>
    <span class="pill">{{
      settings?.mode === 'demo' ? '本地体验' : settings?.configured ? '已配置' : '配置需检查'
    }}</span>
  </section>
  <div class="principles-grid">
    <article v-for="(principle, i) in settings?.principles" :key="principle.name">
      <span class="principle-number">{{ String(i + 1).padStart(2, '0') }}</span>
      <h3>{{ principle.name }}</h3>
      <p>{{ principle.practice }}</p>
    </article>
  </div>
  <section class="settings-about">
    <h3>关于这个学习空间</h3>
    <p>
      DoKnow
      首版面向本地个人学习。学习目标、实战记录、复盘与资料保存在你的学习服务中。模型配置由服务端环境变量管理，界面不会展示或保存密钥。
    </p>
    <ul v-if="settings?.limitations.length">
      <li v-for="limitation in settings.limitations" :key="limitation">{{ limitation }}</li>
    </ul>
    <div class="about-signature">
      <strong>DoKnow</strong><span>Know. Do. Grow. · 知而后行，行而后知。</span>
    </div>
  </section>
</template>

<style scoped>
h1:focus {
  outline: 3px solid #da9c56;
  outline-offset: 4px;
  border-radius: 4px;
}
</style>
