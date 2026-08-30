/** 康复计划与阶段 API 模块。 */

import { request } from './http'
import type {
  PlanCourseStatus,
  RehabPlan,
  RehabPlanCourse,
  RehabPlanCourseDraft,
  RehabPlanTemplate,
  RehabStage,
  RehabStageType,
} from '@/types/api'

/** 查询当前康复师维护的课程计划模板。 */
export function apiListRehabPlanTemplates(params?: {
  keyword?: string
  active_only?: 0 | 1
}): Promise<RehabPlanTemplate[]> {
  return request<RehabPlanTemplate[]>({ method: 'GET', url: '/rehab/plan-templates/', params })
}

/** 创建课程计划模板及其课程组成。 */
export function apiCreateRehabPlanTemplate(
  data: Omit<RehabPlanTemplate, 'id' | 'status_display' | 'usage_count' | 'total_planned_count' | 'total_session_units' | 'created_at' | 'updated_at'>,
): Promise<RehabPlanTemplate> {
  return request<RehabPlanTemplate>({ method: 'POST', url: '/rehab/plan-templates/', data })
}

/** 更新课程计划模板；不会修改既有客户计划。 */
export function apiUpdateRehabPlanTemplate(
  id: number,
  data: Partial<RehabPlanTemplate>,
): Promise<RehabPlanTemplate> {
  return request<RehabPlanTemplate>({ method: 'PUT', url: `/rehab/plan-templates/${id}/`, data })
}

/** 查询某客户康复计划。 */
export function apiListRehabPlans(customerId: number): Promise<RehabPlan[]> {
  return request<RehabPlan[]>({ method: 'GET', url: '/rehab/plans/', params: { customer_id: customerId } })
}

/** 创建康复计划。 */
export function apiCreateRehabPlan(data: {
  customer: number
  source_template?: number | null
  start_date: string
  end_date?: string | null
  name?: string
  goals?: string
  note?: string
  courses?: RehabPlanCourseDraft[]
}): Promise<RehabPlan> {
  return request<RehabPlan>({ method: 'POST', url: '/rehab/plans/', data })
}

/** 更新客户课程计划。 */
export function apiUpdateRehabPlan(id: number, data: Partial<RehabPlan>): Promise<RehabPlan> {
  return request<RehabPlan>({ method: 'PUT', url: `/rehab/plans/${id}/`, data })
}

/** 查询计划内课程，可按计划或客户过滤。 */
export function apiListRehabPlanCourses(params: {
  plan_id?: number
  customer_id?: number
  status?: PlanCourseStatus
}): Promise<RehabPlanCourse[]> {
  return request<RehabPlanCourse[]>({ method: 'GET', url: '/rehab/plan-courses/', params })
}

/** 在客户课程计划内添加课程。 */
export function apiCreateRehabPlanCourse(data: Partial<RehabPlanCourse>): Promise<RehabPlanCourse> {
  return request<RehabPlanCourse>({ method: 'POST', url: '/rehab/plan-courses/', data })
}

/** 更新计划内课程配置或状态。 */
export function apiUpdateRehabPlanCourse(id: number, data: Partial<RehabPlanCourse>): Promise<RehabPlanCourse> {
  return request<RehabPlanCourse>({ method: 'PUT', url: `/rehab/plan-courses/${id}/`, data })
}

/** 增减计划内课程的计划次数。 */
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
