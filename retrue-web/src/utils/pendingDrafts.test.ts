import { strict as assert } from 'node:assert'
import { test } from 'node:test'
import { pendingDraftEntries } from './pendingDrafts.ts'
import type { AiDraft, AssistantTask } from '../types/api.ts'
const draft = (id: number, extra = {}): AiDraft => ({ id, status: 'pending', status_display: '待确认', customer: 1, customer_name: '演示客户', input_text: '不应进入首页模型', ai_result: { training_date: '', customer_hint: null, exercises: [], customer_feedback: '', therapist_observation: '', next_plan: '' }, confirmed_result: {}, error_message: '', created_at: '', ...extra })
test('任务关联草稿只列一次，取消草稿不混入待办', () => {
  const tasks = [{ id: 5, status: 'waiting_confirmation', task_type: 'training_record' }] as AssistantTask[]
  const result = pendingDraftEntries(tasks, [draft(2, { assistant_task: 5 }), draft(3, { status: 'cancelled' }), draft(4)])
  assert.deepEqual(result.map((item) => item.key), ['task:5', 'draft:4'])
  assert.ok(result.every((item) => !('input_text' in item)))
})
test('评估输入恢复原评估并只列最新版本，不走新建领域草稿确认', () => {
  const input = { draft_type: 'assessment', assessment: 8, ai_result: { input_version: 1, source_only: true, assessment_type: 'reassessment' } }
  const result = pendingDraftEntries([], [draft(1, input), draft(2, input)])
  assert.equal(result.length, 1)
  assert.equal(result[0]?.assessmentId, 8)
  assert.equal(result[0]?.assessmentType, 'reassessment')
  assert.equal(result[0]?.draftId, undefined)
  assert.equal(result[0]?.label, '评估描述已保存，待继续')
})
