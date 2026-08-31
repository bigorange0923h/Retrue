/** 课程模板与排课 API 模块。 */

import { request } from './http'
import type {
  CourseScheduleConfirmResult,
  CourseSchedulePreview,
  CourseSessionItem,
  CourseType,
} from '@/types/api'

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
  plan_course?: number | null
  arrangement_type?: 'plan' | 'initial_assessment' | 'reassessment' | 'other'
  session_topic?: string
  session_count?: number
  date?: string
  start_time?: string | null
  end_time?: string | null
  status?: string
  note?: string
}

/** 批量安排课程的条件。星期使用 0（周日）至 6（周六）。 */
export interface CourseScheduleBatchPayload {
  customer: number
  plan_course: number
  start_date: string
  weekly_count: number
  weekdays: number[]
  start_time: string
}

/** 预览批量安排结果，不会写入课表。 */
export function apiPreviewCourseSchedule(
  data: CourseScheduleBatchPayload,
): Promise<CourseSchedulePreview> {
  return request<CourseSchedulePreview>({
    method: 'POST',
    url: '/courses/batch/preview/',
    data,
  })
}

/** 确认批量安排结果，一次性写入课表。 */
export function apiConfirmCourseSchedule(
  data: CourseScheduleBatchPayload,
): Promise<CourseScheduleConfirmResult> {
  return request<CourseScheduleConfirmResult>({
    method: 'POST',
    url: '/courses/batch/confirm/',
    data,
  })
}

/** 创建课程。 */
export function apiCreateCourse(data: CoursePayload): Promise<CourseSessionItem> {
  return request<CourseSessionItem>({ method: 'POST', url: '/courses/', data })
}

/** 更新已有课程的安排或状态。 */
export function apiUpdateCourse(id: number, data: Partial<CoursePayload>): Promise<CourseSessionItem> {
  return request<CourseSessionItem>({ method: 'PUT', url: `/courses/${id}/`, data })
}

/** 查询单节课程详情。 */
export function apiGetCourse(id: number): Promise<CourseSessionItem> {
  return request<CourseSessionItem>({ method: 'GET', url: `/courses/${id}/` })
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
