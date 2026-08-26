/** 评估 API 模块。 */

import { request } from './http'
import type { Assessment, AssessmentMetric } from '@/types/api'

/** 评估创建/更新表单。 */
export interface AssessmentForm {
  customer: number
  plan?: number | null
  assessment_type: 'initial' | 'reassessment'
  assessment_date: string
  chief_complaint?: string
  medical_history?: string
  rehab_goal?: string
  current_status?: string
  note?: string
  metrics: AssessmentMetric[]
}

/** 查询某客户评估列表。 */
export function apiListAssessments(customerId: number): Promise<Assessment[]> {
  return request<Assessment[]>({ method: 'GET', url: '/assessments/', params: { customer_id: customerId } })
}

/** 获取评估详情。 */
export function apiGetAssessment(id: number): Promise<Assessment> {
  return request<Assessment>({ method: 'GET', url: `/assessments/${id}/` })
}

/** 创建评估。 */
export function apiCreateAssessment(data: AssessmentForm): Promise<Assessment> {
  return request<Assessment>({ method: 'POST', url: '/assessments/', data })
}

/** 更新评估。 */
export function apiUpdateAssessment(id: number, data: AssessmentForm): Promise<Assessment> {
  return request<Assessment>({ method: 'PUT', url: `/assessments/${id}/`, data })
}
