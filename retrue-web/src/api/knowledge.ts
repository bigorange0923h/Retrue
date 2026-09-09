/** 客户私有知识库 API 模块。 */

import { request } from './http'
import type { KnowledgeCandidate, KnowledgeItem, KnowledgeItemPayload, MemoryEpisode } from '@/types/api'

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

/** 停用一条长期记忆，保留历史和来源以便追溯。 */
export function apiExpireKnowledgeItem(id: number): Promise<KnowledgeItem> {
  return request<KnowledgeItem>({ method: 'POST', url: `/knowledge/items/${id}/expire/` })
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
  action: 'confirm' | 'reject' | 'replace' | 'keep_existing' | 'coexist' | 'defer',
  payload?: { category?: string; importance?: string; memory_type?: string; importance_score?: number; supersede_existing?: boolean; resolved_memory_key?: string },
): Promise<KnowledgeCandidate> {
  return request<KnowledgeCandidate>({
    method: 'POST',
    url: `/knowledge/candidates/${id}/decide/`,
    data: { action, ...payload },
  })
}

/** 重建指定客户的知识向量索引。 */
export interface KnowledgeIndexResult {
  indexed: number
  pending: number
  embedding_available: boolean
}

export function apiBuildKnowledgeIndex(customerId: number): Promise<KnowledgeIndexResult> {
  return request<KnowledgeIndexResult>({
    method: 'POST',
    url: '/knowledge/index/',
    data: { customer: customerId },
  })
}

/** RAG 问答：基于客户私有知识库回答。 */
export interface KnowledgeRagResult {
  answer: string
  used_knowledge: KnowledgeItem[]
  using_customer_context: boolean
  /** 检索方式：vector=语义检索 / keyword=有限关键词或最近条目 / no_result=无片段。 */
  retrieval_mode: 'vector' | 'keyword' | 'no_result'
}

export function apiRagAnswer(
  customerId: number,
  question: string,
): Promise<KnowledgeRagResult> {
  return request({
    method: 'POST',
    url: '/knowledge/rag/',
    data: { customer: customerId, question },
  })
}

/** 查询客户历史讨论事件。 */
export function apiListMemoryEpisodes(customerId: number): Promise<MemoryEpisode[]> {
  return request<MemoryEpisode[]>({
    method: 'GET',
    url: '/knowledge/episodes/',
    params: { customer: customerId },
  })
}

/** 确认或拒绝 Episode 候选。 */
export function apiDecideMemoryEpisode(
  id: number,
  action: 'confirm' | 'reject',
): Promise<MemoryEpisode> {
  return request<MemoryEpisode>({
    method: 'POST',
    url: `/knowledge/episodes/${id}/decide/`,
    data: { action },
  })
}

/** 删除 Episode，使其不再进入 AI 上下文。 */
export function apiDeleteMemoryEpisode(id: number): Promise<void> {
  return request<void>({ method: 'DELETE', url: `/knowledge/episodes/${id}/` })
}
