/** AI 草稿 API 模块。 */

import { request } from './http'
import type { AiDraft, AiDraftResult, CustomerCandidate, LessonPreparation } from '@/types/api'

/** 解析训练文本生成草稿。 */
export function apiParseDraft(inputText: string, customerId?: number | null): Promise<AiDraft> {
  return request<AiDraft>({ method: 'POST', url: '/ai/parse/', data: { input_text: inputText, customer_id: customerId } })
}

/** 确认草稿并创建正式训练记录。 */
export function apiConfirmDraft(draftId: number, customerId: number, confirmed: AiDraftResult): Promise<AiDraft> {
  return request<AiDraft>({
    method: 'POST',
    url: `/ai/confirm/${draftId}/`,
    data: { customer_id: customerId, confirmed },
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
