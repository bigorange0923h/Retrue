/** 统一 AI 助理任务 API。
 *
 * 任务用于保存康复师尚未完成的工作进度，例如训练补记的原始描述、草稿和
 * 等待确认状态。正式业务数据仍只由原有确认接口写入。
 */

import { request } from './http'
import type { AssistantCustomerMatch, AssistantTask, AssistantTaskStatus, AssistantTaskType, PageData } from '@/types/api'

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
