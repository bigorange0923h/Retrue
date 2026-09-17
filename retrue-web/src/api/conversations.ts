/** Retrue AI 统一会话 API。 */

import { request } from './http'
import type { AiConversation, ConversationOrigin, ConversationType } from '@/types/api'

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

/** 获取一段会话及其历史消息。 */
export function apiGetConversation(conversationId: number): Promise<AiConversation> {
  return request<AiConversation>({ method: 'GET', url: `/conversations/${conversationId}/` })
}
