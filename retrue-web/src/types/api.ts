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

/** 知识条目分类。 */
export type KnowledgeCategory = 'medical' | 'safety' | 'recovery' | 'preference' | 'other'

/** 客户长期记忆分类。 */
export type MemoryType =
  | 'preference'
  | 'dislike'
  | 'communication'
  | 'habit'
  | 'goal'
  | 'concern'
  | 'pattern'
  | 'background'
  | 'therapist_observation'
  | 'other'

/** 客户知识条目。 */
export interface KnowledgeItem {
  id: number
  category: KnowledgeCategory
  category_display: string
  memory_type: MemoryType
  memory_type_display: string
  memory_key: string
  content: string
  normalized_value: string
  source: string
  source_type: string
  source_id: string
  source_message_id: string
  importance: 'high' | 'normal'
  importance_display: string
  importance_score: number
  confidence: string
  is_active: boolean
  status: 'candidate' | 'active' | 'superseded' | 'expired' | 'deleted'
  status_display: string
  confirmed_by_user: boolean
  effective_from: string | null
  effective_to: string | null
  last_confirmed_at: string | null
  supersedes_memory: number | null
  created_at: string
  updated_at: string
}

/** 知识条目创建/更新载荷。 */
export interface KnowledgeItemPayload {
  customer: number
  content: string
  category: KnowledgeCategory
  importance?: 'high' | 'normal'
  memory_type?: MemoryType
  memory_key?: string
  importance_score?: number
  is_active?: boolean
}

/** AI 知识候选。 */
export interface KnowledgeCandidate {
  id: number
  content: string
  category: KnowledgeCategory
  category_display: string
  memory_type: MemoryType
  memory_type_display: string
  memory_key: string
  normalized_value: string
  confidence: string
  importance_score: number
  evidence: string
  conflict_type: 'none' | 'conflict' | 'conditional' | 'supplement'
  conflict_type_display: string
  conflict_memory: number | null
  conflict_memory_content: string | null
  source_conversation: number | null
  source_message: number | null
  source_ref: string
  resolution_action: string
  suggested_at: string
  status: 'pending' | 'confirmed' | 'rejected' | 'deferred'
  status_display: string
}

/** AI 会话入口与业务类型。 */
export type ConversationOrigin =
  | 'dashboard'
  | 'customer_detail'
  | 'lesson_preparation'
  | 'training_record'
  | 'assessment'
  | 'knowledge'
  | 'general'
export type ConversationType =
  | 'general'
  | 'customer_discussion'
  | 'preparation'
  | 'training'
  | 'assessment'
  | 'professional_question'

/** 一条已归档的 AI 消息。 */
export interface AiConversationMessage {
  id: number
  role: 'user' | 'assistant' | 'system' | 'tool'
  content: string
  metadata: Record<string, unknown>
  created_at: string
}

/** 一次连续 AI 会话。 */
export interface AiConversation {
  id: number
  customer: number | null
  origin: ConversationOrigin
  conversation_type: ConversationType
  context_resource_type: string
  context_resource_id: string
  title: string
  summary: string
  summarized_through_message_id: number | null
  summary_updated_at: string | null
  status: 'active' | 'ended'
  started_at: string
  ended_at: string | null
  created_at: string
  updated_at: string
  messages: AiConversationMessage[]
}

/** 发送一轮消息的返回结果。 */
export interface ConversationMessageResult {
  conversation_id: number
  user_message: AiConversationMessage
  assistant_message: AiConversationMessage
  memory_candidates: KnowledgeCandidate[]
}

/** 跨会话回顾的重要历史讨论事件。 */
export interface MemoryEpisode {
  id: number
  customer: number
  conversation: number | null
  episode_key: string
  title: string
  summary: string
  key_points: string[]
  decisions: string[]
  next_actions: string[]
  importance_score: number
  confidence: string
  status: 'candidate' | 'active' | 'rejected' | 'deleted'
  status_display: string
  source_start_message_id: number | null
  source_end_message_id: number | null
  decided_at: string | null
  created_at: string
  updated_at: string
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
  plan_course: number | null
  plan_course_name: string | null
  rehab_plan_name: string | null
  arrangement_type?: 'plan' | 'initial_assessment' | 'reassessment' | 'other'
  arrangement_type_display?: string
  session_topic: string
  session_count: number
  date: string
  start_time: string | null
  end_time: string | null
  status: 'scheduled' | 'completed' | 'cancelled' | 'absent'
  status_display: string
  session_consumed: boolean
  training_record_id: number | null
  note: string
}

/** 批量安排课程时的预览条目。日期与时间由康复师确认后才会写入课表。 */
export interface CourseSchedulePreviewItem {
  date: string
  start_time: string | null
  end_time: string | null
  session_topic: string
  session_count: number
}

/** 批量安排预览中的时间冲突。 */
export interface CourseScheduleConflict {
  date: string
  start_time: string | null
  end_time: string | null
  existing_session_id?: number
  message: string
}

/** 批量安排课程的预览结果。保留可选字段以兼容服务端返回的汇总信息。 */
export interface CourseSchedulePreview {
  items: CourseSchedulePreviewItem[]
  conflicts: Array<CourseScheduleConflict | string>
  total_count?: number
  scheduled_count?: number
  unscheduled_count?: number
}

/** 批量安排课程后的确认结果。 */
export interface CourseScheduleConfirmResult {
  created_count?: number
  items?: CourseSessionItem[]
  sessions?: CourseSessionItem[]
  conflicts?: Array<CourseScheduleConflict | string>
}

/** 课程类型。 */
export interface CourseType {
  id: number
  name: string
  description: string
  is_active: boolean
  default_duration: number | null
  default_session_cost: number
  default_goals: string
  status_display: string
  course_count: number
  created_at: string
}

/** 课程计划模板中的课程组成。 */
export interface RehabPlanTemplateCourse {
  id?: number
  course_type: number
  course_type_name?: string
  planned_count: number
  session_cost: number
  duration: number | null
  goals: string
  sort_order: number
}

/** 康复师维护的可复用课程计划模板。 */
export interface RehabPlanTemplate {
  id: number
  name: string
  description: string
  suggested_duration_weeks: number | null
  goals: string
  is_active: boolean
  status_display: string
  courses: RehabPlanTemplateCourse[]
  usage_count: number
  total_planned_count: number
  total_session_units: number
  created_at: string
  updated_at: string
}

/** 创建客户周期时预览和调整后的课程快照。 */
export interface RehabPlanCourseDraft {
  course_type: number
  package?: number | null
  planned_count: number
  session_cost: number
  duration: number | null
  goals: string
}

/** 计划内课程状态。 */
export type PlanCourseStatus = 'active' | 'paused' | 'completed' | 'cancelled'

/** 计划内课程次数调整。 */
export interface PlanCourseAdjustment {
  id: number
  delta_count: number
  before_count: number
  after_count: number
  reason: string
  assessment: number | null
  therapist_name: string
  created_at: string
}

/** 客户课程计划内的课程。 */
export interface RehabPlanCourse {
  id: number
  rehab_plan: number
  rehab_plan_name: string
  rehab_plan_status: 'active' | 'closed'
  customer: number
  customer_name: string
  course_type: number
  course_type_name: string
  package: number | null
  package_name: string | null
  status: PlanCourseStatus
  status_display: string
  goals: string
  planned_count: number
  completed_count: number
  remaining_count: number
  /** 待上课的有效排课数量。旧服务端未返回时前端回退到剩余次数。 */
  scheduled_count?: number
  /** 尚未安排到课表的次数。 */
  unscheduled_count?: number
  /** 已过期但仍待处理的排课数量。 */
  overdue_count?: number
  /** 下一节待上课安排。 */
  next_session?: CourseSessionItem | null
  session_cost: number
  duration: number | null
  adjustments: PlanCourseAdjustment[]
  created_at: string
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
  draft_type?: AiDraftType
  draft_type_display?: string
  status: AiDraftStatus
  status_display: string
  customer: number | null
  customer_name: string
  input_text: string
  ai_result: AiDraftResult
  confirmed_result: AiDraftResult | Record<string, never>
  assistant_task?: number | null
  training_record?: number | null
  assessment?: number | null
  followup?: number | null
  confirmation_key?: string
  error_message: string
  created_at: string
}

/** AI 草稿类型。 */
export type AiDraftType = 'training_record' | 'assessment' | 'training_revision' | 'followup'

/** 客户候选（脱敏手机号）。 */
export interface CustomerCandidate {
  id: number
  name: string
  phone_masked: string
}

/** 聊天中按姓名确认客户时使用的脱敏候选资料。 */
export interface AssistantCustomerMatch extends CustomerCandidate {
  gender: string
  status: string
  status_display: string
  main_issue: string
  first_visit_date: string | null
}

/** 康复阶段类型。 */
export type RehabStageType = 'acute' | 'recovery' | 'strength' | 'functional'

/** 康复阶段。 */
export interface RehabStage {
  id: number
  customer: number
  customer_name: string
  plan: number
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
  source_template: number | null
  source_template_name: string | null
  name: string
  start_date: string
  end_date: string | null
  status: 'active' | 'closed'
  status_display: string
  goals: string
  note: string
  stages: RehabStage[]
  course_count: number
  created_at: string
  updated_at: string
}

/** 评估指标类型。 */
export type MetricType = 'pain' | 'strength' | 'rom' | 'special_test' | 'functional'

/** 评估记录状态。草稿不会进入 AI 与趋势分析。 */
export type AssessmentStatus = 'draft' | 'completed'

/** 指标左右侧。 */
export type AssessmentSide = 'left' | 'right' | 'bilateral' | 'not_applicable' | ''

/** 指标测量场景。 */
export type AssessmentMetricContext = 'rest' | 'activity' | 'pre_training' | 'post_training' | 'night' | 'custom' | ''

/** ROM 测量方式。 */
export type AssessmentMeasurementMode = 'active' | 'passive' | ''

/** 指标定义中的分类选项。 */
export interface AssessmentMetricOption {
  value: string | number
  label: string
  description?: string
}

/** 由服务端统一维护的指标规则。 */
export interface AssessmentMetricDefinition {
  metric_type: MetricType
  /** 新版定义使用 name；label 为其他实现的兼容字段。 */
  label?: string
  name?: string
  code?: string
  description?: string
  result_type: 'numeric' | 'scale' | 'categorical'
  min?: number | null
  max?: number | null
  min_value?: number | null
  max_value?: number | null
  step?: number | null
  unit?: string
  score_direction?: 'lower_is_better' | 'higher_is_better' | 'neutral'
  scoring_direction?: 'lower_is_better' | 'higher_is_better' | 'neutral'
  required_fields?: string[]
  options?: AssessmentMetricOption[] | Record<string, AssessmentMetricOption[]>
}

/** 评估指标。 */
export interface AssessmentMetric {
  id?: number
  metric_type: MetricType
  metric_type_display?: string
  body_part: string
  score: number | null
  score_max: number | null
  description: string
  sort_order: number
  side?: AssessmentSide
  scale_code?: string
  unit?: string
  context?: AssessmentMetricContext
  movement?: string
  measurement_mode?: AssessmentMeasurementMode
  result_code?: string
  details?: Record<string, unknown>
}

/** 评估指标写入载荷。满分、单位和量表由服务端根据类型决定。
 * `id` 为可选：编辑已有指标时带上，服务端按 id 差异更新并保留原 id；新建不传。 */
export type AssessmentMetricInput = Omit<AssessmentMetric, 'metric_type_display' | 'score_max'> & {
  id?: number
  score_max?: never
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
  status?: AssessmentStatus
  status_display?: string
  completed_at?: string | null
  onset_date?: string | null
  onset_description?: string
  onset_mode?: 'injury' | 'sudden' | 'gradual' | 'postoperative' | 'other' | 'unknown' | ''
  chief_complaint: string
  medical_history: string
  aggravating_factors?: string
  relieving_factors?: string
  prior_care?: string
  surgery_history?: string
  medication?: string
  exercise_habits?: string
  work_demands?: string
  sleep_impact?: string
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

/** 课时流水。正值为补扣，负值为退还。 */
export interface CourseAdjustment {
  id: number
  adjustment_type: 'consumption' | 'manual'
  adjustment_type_display: string
  delta: number
  reason: string
  course_session: number | null
  course_session_topic: string | null
  therapist_name: string
  created_at: string
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
  adjustments: CourseAdjustment[]
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
  active_memories: Array<{
    type: string
    content: string
    importance: number
    source: 'MEMORY'
  }>
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

/** 统一助理任务的生命周期状态。任务只保存工作进度，不代表已经写入业务记录。 */
export type AssistantTaskStatus =
  | 'pending'
  | 'running'
  | 'waiting_user'
  | 'waiting_confirmation'
  | 'blocked'
  | 'completed'
  | 'failed'
  | 'cancelled'
  | 'expired'

/** 统一助理任务类型。保留 string 扩展，便于服务端增加新的业务任务。 */
export type AssistantTaskType = 'training_record' | 'conversation' | 'general' | (string & {})

/** 统一助理未完成任务。draft/input 等字段允许缺省，以兼容任务接口的渐进式返回。 */
export interface AssistantTask {
  id: number
  skill_code?: string
  task_type: AssistantTaskType
  invocation_mode?: string
  origin?: string
  context_resource_type?: string
  context_resource_id?: string
  business_key?: string
  client_request_id?: string
  status: AssistantTaskStatus
  status_display?: string
  customer?: number | null
  conversation?: number | null
  current_step?: string
  missing_fields?: string[]
  state_data?: Record<string, unknown> | null
  draft_resource_type?: string
  draft_resource_id?: string
  result_resource_type?: string
  result_resource_id?: string
  version?: number
  customer_name?: string
  is_resumable?: boolean
  runs?: Array<Record<string, unknown>>
  tool_executions?: Array<Record<string, unknown>>
  events?: Array<Record<string, unknown>>
  /** 便于页面读取状态数据中的训练补记上下文的兼容字段。 */
  input_text?: string
  draft_id?: number | null
  draft?: AiDraft | null
  error_message?: string
  blocked_reason?: string
  last_activity_at?: string
  expires_at?: string | null
  completed_at?: string | null
  cancelled_at?: string | null
  created_at?: string
  updated_at?: string
}
