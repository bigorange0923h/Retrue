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
