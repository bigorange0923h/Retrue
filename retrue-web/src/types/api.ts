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
