/** 统一 AI 助理任务 API。
 *
 * 任务用于保存康复师尚未完成的工作进度，例如训练补记的原始描述、草稿和
 * 等待确认状态。正式业务数据仍只由原有确认接口写入。
 */

import { request } from './http'
import type { AiDraftResult, AssistantCustomerMatch, AssistantTask, AssistantTaskStatus, AssistantTaskType, PageData } from '@/types/api'

/** 卡片允许的操作。 */
export type AssistantCardAction =
  | 'select_customer'
  | 'cancel'
  | 'edit'
  | 'confirm'
  | 'retry'
  | 'supplement'
  | 'continue'
  | 'dismiss'
  | 'view_recent_training'
  | 'view_schedule'
  | 'start_record'
  | 'start_assessment'

/** 聊天内业务卡片。 */
export interface AssistantCard {
  id: string
  type: 'customer_selection' | 'customer_summary' | 'training_draft' | 'assessment_draft' | 'domain_draft' | 'risk_review' | 'batch_overview' | 'batch_draft' | 'batch_summary'
  status: AssistantTaskStatus | 'pending' | 'processing' | 'waiting_user' | 'waiting_confirmation' | 'completed' | 'cancelled' | 'blocked'
  resource_refs?: Record<string, number | string | null>
  customer_candidates?: AssistantCustomerMatch[]
  notice?: string
  summary?: Record<string, unknown>
  batch_summary?: BatchSummary
  allowed_actions?: AssistantCardAction[]
}

/** 客户信息摘要卡片数据。 */
export interface CustomerSummary {
  customer_id?: number | null
  name?: string
  phone_masked?: string
  gender_display?: string
  main_issue?: string
  recent_training_count?: number
  initial_assessment?: { exists: boolean; status_display: string }
  active_plan?: { name: string; goals: string } | null
  current_stage?: { stage_type_display: string } | null
}

/** 统一回合编排的响应结构。 */
export interface AssistantTurnResult {
  task_id: number
  status: AssistantTaskStatus
  current_step?: string
  missing_fields?: string[]
  customer_id?: number | null
  intent?: string
  resource_refs?: Record<string, number | string | null>
  customer_candidates?: AssistantCustomerMatch[]
  needs_confirmation?: boolean
  reply_content?: string
  assistant_message_id?: number | null
  risk_notice?: string
  cards?: AssistantCard[]
}

/** 创建助理任务时可保存的入口上下文。 */
export interface AssistantTaskCreatePayload {
  task_type: AssistantTaskType
  skill_code?: string
  invocation_mode?: string
  origin?: string
  context_resource_type?: string
  context_resource_id?: string
  business_key?: string
  client_request_id?: string
  customer?: number | null
  conversation?: number | null
  current_step?: string
  missing_fields?: string[]
  state_data?: Record<string, unknown>
  draft_resource_type?: string
  draft_resource_id?: string
  result_resource_type?: string
  result_resource_id?: string
}

/** 更新助理任务进度或执行任务操作。 */
export interface AssistantTaskUpdatePayload {
  version?: number
  current_step?: string
  missing_fields?: string[]
  state_data?: Record<string, unknown>
  customer?: number | null
  conversation?: number | null
}

type AssistantTaskListResponse = AssistantTask[] | PageData<AssistantTask> | { items?: AssistantTask[]; tasks?: AssistantTask[] }

/** 统一助理任务列表筛选条件。 */
export interface AssistantTaskQuery {
  customer?: number
  status?: AssistantTaskStatus | AssistantTaskStatus[]
  resumable?: boolean
}

/** 从服务端列表响应中提取任务数组，兼容分页和直接数组两种返回。 */
function normalizeTasks(result: AssistantTaskListResponse): AssistantTask[] {
  if (Array.isArray(result)) return result
  if (Array.isArray(result.items)) return result.items
  if ('tasks' in result && Array.isArray(result.tasks)) return result.tasks
  return []
}

/** 查询当前康复师的助理任务。服务端默认返回未完成任务。 */
export async function apiListAssistantTasks(params?: AssistantTaskQuery): Promise<AssistantTask[]> {
  const result = await request<AssistantTaskListResponse>({
    method: 'GET',
    url: '/assistant/tasks/',
    params: params
      ? {
          ...params,
          status: Array.isArray(params.status) ? params.status.join(',') : params.status,
        }
      : undefined,
  })
  return normalizeTasks(result)
}

/** 创建一条可恢复的助理任务。 */
export function apiCreateAssistantTask(data: AssistantTaskCreatePayload): Promise<AssistantTask> {
  return request<AssistantTask>({ method: 'POST', url: '/assistant/tasks/', data })
}

/** 获取一条任务的最新状态，用于继续时恢复服务端保存的上下文。 */
export function apiGetAssistantTask(id: number): Promise<AssistantTask> {
  return request<AssistantTask>({ method: 'GET', url: `/assistant/tasks/${id}/` })
}

/** 保存助理任务的可恢复进度或上下文；生命周期状态由服务端流程负责变更。 */
export function apiUpdateAssistantTask(id: number, data: AssistantTaskUpdatePayload): Promise<AssistantTask> {
  return request<AssistantTask>({ method: 'PATCH', url: `/assistant/tasks/${id}/`, data })
}

/** 获取一条任务的最新状态，继续操作由页面加载其状态，不伪造生命周期状态。 */
export function apiResumeAssistantTask(id: number): Promise<AssistantTask> {
  return apiGetAssistantTask(id)
}

/** 放弃任务；放弃只取消任务，不会删除已经存在的业务记录。 */
export function apiCancelAssistantTask(id: number, reason?: string): Promise<AssistantTask> {
  return request<AssistantTask>({
    method: 'POST',
    url: `/assistant/tasks/${id}/cancel/`,
    data: reason ? { reason } : undefined,
  })
}

/** 按精确姓名查询当前康复师名下客户；可能返回多个同名候选。 */
export function apiLookupAssistantCustomers(name: string): Promise<AssistantCustomerMatch[]> {
  return request<AssistantCustomerMatch[]>({
    method: 'GET',
    url: '/assistant/customers/by-name/',
    params: { name },
  })
}

/** 发起一轮统一回合对话。 */
export interface AssistantTurnPayload {
  message: string
  conversation_id?: number | null
  customer_id?: number | null
  customer_name?: string
  client_request_id?: string
}

export function apiSendAssistantTurn(data: AssistantTurnPayload): Promise<AssistantTurnResult> {
  return request<AssistantTurnResult>({ method: 'POST', url: '/assistant/turns/', data })
}

/** 恢复未完成任务，从服务端保存的暂停节点继续。 */
export function apiResumeAssistantTurn(taskId: number, message?: string): Promise<AssistantTurnResult> {
  return request<AssistantTurnResult>({
    method: 'POST',
    url: `/assistant/tasks/${taskId}/resume/`,
    data: message ? { message } : undefined,
  })
}

/** 提交同名客户选择，服务端校验归属后从中断节点继续。 */
export function apiSelectAssistantCustomer(taskId: number, customerId: number): Promise<AssistantTurnResult> {
  return request<AssistantTurnResult>({
    method: 'POST',
    url: `/assistant/tasks/${taskId}/customer-selection/`,
    data: { customer_id: customerId },
  })
}

/** 批量训练补记子项状态。 */
export type BatchItemStatus =
  | 'pending'
  | 'searching_customer'
  | 'waiting_customer'
  | 'waiting_draft'
  | 'saving'
  | 'completed'
  | 'skipped'
  | 'failed'
  | 'cancelled'

/** 批量训练补记子项。 */
export interface BatchItem {
  id: number
  sequence: number
  customer_name_hint: string
  customer_id: number | null
  customer_name: string
  status: BatchItemStatus
  draft_id: number | null
  training_record_id: number | null
}

/** 批量任务概览。 */
export interface BatchState {
  task_id: number
  status: AssistantTaskStatus
  current_step?: string
  total_items: number
  current_item_id: number | null
  items: BatchItem[]
}

/** 批量补记处理汇总。 */
export interface BatchSummary {
  task_id: number
  total_items: number
  succeeded: number
  skipped: number
  failed: number
  lines: Array<{ sequence: number; customer_name: string; status: string; training_record_id: number | null }>
}

/** 查询批量任务概览。 */
export function apiGetBatchState(taskId: number): Promise<BatchState> {
  return request<BatchState>({ method: 'GET', url: `/assistant/tasks/${taskId}/batch/` })
}

/** 子项客户搜索。 */
export function apiSearchBatchItemCustomer(taskId: number, itemId: number): Promise<{ candidates: AssistantCustomerMatch[] }> {
  return request<{ candidates: AssistantCustomerMatch[] }>({
    method: 'POST',
    url: `/assistant/tasks/${taskId}/items/${itemId}/customer-search/`,
    data: {},
  })
}

/** 子项客户确认结果。 */
export interface BatchItemCustomerSelectionResult {
  item_id: number
  status: string
  draft_id: number | null
  customer_id: number | null
  customer_name: string
  ai_result: AiDraftResult | null
}

/** 子项客户确认。 */
export function apiSelectBatchItemCustomer(taskId: number, itemId: number, customerId: number): Promise<BatchItemCustomerSelectionResult> {
  return request<BatchItemCustomerSelectionResult>({
    method: 'POST',
    url: `/assistant/tasks/${taskId}/items/${itemId}/customer-selection/`,
    data: { customer_id: customerId },
  })
}

/** 子项草稿保存。 */
export function apiSaveBatchItemDraft(taskId: number, itemId: number, confirmed: Record<string, unknown>): Promise<{ draft_id: number; ai_result: Record<string, unknown> }> {
  return request<{ draft_id: number; ai_result: Record<string, unknown> }>({
    method: 'PATCH',
    url: `/assistant/tasks/${taskId}/items/${itemId}/draft/`,
    data: confirmed,
  })
}

/** 子项正式确认。 */
export function apiConfirmBatchItem(taskId: number, itemId: number, confirmed: Record<string, unknown>, idempotencyKey?: string): Promise<{ item_id: number; status: string; training_record_id: number | null; summary: BatchSummary }> {
  return request<{ item_id: number; status: string; training_record_id: number | null; summary: BatchSummary }>({
    method: 'POST',
    url: `/assistant/tasks/${taskId}/items/${itemId}/confirm/`,
    data: { confirmed, idempotency_key: idempotencyKey },
  })
}

/** 子项跳过。 */
export function apiSkipBatchItem(taskId: number, itemId: number): Promise<{ item_id: number; status: string; summary: BatchSummary }> {
  return request<{ item_id: number; status: string; summary: BatchSummary }>({
    method: 'POST',
    url: `/assistant/tasks/${taskId}/items/${itemId}/skip/`,
    data: {},
  })
}
