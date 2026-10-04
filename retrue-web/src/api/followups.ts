/** 回访/复查 API 模块。 */

import { request } from './http'
import type { FollowUpStatus, FollowUpTask, FollowUpType } from '@/types/api'

/** 回访查询参数。 */
export interface FollowUpQuery {
  customer_id?: number
  status?: string
}

/** 回访创建/更新表单。 */
export interface FollowUpForm {
  customer?: number
  followup_type?: FollowUpType
  due_date: string
  content?: string
  status?: FollowUpStatus
  result?: string
  /** 仅完成时显式安排下一项，由后端同事务创建。 */
  next_task?: { followup_type: FollowUpType; due_date: string; content: string }
}

/** 查询回访列表。 */
export function apiListFollowUps(params: FollowUpQuery): Promise<FollowUpTask[]> {
  return request<FollowUpTask[]>({ method: 'GET', url: '/followups/', params })
}

/** 创建回访。 */
export function apiCreateFollowUp(data: FollowUpForm): Promise<FollowUpTask> {
  return request<FollowUpTask>({ method: 'POST', url: '/followups/', data })
}

/** 更新回访。 */
export function apiUpdateFollowUp(id: number, data: FollowUpForm): Promise<FollowUpTask> {
  return request<FollowUpTask>({ method: 'PUT', url: `/followups/${id}/`, data })
}
