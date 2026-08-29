/** 客户私有知识库 API 模块。 */

import { request } from './http'
import type { KnowledgeCandidate, KnowledgeItem, KnowledgeItemPayload } from '@/types/api'

/** 查询指定客户的知识条目。 */
export function apiListKnowledgeItems(customerId: number): Promise<KnowledgeItem[]> {
  return request<KnowledgeItem[]>({
    method: 'GET',
    url: '/knowledge/items/',
    params: { customer: customerId },
  })
}

/** 新增知识条目。 */
export function apiCreateKnowledgeItem(data: KnowledgeItemPayload): Promise<KnowledgeItem> {
  return request<KnowledgeItem>({ method: 'POST', url: '/knowledge/items/', data })
}

/** 更新知识条目。 */
export function apiUpdateKnowledgeItem(
  id: number,
  data: Partial<KnowledgeItemPayload>,
): Promise<KnowledgeItem> {
  return request<KnowledgeItem>({ method: 'PUT', url: `/knowledge/items/${id}/`, data })
}

/** 删除知识条目。 */
export function apiDeleteKnowledgeItem(id: number): Promise<void> {
  return request<void>({ method: 'DELETE', url: `/knowledge/items/${id}/` })
}

/** 查询指定客户的知识候选，可按状态筛选。 */
export function apiListKnowledgeCandidates(
  customerId: number,
  status?: string,
): Promise<KnowledgeCandidate[]> {
  return request<KnowledgeCandidate[]>({
    method: 'GET',
    url: '/knowledge/candidates/',
    params: { customer: customerId, ...(status ? { status } : {}) },
  })
}

/** 确认或拒绝知识候选。 */
export function apiDecideKnowledgeCandidate(
  id: number,
  action: 'confirm' | 'reject',
  payload?: { category?: string; importance?: string },
): Promise<KnowledgeCandidate> {
  return request<KnowledgeCandidate>({
    method: 'POST',
    url: `/knowledge/candidates/${id}/decide/`,
    data: { action, ...payload },
  })
}

/** 重建指定客户的知识向量索引。 */
export function apiBuildKnowledgeIndex(customerId: number): Promise<{ indexed: number }> {
  return request<{ indexed: number }>({
    method: 'POST',
    url: '/knowledge/index/',
    data: { customer: customerId },
  })
}

/** RAG 问答：基于客户私有知识库回答。 */
export function apiRagAnswer(
  customerId: number,
  question: string,
): Promise<{ answer: string; used_knowledge: KnowledgeItem[]; using_customer_context: boolean }> {
  return request({
    method: 'POST',
    url: '/knowledge/rag/',
    data: { customer: customerId, question },
  })
}
