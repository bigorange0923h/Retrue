/** 后端统一响应信封结构。 */

/** 业务状态码常量。 */
export const ApiCode = {
  SUCCESS: 200,
  BAD_REQUEST: 400,
  UNAUTHORIZED: 401,
  FORBIDDEN: 403,
  NOT_FOUND: 404,
  SERVER_ERROR: 500,
} as const

/** 统一响应外层结构。 */
export interface ApiResponse<T = unknown> {
  code: number
  message: string
  data: T
}

/** 分页数据外层结构。 */
export interface PageData<T> {
  items: T[]
  page: number
  page_size: number
  total: number
}

/** 当前登录用户信息。 */
export interface CurrentUser {
  id: number
  username: string
  display_name: string
  therapist_id: number | null
  is_superuser: boolean
  is_active: boolean
  is_staff: boolean
}

/** 账号管理：用户列表项。 */
export interface UserAccountItem {
  id: number
  username: string
  display_name: string
  is_active: boolean
  is_staff: boolean
  is_superuser: boolean
  last_login: string | null
  date_joined: string
}

/** 账号管理：创建表单。 */
export interface UserCreateForm {
  username: string
  password: string
  is_active: boolean
  is_staff: boolean
  is_superuser: boolean
}

/** 账号管理：更新表单（password 可选，留空则不修改）。 */
export interface UserUpdateForm {
  is_active?: boolean
  is_staff?: boolean
  is_superuser?: boolean
  password?: string
}

/** 审计日志条目。 */
export interface AuditLogItem {
  id: number
  action: string
  action_display: string
  actor_name: string
  before_data: Record<string, unknown>
  after_data: Record<string, unknown>
  reason: string
  created_at: string
}

/** 客户状态。 */
export type CustomerStatus = 'active' | 'paused' | 'closed'

/** 客户列表项（脱敏手机号）。 */
export interface CustomerListItem {
  id: number
  name: string
  phone_masked: string
  gender: 'male' | 'female' | ''
  gender_display: string
  main_issue: string
  status: CustomerStatus
  status_display: string
  first_visit_date: string | null
  created_at: string
  updated_at: string
}

/** 客户详情（含完整手机号，供资料编辑）。 */
export interface CustomerDetail extends CustomerListItem {
  phone: string
  birth_date: string | null
  occupation: string
  sport: string
  injury_date: string | null
  surgery_date: string | null
  note: string
}

/** 课程条目。 */
export interface CourseSessionItem {
  id: number
  customer: number
  customer_name: string
  customer_phone_masked: string
  course_name: string
  date: string
  start_time: string | null
  end_time: string | null
  status: 'scheduled' | 'completed' | 'cancelled' | 'absent'
  status_display: string
  note: string
}

/** 训练动作明细。 */
export interface TrainingExercise {
  id?: number
  exercise_name: string
  sets: number | null
  reps: number | null
  weight: string
  duration_seconds: number | null
  note: string
  sort_order: number
}

/** 训练记录。 */
export interface TrainingRecord {
  id: number
  customer: number
  customer_name: string
  course_session: number | null
  training_date: string
  customer_feedback: string
  therapist_observation: string
  next_plan: string
  note: string
  exercises: TrainingExercise[]
  created_at: string
  updated_at: string
}

/** AI 草稿状态。 */
export type AiDraftStatus = 'pending' | 'confirmed' | 'cancelled' | 'failed'

/** AI 解析出的训练草稿结果。 */
export interface AiDraftResult {
  training_date: string
  customer_hint: string | null
  exercises: TrainingExercise[]
  customer_feedback: string
  therapist_observation: string
  next_plan: string
}

/** AI 草稿。 */
export interface AiDraft {
  id: number
  status: AiDraftStatus
  status_display: string
  customer: number | null
  customer_name: string
  input_text: string
  ai_result: AiDraftResult
  confirmed_result: AiDraftResult | Record<string, never>
  error_message: string
  created_at: string
}

/** 客户候选（脱敏手机号）。 */
export interface CustomerCandidate {
  id: number
  name: string
  phone_masked: string
}

/** 康复阶段类型。 */
export type RehabStageType = 'acute' | 'recovery' | 'strength' | 'functional'

/** 康复阶段。 */
export interface RehabStage {
  id: number
  customer: number
  plan: number | null
  stage_type: RehabStageType
  stage_type_display: string
  start_date: string
  end_date: string | null
  note: string
}

/** 康复计划。 */
export interface RehabPlan {
  id: number
  customer: number
  customer_name: string
  name: string
  start_date: string
  status: 'active' | 'closed'
  status_display: string
  note: string
  stages: RehabStage[]
  created_at: string
  updated_at: string
}

/** 评估指标类型。 */
export type MetricType = 'pain' | 'strength' | 'rom' | 'special_test' | 'functional'

/** 评估指标。 */
export interface AssessmentMetric {
  id?: number
  metric_type: MetricType
  metric_type_display: string
  body_part: string
  score: number | null
  score_max: number | null
  description: string
  sort_order: number
}

/** 评估记录。 */
export interface Assessment {
  id: number
  customer: number
  customer_name: string
  plan: number | null
  assessment_type: 'initial' | 'reassessment'
  assessment_type_display: string
  assessment_date: string
  chief_complaint: string
  medical_history: string
  rehab_goal: string
  current_status: string
  note: string
  metrics: AssessmentMetric[]
  created_at: string
  updated_at: string
}

/** 回访/复查类型与状态。 */
export type FollowUpType = 'visit' | 'review' | 'other'
export type FollowUpStatus = 'pending' | 'done' | 'skipped'

/** 回访/复查待办。 */
export interface FollowUpTask {
  id: number
  customer: number
  customer_name: string
  followup_type: FollowUpType
  followup_type_display: string
  due_date: string
  content: string
  status: FollowUpStatus
  status_display: string
  result: string
  created_at: string
  updated_at: string
}

/** 家庭训练动作。 */
export interface HomeTrainingExercise {
  id?: number
  exercise_name: string
  sets: number | null
  reps: number | null
  duration_seconds: number | null
  frequency: string
  note: string
  sort_order: number
}

/** 家庭训练计划。 */
export interface HomeTrainingPlan {
  id: number
  customer: number
  customer_name: string
  title: string
  frequency: string
  note: string
  exercises: HomeTrainingExercise[]
  created_at: string
  updated_at: string
}

/** 课时包。 */
export interface CoursePackage {
  id: number
  customer: number
  customer_name: string
  name: string
  total_sessions: number
  used_sessions: number
  remaining_sessions: number
  note: string
  created_at: string
  updated_at: string
}

/** 备课助手：客户历史汇总。 */
export interface LessonSummary {
  last_record_date: string | null
  last_exercises: string[]
  customer_feedback: string
  therapist_observation: string
  next_plan: string
  current_stage: string
  note: string
}

/** 备课助手：AI 建议。 */
export interface LessonSuggestions {
  suggested_checks: string[]
  recommended_tests: string[]
  recommended_parts: string[]
  training_approach: string
  risk_reminders: string[]
}

/** 备课助手完整结果。 */
export interface LessonPreparation {
  customer_summary: LessonSummary
  ai_suggestions: LessonSuggestions
}

/** 风险等级与建议动作。 */
export type RiskLevel = 'low' | 'medium' | 'high'
export type RiskAction = 'pause' | 'review' | 'check' | 'refer'

/** 风险提醒。 */
export interface RiskAlert {
  id: number
  customer: number
  customer_name: string
  training_record: number | null
  risk_level: RiskLevel
  risk_level_display: string
  evidence: string
  suggested_action: RiskAction
  suggested_action_display: string
  is_confirmed: boolean
  outcome: string
  created_at: string
}

/** 阶段进展参考。 */
export interface ProgressAnalysis {
  pain_trend: '改善' | '加重' | '平稳' | null
  observations: string[]
  summary: string
  recommendation: string
}

/** AI 专业问答结果。 */
export interface AiQaResponse {
  question: string
  answer: string
  sources: Array<{
    name: string
    body_part: string
    description: string
    precautions: string
  }>
}
