/** Retrue AI 统一会话 API。 */

import { request } from './http'
import type { AiConversation, ConversationMessageResult, ConversationOrigin, ConversationType, MemoryEpisode } from '@/types/api'

export interface ConversationCreatePayload {
  customer?: number | null
  origin: ConversationOrigin
  conversation_type: ConversationType
  context_resource_type?: string
  context_resource_id?: string
}

/** 创建一段可追溯的 AI 会话。 */
export function apiCreateConversation(data: ConversationCreatePayload): Promise<AiConversation> {
  return request<AiConversation>({ method: 'POST', url: '/conversations/', data })
}

/** 发送消息并返回已持久化的 AI 回复及本轮记忆候选。 */
export function apiSendConversationMessage(
  conversationId: number,
  content: string,
): Promise<ConversationMessageResult> {
  return request<ConversationMessageResult>({
    method: 'POST',
    url: `/conversations/${conversationId}/messages/`,
    data: { content },
  })
}

/** 获取一段会话及其历史消息。 */
export function apiGetConversation(conversationId: number): Promise<AiConversation> {
  return request<AiConversation>({ method: 'GET', url: `/conversations/${conversationId}/` })
}

/** 主动从当前会话提取待确认的历史讨论事件。 */
export function apiExtractConversationEpisodes(conversationId: number): Promise<MemoryEpisode[]> {
  return request<MemoryEpisode[]>({
    method: 'POST',
    url: `/conversations/${conversationId}/episodes/extract/`,
  })
}
