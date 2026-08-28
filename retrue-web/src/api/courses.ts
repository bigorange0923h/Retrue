/** 课程/日程 API 模块。 */

import { request } from './http'
import type { CourseSessionItem } from '@/types/api'

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

/** 创建课程。 */
export function apiCreateCourse(data: {
  customer: number
  course_name?: string
  date: string
  start_time?: string | null
  end_time?: string | null
  status?: string
  note?: string
}): Promise<CourseSessionItem> {
  return request<CourseSessionItem>({ method: 'POST', url: '/courses/', data })
}

/** 更新已有课程的安排或状态。 */
export function apiUpdateCourse(id: number, data: {
  customer?: number
  course_name?: string
  date?: string
  start_time?: string | null
  end_time?: string | null
  status?: string
  note?: string
}): Promise<CourseSessionItem> {
  return request<CourseSessionItem>({ method: 'PUT', url: `/courses/${id}/`, data })
}
