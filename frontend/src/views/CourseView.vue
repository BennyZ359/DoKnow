<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { coursesApi } from '@/api/courses'
import EmptyState from '@/components/EmptyState.vue'
import Spinner from '@/components/Spinner.vue'
import type { CourseDetail } from '@/api/types'
import { useToastStore } from '@/stores/toast'
import { fmtMinutes, statusClass } from '@/utils/format'

const route = useRoute()
const toast = useToastStore()

const courseId = computed(() => route.params.courseId as string)
const taskQuery = computed(() => (route.query.task as string | undefined) ?? undefined)

const loading = ref(true)
const course = ref<CourseDetail | null>(null)

async function load(): Promise<void> {
  loading.value = true
  try {
    course.value = await coursesApi.get(courseId.value)
  } catch (e) {
    toast.error(e instanceof Error ? e.message : '课程加载失败')
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <div>
    <div v-if="loading" class="card"><Spinner /></div>

    <template v-else-if="course">
      <div class="page-header">
        <div>
          <h1 class="page-title">{{ course.title }}</h1>
          <p class="page-sub">
            共 {{ course.lessons.length }} 节 · 约 {{ fmtMinutes(course.total_est_minutes) }}
            <span v-if="course.description" class="muted"> · {{ course.description }}</span>
          </p>
        </div>
        <div class="row">
          <span class="badge" :class="statusClass(course.status)">
            {{ course.status === 'PUBLISHED' ? '已发布' : (course.status ?? '生成中') }}
          </span>
          <RouterLink class="btn btn-ghost btn-sm" :to="{ name: 'goal', params: { goalId: course.goal_id } }">
            返回目标
          </RouterLink>
        </div>
      </div>

      <div v-if="course.lessons.length" class="row-list">
        <RouterLink
          v-for="lesson in course.lessons"
          :key="lesson.id"
          class="row-item card-hover"
          :to="{
            name: 'lesson',
            params: { courseId: course.id, lessonId: lesson.id },
            query: taskQuery ? { task: taskQuery } : undefined,
          }"
        >
          <span class="seq-chip">{{ lesson.order_index }}</span>
          <div class="row-main">
            <div class="row-title">{{ lesson.title }}</div>
            <div class="row-desc">{{ lesson.summary }}</div>
          </div>
          <div class="row-side">
            <span v-if="lesson.est_minutes" class="muted small">{{ fmtMinutes(lesson.est_minutes) }}</span>
            <span class="btn btn-soft btn-sm">阅读</span>
          </div>
        </RouterLink>
      </div>

      <div v-else class="card">
        <EmptyState icon="📖" title="课程内容还在生成中" hint="AI 完成写作并通过质检后会在这里发布" />
      </div>
    </template>

    <div v-else class="card">
      <EmptyState icon="🤔" title="课程不存在或尚未发布">
        <RouterLink class="btn btn-primary" :to="{ name: 'dashboard' }">回到首页</RouterLink>
      </EmptyState>
    </div>
  </div>
</template>

<style scoped>
.seq-chip {
  width: 30px;
  height: 30px;
  flex: none;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 10px;
  background: var(--accent-soft);
  color: var(--accent);
  font-weight: 600;
  font-size: 13px;
}
</style>
