/** 评估 API 模块。 */

import { request } from './http'
import type {
  Assessment,
  AssessmentMetric,
  AssessmentMetricDefinition,
  AssessmentMetricInput,
  AssessmentStatus,
} from '@/types/api'

/** 评估创建/更新表单。 */
export interface AssessmentForm {
  customer: number
  plan?: number | null
  assessment_type: 'initial' | 'reassessment'
  assessment_date: string
  status?: AssessmentStatus
  onset_date?: string | null
  onset_description?: string
  onset_mode?: 'injury' | 'sudden' | 'gradual' | 'postoperative' | 'other' | 'unknown' | ''
  chief_complaint?: string
  medical_history?: string
  aggravating_factors?: string
  relieving_factors?: string
  prior_care?: string
  surgery_history?: string
  medication?: string
  exercise_habits?: string
  work_demands?: string
  sleep_impact?: string
  rehab_goal?: string
  current_status?: string
  note?: string
  metrics: AssessmentMetricInput[]
}

/** 查询某客户评估列表。 */
export function apiListAssessments(customerId: number): Promise<Assessment[]> {
  return request<Assessment[]>({ method: 'GET', url: '/assessments/', params: { customer_id: customerId } })
}

/** 首次评估状态（直达接口，供“去评估 / 继续评估”引导使用）。 */
export interface InitialAssessmentStatus {
  exists: boolean
  status: AssessmentStatus | null
  assessment_id: number | null
}

/** 查询某客户的首次评估状态。 */
export function apiGetInitialAssessment(customerId: number): Promise<InitialAssessmentStatus> {
  return request<InitialAssessmentStatus>({
    method: 'GET',
    url: '/assessments/initial/',
    params: { customer_id: customerId },
  })
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

/** 查询服务端维护的指标定义，前端只使用它渲染规则和选项。 */
export function apiGetMetricDefinitions(): Promise<AssessmentMetricDefinition[]> {
  return request<AssessmentMetricDefinition[]>({ method: 'GET', url: '/assessments/metric-definitions/' })
}

/** 完成评估，服务端执行完整校验并写入完成时间。 */
export function apiCompleteAssessment(id: number): Promise<Assessment> {
  return request<Assessment>({ method: 'POST', url: `/assessments/${id}/complete/` })
}

/** 兼容旧响应中的指标结构，供页面编辑时使用。
 * 保留 `id`，以便更新时让服务端按原 id 差异同步指标。 */
export function toAssessmentMetricInput(metric: AssessmentMetric): AssessmentMetricInput {
  const {
    metric_type_display: _metricTypeDisplay,
    score_max: _scoreMax,
    ...input
  } = metric
  return input as AssessmentMetricInput
}
