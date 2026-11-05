/**
 * Typed view of the DoKnow backend API contract.
 * Shapes mirror the service-layer dicts (verified against the services).
 */

// ---------- Auth / user ----------

export interface User {
  id: string
  email: string
  display_name: string | null
  avatar_url: string | null
}

export interface UserProfile {
  user_id: string
  learning_style: string | null
  preferred_method: string | null
  daily_time_budget_minutes: number | null
  weekly_target_hours: number | null
  timezone: string | null
}

export interface RegisterRequest {
  email: string
  password: string
  display_name?: string
}

export interface LoginRequest {
  email: string
  password: string
}

export interface AuthResponse {
  user_id: string
  token: string
  expires_at?: string
  user: User
}

export interface MeResponse {
  user: User
  profile: UserProfile
}

export interface ProfileUpdate {
  learning_style?: string | null
  preferred_method?: string | null
  daily_time_budget_minutes?: number | null
  weekly_target_hours?: number | null
  timezone?: string | null
}

// ---------- Goal ----------

export type GoalStatus = 'DRAFT' | 'ACTIVE' | 'PAUSED' | 'COMPLETED' | 'ARCHIVED'

export interface Goal {
  id: string
  user_id: string
  title: string
  description: string | null
  target_level: string | null
  deadline: string | null // isoformat
  status: GoalStatus
  priority: number
  success_criteria: Record<string, unknown> | null
  progress: number // 0..1
  meta: Record<string, unknown>
  started_at: string | null
  completed_at: string | null
  created_at: string
}

export interface GoalCreate {
  title: string
  description?: string
  target_level?: string
  deadline?: string
  success_criteria?: Record<string, unknown>
  priority?: number
}

export interface GoalUpdate {
  title?: string
  description?: string
  target_level?: string
  deadline?: string
  success_criteria?: Record<string, unknown>
  priority?: number
  status?: GoalStatus
}

export interface GoalActivateResponse {
  ok: boolean
  goal: Goal
}

export interface GoalCreateResponse {
  id: string
  goal: Goal
}

// ---------- Knowledge system ----------

export type KnowledgeType = 'CONCEPT' | 'FACT' | 'PROCEDURE' | 'PRINCIPLE' | 'SKILL'
export type Difficulty = 'BEGINNER' | 'INTERMEDIATE' | 'ADVANCED'
export type Method = 'STUDY' | 'PRACTICE' | 'APPLY' | 'EXPLAIN' | 'REVIEW'
export type MasteryState =
  | 'NOT_STARTED'
  | 'IN_PROGRESS'
  | 'COMPLETED'
  | 'REVIEW_REQUIRED'
  | 'MASTERED'

export interface KnowledgePoint {
  id: string
  code: string
  name: string
  description: string | null
  knowledge_type: KnowledgeType
  difficulty: Difficulty
  recommended_methods: Method[]
  tags: string[]
  est_minutes: number
  prerequisites: string[] // source `code`s
}

export interface PointBrief {
  id: string
  code: string
  name: string
  knowledge_type: KnowledgeType | null
  difficulty: Difficulty | null
  est_minutes: number
}

export interface PathNodeMastery {
  mastery_state: MasteryState | null
  score: number | null
  confidence: number | null
}

export interface PathNode {
  order: number
  sequence: string
  est_minutes: number
  reason: string | null
  knowledge_point: PointBrief | null
  mastery: PathNodeMastery | null
}

export interface LearningPath {
  id: string
  goal_id: string
  title: string
  description: string | null
  total_est_minutes: number
  nodes: PathNode[]
}

// ---------- Curriculum ----------

export interface CourseSummary {
  id: string
  title: string
  description: string | null
  status: string | null
  total_est_minutes: number
  published_at: string | null
}

export interface Lesson {
  id: string
  order_index: number
  title: string
  summary: string
  format: string
  body: string | null
  knowledge_point_id: string | null
  est_minutes: number | null
}

export interface CourseDetail {
  id: string
  goal_id: string
  title: string
  description: string | null
  status: string | null
  active_version_id: string | null
  total_est_minutes: number
  lessons: Lesson[]
}

export interface OverviewResponse {
  goal: Goal
  knowledge_system_built: boolean
  knowledge_points: KnowledgePoint[]
  path: LearningPath | null
  courses: CourseSummary[]
}

// ---------- Tasks & reviews ----------

export type TaskType = 'STUDY' | 'PRACTICE' | 'EXPLAIN'
export type TaskStatus = 'NOT_STARTED' | 'IN_PROGRESS' | 'COMPLETED' | 'SKIPPED' | 'EXPIRED'

export interface Task {
  id: string
  goal_id: string
  course_id: string | null
  knowledge_point_id: string | null
  task_type: TaskType | null
  status: TaskStatus
  title: string
  instructions: string
  due_at: string | null
  scheduled_for: string | null
  started_at: string | null
  completed_at: string | null
  est_minutes: number | null
  meta: Record<string, unknown>
}

export type ReviewStatus = 'PENDING' | 'DUE' | 'COMPLETED' | 'SKIPPED'

export interface ReviewSchedule {
  intervals: number[]
  index: number
}

export interface Review {
  id: string
  knowledge_point_id: string
  review_type: 'SPACED' | 'WEAKNESS'
  status: ReviewStatus
  due_at: string | null
  interval_days: number | null
  schedule: ReviewSchedule
  completed_at: string | null
}

export interface ReviewCompleteRequest {
  score: number // 0..1
}

export interface ReviewCompleteResponse {
  id: string
  already_completed?: boolean
  status?: string
  score?: number
  next_due_at?: string | null
  message?: string
  [key: string]: unknown
}

export interface ReviewSkipResponse {
  ok: boolean
}

// ---------- Practice / exercises ----------

export interface Exercise {
  id: string
  knowledge_point_id: string
  question_type: string | null
  prompt: string
  options: string[]
  difficulty: Difficulty
  has_answer: boolean
  // only present via get_exercise_full (after grading):
  answer?: string
  explanation?: string
}

/**
 * `answer` is a free-form dict: objective grading reads `choice|answer|value`,
 * subjective answers keep the whole payload for the AI grader.
 */
export interface AnswerPayload {
  choice?: string
  answer?: string
  value?: string
  text?: string
  [key: string]: unknown
}

export interface AttemptResponse {
  attempt_id: string
  is_correct: boolean | null
  score: number | null // 1.0/0.0 graded; None pending
  status: 'graded' | 'pending_grading'
}

export interface ExerciseGenerateRequest {
  requirement?: string
  count?: number
}

export interface ExerciseGenerateResponse {
  status: string
  exercises: Exercise[]
}

// ---------- Explain (讲) ----------

export interface ExplanationRequest {
  explanation: string
}

/** assess_explanation workflow output (opaque assessment dict). */
export type ExplanationResponse = Record<string, unknown>

// ---------- Sources ----------

export type SourceType = 'PDF' | 'DOCX' | 'PPTX' | 'MARKDOWN' | 'HTML'
export type SourceStatus = 'UPLOADED' | 'PARSING' | 'PARSED' | 'FAILED'

export interface Source {
  id: string
  filename: string
  source_type: SourceType | null
  status: SourceStatus
  parser_backend: string | null
  size_bytes: number
  error: { type: string; message: string } | null
  excerpt: string
  created_at: string | null
}

// ---------- Manager / intervention ----------

export interface ManagerMessage {
  message: string
  action: string | null
  problem_type: string | null
  at: string
}

export interface PlanProposal {
  proposal: Record<string, unknown>
  reason: string
  proposed_at: string
}

export interface PlanAdjustDecision {
  accept: boolean
}

export interface PlanAdjustConfirmResponse {
  accepted: boolean
  replanning: boolean
  proposal: PlanProposal | null
}

// ---------- Dashboard ----------

export interface DashboardProgress {
  goal_progress: number
  points_total: number
  mastered: number
  review_required: number
  path_nodes: number
}

export interface DashboardResponse {
  user: User
  profile: UserProfile
  goal: Goal | null
  today_tasks: Task[]
  due_reviews: Review[]
  manager_messages: ManagerMessage[]
  plan_proposal: PlanProposal | null
  progress: DashboardProgress | null
}

// ---------- Mastery snapshot ----------

export interface MasteryRecord {
  mastery_state: MasteryState | null
  score: number
  confidence: number
  last_assessed_at: string | null
}

export interface OkResponse {
  ok: boolean
}
