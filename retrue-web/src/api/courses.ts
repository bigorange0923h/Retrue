/** 课程/日程/疗程 API 模块。 */

import { request } from './http'
import type { CourseSessionItem, CourseType, CustomerCourse } from '@/types/api'

/** 查询今日课程。 */
export function apiGetTodayCourses(date?: string): Promise<CourseSessionItem[]> {
  return request<CourseSessionItem[]>({
    method: 'GET',
    url: '/courses/today/',
    params: date ? { date } : undefined,
  })
}

/** 查询指定日期范围内的课程，用于课表日历。 */
export function apiGetCalendarCourses(start: string, end: string): Promise<CourseSessionItem[]> {
  return request<CourseSessionItem[]>({
    method: 'GET',
    url: '/courses/calendar/',
    params: { start, end },
  })
}

/** 课程创建/更新载荷。 */
export interface CoursePayload {
  customer: number
  customer_course?: number | null
  session_topic?: string
  session_count?: number
  date?: string
  start_time?: string | null
  end_time?: string | null
  status?: string
  note?: string
}

/** 创建课程。 */
export function apiCreateCourse(data: CoursePayload): Promise<CourseSessionItem> {
  return request<CourseSessionItem>({ method: 'POST', url: '/courses/', data })
}

/** 更新已有课程的安排或状态。 */
export function apiUpdateCourse(id: number, data: Partial<CoursePayload>): Promise<CourseSessionItem> {
  return request<CourseSessionItem>({ method: 'PUT', url: `/courses/${id}/`, data })
}

/** 查询课程类型列表。 */
export function apiListCourseTypes(keyword?: string): Promise<CourseType[]> {
  return request<CourseType[]>({
    method: 'GET',
    url: '/courses/course-types/',
    params: keyword ? { keyword } : undefined,
  })
}

/** 创建课程类型。 */
export function apiCreateCourseType(data: Partial<CourseType>): Promise<CourseType> {
  return request<CourseType>({ method: 'POST', url: '/courses/course-types/', data })
}

/** 更新课程类型。 */
export function apiUpdateCourseType(id: number, data: Partial<CourseType>): Promise<CourseType> {
  return request<CourseType>({ method: 'PUT', url: `/courses/course-types/${id}/`, data })
}

/** 查询客户疗程列表，可按客户或状态筛选。 */
export function apiListCustomerCourses(params?: {
  customer?: number
  status?: string
}): Promise<CustomerCourse[]> {
  return request<CustomerCourse[]>({
    method: 'GET',
    url: '/courses/customer-courses/',
    params,
  })
}

/** 创建客户疗程。 */
export function apiCreateCustomerCourse(data: Partial<CustomerCourse>): Promise<CustomerCourse> {
  return request<CustomerCourse>({ method: 'POST', url: '/courses/customer-courses/', data })
}

/** 更新客户疗程。 */
export function apiUpdateCustomerCourse(
  id: number,
  data: Partial<CustomerCourse>,
): Promise<CustomerCourse> {
  return request<CustomerCourse>({ method: 'PUT', url: `/courses/customer-courses/${id}/`, data })
}
