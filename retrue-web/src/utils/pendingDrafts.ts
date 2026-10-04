import type { AiDraft, AssistantTask } from '../types/api'

/** 待办草稿引用，不携带原始病史文本到首页。 */
export interface PendingDraftEntry { key: string; customerName: string; label: string; taskId?: number; draftId?: number; customerId?: number | null; assessmentId?: number | null; assessmentType?: 'initial' | 'reassessment' }

/** 统一任务与旧草稿去重；评估输入使用该目标的最新待采用描述，避免历史保存版本重复列出。 */
export function pendingDraftEntries(tasks: AssistantTask[], drafts: AiDraft[]): PendingDraftEntry[] {
  const entries: PendingDraftEntry[] = tasks.map((item) => ({ key: `task:${item.id}`, customerName: item.customer_name || '待选择客户', label: item.status_display || '待你确认', taskId: item.id }))
  const taskIds = new Set(tasks.map((item) => item.id))
  const inputTargets = new Set<string>()
  for (const draft of [...drafts].sort((a, b) => b.id - a.id)) {
    if (draft.status !== 'pending' || (draft.assistant_task && taskIds.has(draft.assistant_task))) continue
    const result = draft.ai_result as unknown as Record<string, unknown>
    if (draft.draft_type === 'assessment' && result.input_version === 1) {
      const assessmentType = result.assessment_type === 'reassessment' ? 'reassessment' : 'initial'
      const target = `${draft.customer}:${draft.assessment || ''}:${assessmentType}`
      if (inputTargets.has(target)) continue
      inputTargets.add(target)
      entries.push({ key: `input:${draft.id}`, customerName: draft.customer_name || '当前客户', label: result.source_only ? '评估描述已保存，待继续' : '评估候选待核对采用', customerId: draft.customer, assessmentId: draft.assessment, assessmentType })
    } else entries.push({ key: `draft:${draft.id}`, customerName: draft.customer_name || '待选择客户', label: `${draft.draft_type_display || '训练'}草稿待确认`, draftId: draft.id })
  }
  return entries
}
