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

/** 创建课程。 */
export function apiCreateCourse(data: {
  customer: number
  date: string
  start_time?: string | null
  end_time?: string | null
  status?: string
  note?: string
}): Promise<CourseSessionItem> {
  return request<CourseSessionItem>({ method: 'POST', url: '/courses/', data })
}
