<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { goalsApi } from '@/api/goals'
import { useToastStore } from '@/stores/toast'

const router = useRouter()
const toast = useToastStore()

const busy = ref(false)
const form = reactive({
  title: '',
  description: '',
  target_level: '',
  deadline: '',
  priority: 3,
  criteria: '',
})

async function submit(): Promise<void> {
  if (form.title.trim().length < 2) {
    toast.error('目标标题至少 2 个字，例如「三个月掌握 SQL 数据分析」')
    return
  }
  busy.value = true
  try {
    const criteria = form.criteria
      .split('\n')
      .map((s) => s.trim())
      .filter(Boolean)
    const created = await goalsApi.create({
      title: form.title.trim(),
      description: form.description.trim() || undefined,
      target_level: form.target_level.trim() || undefined,
      deadline: form.deadline || undefined,
      priority: form.priority,
      success_criteria: criteria.length ? { criteria } : undefined,
    })
    // 激活后 AI 开始搭建知识体系 → 学习路径 → 课程（异步流水线）
    try {
      await goalsApi.activate(created.id)
    } catch {
      toast.info('目标已创建，但激活暂未成功，可稍后在目标页重试')
    }
    toast.success('目标已创建！AI 正在搭建知识体系…')
    router.push({ name: 'goal', params: { goalId: created.id } })
  } catch (e) {
    toast.error(e instanceof Error ? e.message : '创建失败，请重试')
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div style="max-width: 640px; margin: 0 auto">
    <div class="page-header">
      <div>
        <h1 class="page-title">创建学习目标</h1>
        <p class="page-sub">描述你想学会什么——越具体，AI 搭建的知识体系越贴合</p>
      </div>
    </div>

    <form class="card" @submit.prevent="submit">
      <div class="field">
        <label>学习目标 *</label>
        <input
          v-model="form.title"
          class="input"
          placeholder="例如：三个月掌握 SQL 数据分析，能独立完成业务报表"
          maxlength="255"
        />
      </div>

      <div class="field">
        <label>补充说明</label>
        <textarea
          v-model="form.description"
          class="textarea"
          rows="3"
          placeholder="背景、基础、应用场景……AI 会据此定制学习内容（可选）"
        />
      </div>

      <div class="row wrap" style="gap: 16px">
        <div class="field flex-1">
          <label>目标水平</label>
          <input v-model="form.target_level" class="input" placeholder="例如：能独立上手工作项目" />
        </div>
        <div class="field" style="width: 170px">
          <label>优先级</label>
          <select v-model.number="form.priority" class="select">
            <option :value="1">1 · 从容</option>
            <option :value="2">2</option>
            <option :value="3">3 · 标准</option>
            <option :value="4">4</option>
            <option :value="5">5 · 冲刺</option>
          </select>
        </div>
        <div class="field" style="width: 170px">
          <label>截止日期</label>
          <input v-model="form.deadline" class="input" type="date" />
        </div>
      </div>

      <div class="field">
        <label>怎样算学会了？</label>
        <textarea
          v-model="form.criteria"
          class="textarea"
          rows="3"
          placeholder="每行一条，例如：&#10;能写出多表关联查询&#10;能解释索引的原理"
        />
        <p class="field-hint">AI 会把这些标准转化为知识点与评估依据（可选）</p>
      </div>

      <div class="row">
        <button class="btn btn-primary btn-lg" type="submit" :disabled="busy">
          {{ busy ? '创建中…' : '创建并激活目标' }}
        </button>
        <RouterLink class="btn btn-ghost" :to="{ name: 'dashboard' }">取消</RouterLink>
      </div>
    </form>
  </div>
</template>
