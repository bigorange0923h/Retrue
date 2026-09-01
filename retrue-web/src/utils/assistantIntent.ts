/**
 * 统一助理的本地安全意图识别。
 *
 * 这里只判断是否“建议切换到训练补记”，不会创建草稿或写入正式记录。
 * 规则刻意保持保守：问题句优先作为咨询，只有明确补记指令或同时出现多类
 * 训练经过信号时才提示康复师选择。
 */

export interface AssistantIntentSuggestion {
  intent: 'chat' | 'training_record'
  confidence: 'low' | 'medium' | 'high'
}

const DIRECT_RECORD_REQUEST = /(?:帮我|请|麻烦|给我).{0,8}(?:补记|记录|整理成.{0,4}记录|保存为.{0,4}记录)|^(?:补记|记录)[：:，,\s]/
const QUESTION_SIGNAL = /[?？]|(?:怎么|如何|为什么|是否|能不能|可不可以|建议|应该|什么|哪里|哪种|多少)/
const SESSION_SIGNAL = /(?:今天|今日|本次|这次|这节课|刚才|训练中|训练后)/
const DOSE_SIGNAL = /(?:做了|完成了|训练了)|\d+(?:\.\d+)?\s*(?:组|次|秒|分钟|公斤|kg|米)/i
const OBSERVATION_SIGNAL = /(?:疼|痛|不适|稳定|代偿|疲劳|耐受|活动度|力量|平衡|反馈|感觉)/
const NEXT_PLAN_SIGNAL = /(?:下次|后续|接下来).{0,12}(?:训练|增加|减少|调整|继续|观察)/

/** 返回建议类型；调用方必须让康复师确认后才能切换到补记流程。 */
export function suggestAssistantIntent(input: string): AssistantIntentSuggestion {
  const text = input.trim()
  if (!text) return { intent: 'chat', confidence: 'low' }
  if (DIRECT_RECORD_REQUEST.test(text)) return { intent: 'training_record', confidence: 'high' }
  if (QUESTION_SIGNAL.test(text)) return { intent: 'chat', confidence: 'low' }

  const signalCount = [SESSION_SIGNAL, DOSE_SIGNAL, OBSERVATION_SIGNAL, NEXT_PLAN_SIGNAL]
    .filter((pattern) => pattern.test(text))
    .length
  if (signalCount >= 2) return { intent: 'training_record', confidence: 'medium' }
  return { intent: 'chat', confidence: 'low' }
}
