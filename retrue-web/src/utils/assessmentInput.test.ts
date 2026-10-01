/** 保守合并与项目防重复的业务回归，可用 node --experimental-strip-types --test 运行。 */
import { strict as assert } from 'node:assert'
import { test } from 'node:test'
import { adoptAssessmentInput } from './assessmentInput.ts'
import type { AssessmentForm, AssessmentInputDraft } from '../api/assessments.ts'

function fixture(): { form: AssessmentForm; draft: AssessmentInputDraft } {
  return {
    form: { customer: 1, assessment_type: 'initial', assessment_date: '2026-10-01', chief_complaint: '人工填写', metrics: [] },
    draft: {
      id: 1, input_text: '测试描述', warnings: [],
      fields: [{ field: 'chief_complaint', value: '模型主诉', evidence: '模型主诉' }, { field: 'onset_description', value: '两周前', evidence: '两周前' }],
      metrics: [{ value: { metric_type: 'pain', body_part: '膝', side: 'right', context: 'activity', score: 3, description: '', sort_order: 0 }, evidence: {} }],
    },
  }
}

test('未选中的人工字段保留，仅合并明确采用的缺项', () => {
  const { form, draft } = fixture()
  adoptAssessmentInput(form, draft, ['onset_description'], [])
  assert.equal(form.chief_complaint, '人工填写')
  assert.equal(form.onset_description, '两周前')
  assert.equal(form.metrics.length, 0)
})
test('重复采用项目不重复添加，不覆盖人工测量结果', () => {
  const { form, draft } = fixture()
  adoptAssessmentInput(form, draft, [], [0])
  form.metrics[0]!.score = 5
  adoptAssessmentInput(form, draft, [], [0])
  assert.equal(form.metrics.length, 1)
  assert.equal(form.metrics[0]!.score, 5)
  assert.equal(draft.metrics[0]!.value.score, 3)
})
test('不同侧别保持两个独立项目，不错误去重', () => {
  const { form, draft } = fixture()
  adoptAssessmentInput(form, draft, [], [0])
  draft.metrics[0]!.value.side = 'left'
  adoptAssessmentInput(form, draft, [], [0])
  assert.equal(form.metrics.length, 2)
  assert.deepEqual(form.metrics.map((metric) => metric.side), ['right', 'left'])
})
test('候选不能修改客户身份、生命周期或执行完成', () => {
  const { form, draft } = fixture()
  draft.fields.push({ field: 'customer', value: '2', evidence: '2' }, { field: 'status', value: 'completed', evidence: 'completed' })
  adoptAssessmentInput(form, draft, ['customer', 'status'], [])
  assert.equal(form.customer, 1)
  assert.notEqual(form.status, 'completed')
})
