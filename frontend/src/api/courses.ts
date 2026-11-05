import { http } from './client'
import type {
  AnswerPayload,
  AttemptResponse,
  CourseDetail,
  CourseSummary,
  Exercise,
  ExerciseGenerateRequest,
  ExerciseGenerateResponse,
  ExplanationResponse,
  Lesson,
} from './types'

export interface CourseListResponse {
  courses: CourseSummary[]
}

export interface ExerciseListResponse {
  exercises: Exercise[]
}

/**
 * /courses + /knowledge-points/{kp}/exercises + /tasks/{id}/explanation
 * 学（课程/小节）· 练（练习题）· 讲（讲解评估）三个交互面.
 */
export const coursesApi = {
  list: (goalId: string) => http.get<CourseListResponse>('/courses', { goal_id: goalId }),
  get: (courseId: string) => http.get<CourseDetail>(`/courses/${courseId}`),
  lesson: (courseId: string, lessonId: string) =>
    http.get<Lesson>(`/courses/${courseId}/lessons/${lessonId}`),

  exercises: (kpId: string, goalId: string) =>
    http.get<ExerciseListResponse>(`/knowledge-points/${kpId}/exercises`, { goal_id: goalId }),
  regenerateExercises: (exerciseId: string, goalId: string, body: ExerciseGenerateRequest) =>
    http.post<ExerciseGenerateResponse>(
      `/knowledge-points/exercises/${exerciseId}/generate`,
      body,
      { goal_id: goalId },
    ),
  attempt: (exerciseId: string, goalId: string, answer: AnswerPayload) =>
    http.post<AttemptResponse>(
      `/knowledge-points/exercises/${exerciseId}/attempt`,
      { answer },
      { goal_id: goalId },
    ),

  explain: (taskId: string, explanation: string) =>
    http.post<ExplanationResponse>(`/tasks/${taskId}/explanation`, { explanation }),
}
