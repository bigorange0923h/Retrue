/** 康复计划与阶段 API 模块。 */

import { request } from './http'
import type { RehabPlan, RehabStage, RehabStageType } from '@/types/api'

/** 查询某客户康复计划。 */
export function apiListRehabPlans(customerId: number): Promise<RehabPlan[]> {
  return request<RehabPlan[]>({ method: 'GET', url: '/rehab/plans/', params: { customer_id: customerId } })
}

/** 创建康复计划。 */
export function apiCreateRehabPlan(data: { customer: number; start_date: string; name?: string; note?: string }): Promise<RehabPlan> {
  return request<RehabPlan>({ method: 'POST', url: '/rehab/plans/', data })
}

/** 查询客户当前阶段。 */
export function apiGetCurrentStage(customerId: number): Promise<RehabStage | null> {
  return request<RehabStage | null>({ method: 'GET', url: '/rehab/stages/', params: { customer_id: customerId } })
}

/** 设置康复阶段。 */
export function apiSetStage(data: { customer: number; stage_type: RehabStageType; start_date: string; note?: string }): Promise<RehabStage> {
  return request<RehabStage>({ method: 'POST', url: '/rehab/stages/', data })
}
