/** 训练记录 API 模块。 */

import { request } from './http'
import type { HomeTrainingExercise, HomeTrainingPlan, PageData, TrainingExercise, TrainingRecord } from '@/types/api'

/** 训练记录创建/更新表单（含动作明细）。 */
export interface TrainingRecordForm {
  customer: number
  course_session?: number | null
  training_date: string
  customer_feedback?: string
  therapist_observation?: string
  next_plan?: string
  note?: string
  exercises?: TrainingExercise[]
}

/** 分页查询某客户的训练记录。 */
export function apiListTrainingRecords(customerId: number, page = 1, pageSize = 20): Promise<PageData<TrainingRecord>> {
  return request<PageData<TrainingRecord>>({
    method: 'GET',
    url: '/training/',
    params: { customer_id: customerId, page, page_size: pageSize },
  })
}

/** 获取训练记录详情。 */
export function apiGetTrainingRecord(id: number): Promise<TrainingRecord> {
  return request<TrainingRecord>({ method: 'GET', url: `/training/${id}/` })
}

/** 创建训练记录。 */
export function apiCreateTrainingRecord(data: TrainingRecordForm): Promise<TrainingRecord> {
  return request<TrainingRecord>({ method: 'POST', url: '/training/', data })
}

/** 人工修订训练记录（需修改原因）。 */
export function apiReviseTrainingRecord(id: number, data: TrainingRecordForm & { reason: string }): Promise<TrainingRecord> {
  return request<TrainingRecord>({ method: 'PUT', url: `/training/${id}/`, data })
}

/** 查询客户时间线。 */
export function apiGetCustomerTimeline(customerId: number): Promise<TrainingRecord[]> {
  return request<TrainingRecord[]>({
    method: 'GET',
    url: '/training/timeline/',
    params: { customer_id: customerId },
  })
}

/** 查询家庭训练计划列表。 */
export function apiListHomeTrainingPlans(customerId: number): Promise<HomeTrainingPlan[]> {
  return request<HomeTrainingPlan[]>({
    method: 'GET',
    url: '/training/home/plans/',
    params: { customer_id: customerId },
  })
}

/** 创建家庭训练计划。 */
export function apiCreateHomeTrainingPlan(data: {
  customer: number
  title?: string
  frequency?: string
  note?: string
  exercises?: HomeTrainingExercise[]
}): Promise<HomeTrainingPlan> {
  return request<HomeTrainingPlan>({ method: 'POST', url: '/training/home/plans/', data })
}

/** 更新家庭训练计划。 */
export function apiUpdateHomeTrainingPlan(id: number, data: Partial<{ title: string; frequency: string; note: string; exercises: HomeTrainingExercise[] }>): Promise<HomeTrainingPlan> {
  return request<HomeTrainingPlan>({ method: 'PUT', url: `/training/home/plans/${id}/`, data })
}
