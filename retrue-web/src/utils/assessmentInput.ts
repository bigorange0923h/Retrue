/** 评估输入的字段文案与保守合并；摘要和精确编辑共用 AssessmentForm。 */
import type { AssessmentForm, AssessmentInputDraft } from '@/api/assessments'
import type { AssessmentMetricInput } from '@/types/api'

export const assessmentFieldLabels: Record<string, string> = {
  assessment_date: '评估日期', chief_complaint: '主要问题', onset_date: '开始日期',
  onset_description: '开始时间描述', onset_mode: '发生方式', medical_history: '既往伤病',
  aggravating_factors: '加重因素', relieving_factors: '缓解因素', prior_care: '既往就医与治疗',
  surgery_history: '手术史', medication: '用药情况', exercise_habits: '运动习惯',
  work_demands: '工作负荷', sleep_impact: '睡眠影响', rehab_goal: '康复目标',
  current_status: '当前状态', note: '补充备注',
}
export const onsetLabels: Record<string, string> = {
  injury: '受伤', sudden: '突然发作', gradual: '逐渐加重', postoperative: '术后',
  other: '其他', unknown: '暂不清楚',
}

/** 新候选仅填选中的字段；已有项目按身份防重复，绝不覆盖本次人工结果。 */
export function adoptAssessmentInput(form: AssessmentForm, draft: AssessmentInputDraft, selectedFields: string[], selectedMetrics: number[]): void {
  const writable = form as unknown as Record<string, unknown>
  for (const item of draft.fields) {
    if (selectedFields.includes(item.field) && assessmentFieldLabels[item.field]) writable[item.field] = item.value
  }
  for (const index of selectedMetrics) {
    const metric = draft.metrics[index]?.value
    if (!metric || form.metrics.some((existing) => metricIdentity(existing) === metricIdentity(metric))) continue
    form.metrics.push({ ...JSON.parse(JSON.stringify(metric)), sort_order: form.metrics.length })
  }
}

/** 项目身份只使用定义字段，避免同一测量被重复添加。 */
export function metricIdentity(metric: AssessmentMetricInput): string {
  return JSON.stringify([
    metric.metric_type, metric.body_part || '', metric.side || '', metric.context || '',
    metric.movement || '', metric.measurement_mode || '', metric.details?.test_name || '',
  ])
}

/** 冲突复核使用业务文案，不把内部字段 JSON 当作用户界面。 */
export function assessmentValueSummary(field: string, value: unknown): string {
  if (field === 'onset_mode') return onsetLabels[String(value)] || '尚未记录'
  if (field !== 'metrics') return value ? String(value) : '尚未记录'
  if (!Array.isArray(value) || !value.length) return '尚未添加项目'
  const types: Record<string, string> = { pain: '疼痛', strength: '肌力', rom: '活动度', special_test: '特殊测试', functional: '功能动作' }
  const results: Record<string, string> = { positive: '阳性', negative: '阴性', uncertain: '无法判断', normal: '正常', limited: '受限', unable: '无法完成' }
  const sides: Record<string, string> = { left: '左侧', right: '右侧', bilateral: '双侧', not_applicable: '不适用' }
  return value.map((metric: AssessmentMetricInput) => [
    types[metric.metric_type], metric.body_part, sides[metric.side || ''], metric.movement,
    metric.details?.test_name,
    metric.score != null ? `${metric.score}${metric.metric_type === 'rom' ? '°' : metric.metric_type === 'strength' ? ' 级' : ' 分'}` : results[metric.result_code || ''] || '结果尚未填写',
    metric.description,
  ].filter(Boolean).join(' · ')).join('\n')
}
