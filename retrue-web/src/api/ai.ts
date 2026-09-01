/** AI 草稿 API 模块。 */

import { request } from './http'
import type { AiDraft, AiDraftResult, AiQaResponse, CustomerCandidate, LessonPreparation, ProgressAnalysis, RiskAlert } from '@/types/api'

// AI 解析服务端最长等待约 60 秒；前端需要比服务端多留出响应传输时间，
// 避免浏览器先超时而服务端仍在生成草稿，导致康复师误以为需要重复提交。
const AI_REQUEST_TIMEOUT_MS = 75_000

/** 解析训练描述时关联的统一助理任务。 */
export interface ParseDraftOptions {
  assistantTaskId?: number | null
  courseSessionId?: number | null
  clientRequestId?: string
}

/** 确认草稿时用于幂等和任务回写的上下文。 */
export interface ConfirmDraftOptions {
  idempotencyKey?: string
}

/** 解析训练文本生成草稿。 */
export function apiParseDraft(
  inputText: string,
  customerId?: number | null,
  options?: ParseDraftOptions,
): Promise<AiDraft> {
  const data: Record<string, unknown> = { input_text: inputText, customer_id: customerId }
  if (options?.assistantTaskId != null) data.assistant_task_id = options.assistantTaskId
  if (options?.courseSessionId != null) data.course_session_id = options.courseSessionId
  if (options?.clientRequestId) data.client_request_id = options.clientRequestId
  return request<AiDraft>({ method: 'POST', url: '/ai/parse/', data, timeout: AI_REQUEST_TIMEOUT_MS })
}

/** 确认草稿并创建正式训练记录。 */
export function apiConfirmDraft(
  draftId: number,
  customerId: number,
  confirmed: AiDraftResult,
  courseSessionId?: number | null,
  options?: ConfirmDraftOptions,
): Promise<AiDraft> {
  const data: Record<string, unknown> = {
    customer_id: customerId,
    course_session_id: courseSessionId,
    confirmed,
  }
  if (options?.idempotencyKey) data.idempotency_key = options.idempotencyKey
  return request<AiDraft>({
    method: 'POST',
    url: `/ai/confirm/${draftId}/`,
    data,
    timeout: AI_REQUEST_TIMEOUT_MS,
  })
}

/** 取消草稿。 */
export function apiCancelDraft(draftId: number): Promise<AiDraft> {
  return request<AiDraft>({ method: 'POST', url: `/ai/cancel/${draftId}/` })
}

/** 待确认草稿列表。 */
export function apiListDrafts(): Promise<AiDraft[]> {
  return request<AiDraft[]>({ method: 'GET', url: '/ai/drafts/' })
}

/** 客户候选查询。 */
export function apiCustomerCandidates(name?: string): Promise<CustomerCandidate[]> {
  return request<CustomerCandidate[]>({
    method: 'GET',
    url: '/ai/customer-candidates/',
    params: name ? { name } : undefined,
  })
}

/** 备课助手。 */
export function apiPrepareLesson(customerId: number): Promise<LessonPreparation> {
  return request<LessonPreparation>({
    method: 'GET',
    url: '/ai/prepare-lesson/',
    params: { customer_id: customerId },
  })
}

/** 查询风险提醒列表。 */
export function apiListRiskAlerts(customerId: number): Promise<RiskAlert[]> {
  return request<RiskAlert[]>({ method: 'GET', url: '/ai/risks/', params: { customer_id: customerId } })
}

/** 风险检测。 */
export function apiDetectRisk(customerId: number, trainingRecordId?: number): Promise<RiskAlert | null> {
  return request<RiskAlert | null>({
    method: 'POST',
    url: '/ai/risks/detect/',
    data: { customer_id: customerId, training_record_id: trainingRecordId },
  })
}

/** 更新风险提醒（确认/处理结果）。 */
export function apiUpdateRiskAlert(id: number, data: { is_confirmed?: boolean; outcome?: string }): Promise<RiskAlert> {
  return request<RiskAlert>({ method: 'PUT', url: `/ai/risks/${id}/`, data })
}

/** 阶段进展参考。 */
export function apiAnalyzeProgress(customerId: number): Promise<ProgressAnalysis> {
  return request<ProgressAnalysis>({ method: 'GET', url: '/ai/progress/', params: { customer_id: customerId } })
}

/** AI 专业问答。 */
export function apiAskAi(question: string): Promise<AiQaResponse> {
  return request<AiQaResponse>({ method: 'POST', url: '/ai/qa/', data: { question } })
}
