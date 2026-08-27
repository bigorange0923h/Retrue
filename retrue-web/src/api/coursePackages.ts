/** 课时包 API 模块。 */

import { request } from './http'
import type { CoursePackage } from '@/types/api'

/** 查询某客户课时包。 */
export function apiListCoursePackages(customerId: number): Promise<CoursePackage[]> {
  return request<CoursePackage[]>({ method: 'GET', url: '/courses/packages/', params: { customer_id: customerId } })
}

/** 创建课时包。 */
export function apiCreateCoursePackage(data: { customer: number; name?: string; total_sessions: number; note?: string }): Promise<CoursePackage> {
  return request<CoursePackage>({ method: 'POST', url: '/courses/packages/', data })
}

/** 人工调整课时。 */
export function apiAdjustCoursePackage(packageId: number, delta: number, reason: string): Promise<CoursePackage> {
  return request<CoursePackage>({ method: 'POST', url: `/courses/packages/${packageId}/adjust/`, data: { delta, reason } })
}
