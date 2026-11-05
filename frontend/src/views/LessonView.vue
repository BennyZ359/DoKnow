<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { coursesApi } from '@/api/courses'
import { tasksApi } from '@/api/tasks'
import EmptyState from '@/components/EmptyState.vue'
import Spinner from '@/components/Spinner.vue'
import type { CourseDetail, Lesson } from '@/api/types'
import { useToastStore } from '@/stores/toast'
import { fmtMinutes } from '@/utils/format'
import { renderMarkdown } from '@/utils/markdown'

const route = useRoute()
const router = useRouter()
const toast = useToastStore()

const courseId = computed(() => route.params.courseId as string)
const lessonId = computed(() => route.params.lessonId as string)
const taskId = computed(() => (route.query.task as string | undefined) ?? undefined)

const loading = ref(true)
const course = ref<CourseDetail | null>(null)
const completing = ref(false)

const lesson = computed<Lesson | null>(() => {
  if (!course.value) return null
  return course.value.lessons.find((l) => l.id === lessonId.value) ?? null
})

const html = computed(() => renderMarkdown(lesson.value?.body ?? lesson.value?.summary ?? ''))

const index = computed(() =>
  course.value ? course.value.lessons.findIndex((l) => l.id === lessonId.value) : -1,
)
const prev = computed(() => (index.value > 0 ? course.value?.lessons[index.value - 1] ?? null : null))
const next = computed(() => {
  if (!course.value || index.value < 0) return null
  return course.value.lessons[index.value + 1] ?? null
})

function lessonRoute(l: Lesson): { name: string; params: Record<string, string>; query?: { task: string } } {
  return {
    name: 'lesson',
    params: { courseId: courseId.value, lessonId: l.id },
    query: taskId.value ? { task: taskId.value } : undefined,
  }
}

async function load(): Promise<void> {
  loading.value = true
  try {
    course.value = await coursesApi.get(courseId.value)
    // 由任务进入时顺手把任务置为进行中（fire-and-forget）
    if (taskId.value) void tasksApi.start(taskId.value).catch(() => {})
  } catch (e) {
    toast.error(e instanceof Error ? e.message : '内容加载失败')
  } finally {
    loading.value = false
  }
}

async function completeStudy(): Promise<void> {
  if (!taskId.value) return
  completing.value = true
  try {
    await tasksApi.complete(taskId.value)
    toast.success('学习任务完成！记得通过练习和讲解来真正巩固')
    router.push({ name: 'tasks' })
  } catch (e) {
    toast.error(e instanceof Error ? e.message : '操作失败')
  } finally {
    completing.value = false
  }
}

onMounted(load)
</script>

<template>
  <div>
    <div v-if="loading" class="card"><Spinner /></div>

    <template v-else-if="lesson && course">
      <div class="page-header">
        <div>
          <p class="page-sub" style="margin: 0 0 4px">
            <RouterLink :to="{ name: 'course', params: { courseId: course.id } }">{{ course.title }}</RouterLink>
            · 第 {{ index + 1 }}/{{ course.lessons.length }} 节
          </p>
          <h1 class="page-title">{{ lesson.title }}</h1>
        </div>
        <div class="row wrap">
          <span v-if="lesson.est_minutes" class="muted small">{{ fmtMinutes(lesson.est_minutes) }}</span>
          <button
            v-if="taskId"
            class="btn btn-primary btn-sm"
            type="button"
            :disabled="completing"
            @click="completeStudy"
          >
            {{ completing ? '提交中…' : '完成学习任务 ✓' }}
          </button>
        </div>
      </div>

      <div class="card">
        <div class="markdown-body" v-html="html" />
        <p v-if="!lesson.body && !lesson.summary" class="muted small">本节内容还在生成中。</p>
      </div>

      <div class="row between mt-16 wrap">
        <RouterLink v-if="prev" class="btn btn-ghost" :to="lessonRoute(prev)">← {{ prev.title }}</RouterLink>
        <span v-else class="muted small">已是第一节</span>
        <div class="row">
          <RouterLink
            v-if="next"
            class="btn btn-soft"
            :to="lessonRoute(next)"
          >
            {{ next.title }} →
          </RouterLink>
          <RouterLink
            v-else
            class="btn btn-ghost"
            :to="{ name: 'course', params: { courseId: course.id } }"
          >
            返回目录
          </RouterLink>
        </div>
      </div>
    </template>

    <div v-else class="card">
      <EmptyState icon="🤔" title="小节不存在">
        <RouterLink class="btn btn-primary" :to="{ name: 'dashboard' }">回到首页</RouterLink>
      </EmptyState>
    </div>
  </div>
</template>
