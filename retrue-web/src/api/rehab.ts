/** 康复计划与阶段 API 模块。 */

import { request } from './http'
import type { PlanCourseStatus, RehabPlan, RehabPlanCourse, RehabStage, RehabStageType } from '@/types/api'

/** 查询某客户康复计划。 */
export function apiListRehabPlans(customerId: number): Promise<RehabPlan[]> {
  return request<RehabPlan[]>({ method: 'GET', url: '/rehab/plans/', params: { customer_id: customerId } })
}

/** 创建康复计划。 */
export function apiCreateRehabPlan(data: { customer: number; start_date: string; end_date?: string | null; name?: string; goals?: string; note?: string }): Promise<RehabPlan> {
  return request<RehabPlan>({ method: 'POST', url: '/rehab/plans/', data })
}

/** 更新康复周期计划。 */
export function apiUpdateRehabPlan(id: number, data: Partial<RehabPlan>): Promise<RehabPlan> {
  return request<RehabPlan>({ method: 'PUT', url: `/rehab/plans/${id}/`, data })
}

/** 查询周期课程，可按周期或客户过滤。 */
export function apiListRehabPlanCourses(params: {
  plan_id?: number
  customer_id?: number
  status?: PlanCourseStatus
}): Promise<RehabPlanCourse[]> {
  return request<RehabPlanCourse[]>({ method: 'GET', url: '/rehab/plan-courses/', params })
}

/** 在康复周期内添加课程。 */
export function apiCreateRehabPlanCourse(data: Partial<RehabPlanCourse>): Promise<RehabPlanCourse> {
  return request<RehabPlanCourse>({ method: 'POST', url: '/rehab/plan-courses/', data })
}

/** 更新周期课程配置或状态。 */
export function apiUpdateRehabPlanCourse(id: number, data: Partial<RehabPlanCourse>): Promise<RehabPlanCourse> {
  return request<RehabPlanCourse>({ method: 'PUT', url: `/rehab/plan-courses/${id}/`, data })
}

/** 增减周期课程计划次数。 */
export function apiAdjustRehabPlanCourse(id: number, deltaCount: number, reason: string, assessment?: number | null): Promise<RehabPlanCourse> {
  return request<RehabPlanCourse>({
    method: 'POST',
    url: `/rehab/plan-courses/${id}/adjust/`,
    data: { delta_count: deltaCount, reason, assessment },
  })
}

/** 查询客户当前阶段。 */
export function apiGetCurrentStage(customerId: number): Promise<RehabStage | null> {
  return request<RehabStage | null>({ method: 'GET', url: '/rehab/stages/', params: { customer_id: customerId } })
}

/** 设置康复阶段。 */
export function apiSetStage(data: { customer: number; stage_type: RehabStageType; start_date: string; note?: string }): Promise<RehabStage> {
  return request<RehabStage>({ method: 'POST', url: '/rehab/stages/', data })
}
