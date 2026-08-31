<script setup lang="ts">
/** 第五步：以中文摘要检查本次评估，完成前提醒缺失内容。 */

import type { AssessmentForm } from '@/api/assessments'
import type { AssessmentMetricInput, MetricType } from '@/types/api'

const props = defineProps<{
  form: AssessmentForm
  customerName?: string
  missingItems?: string[]
}>()

const metricLabels: Record<MetricType, string> = {
  pain: '疼痛',
  strength: '肌力',
  rom: '活动度',
  special_test: '特殊测试',
  functional: '功能动作',
}

const resultLabels: Record<string, string> = {
  positive: '阳性',
  negative: '阴性',
  uncertain: '无法判断',
  normal: '正常完成',
  limited: '受限完成',
  unable: '无法完成',
}

function metricTitle(metric: AssessmentMetricInput): string {
  const detailName = typeof metric.details?.test_name === 'string' ? metric.details.test_name : ''
  if (metric.metric_type === 'special_test' && detailName) return `${metricLabels[metric.metric_type]} · ${detailName}`
  if (metric.metric_type === 'functional' && metric.movement) return `${metricLabels[metric.metric_type]} · ${metric.movement}`
  if (metric.movement) return `${metricLabels[metric.metric_type]} · ${metric.movement}`
  return metricLabels[metric.metric_type]
}

function metricResult(metric: AssessmentMetricInput): string {
  if (metric.metric_type === 'pain' && metric.score !== null && metric.score !== undefined) return `${metric.score} 分`
  if (metric.metric_type === 'strength' && metric.score !== null && metric.score !== undefined) return `${metric.score} 级`
  if (metric.metric_type === 'rom' && metric.score !== null && metric.score !== undefined) return `${metric.score}°`
  return resultLabels[metric.result_code || ''] || '尚未填写结果'
}

function metricMeta(metric: AssessmentMetricInput): string {
  const parts: string[] = []
  if (metric.body_part) parts.push(metric.body_part)
  if (metric.side && metric.side !== 'not_applicable') {
    parts.push({ left: '左侧', right: '右侧', bilateral: '双侧' }[metric.side] || '')
  }
  if (metric.context) {
    parts.push({ rest: '静息', activity: '活动时', pre_training: '训练前', post_training: '训练后', night: '夜间', custom: '其他场景' }[metric.context] || '')
  }
  if (metric.measurement_mode) parts.push(metric.measurement_mode === 'active' ? '主动' : '被动')
  return parts.filter(Boolean).join(' · ')
}
</script>

<template>
  <section class="assessment-step">
    <div class="step-intro">
      <p class="eyebrow">第五步 / 检查并完成</p>
      <h3>请检查这份评估，再决定是否完成</h3>
      <p>完成后数据才会用于 AI 辅助和复评趋势。之后仍可按权限修订记录。</p>
    </div>

    <el-alert v-if="props.missingItems?.length" title="还有内容需要补充" type="warning" :closable="false" show-icon>
      <template #default>
        <ul class="missing-list">
          <li v-for="item in props.missingItems" :key="item">{{ item }}</li>
        </ul>
      </template>
    </el-alert>

    <div class="review-section">
      <h4>本次问题</h4>
      <dl class="summary-grid">
        <div><dt>客户</dt><dd>{{ props.customerName || `客户 #${props.form.customer}` }}</dd></div>
        <div><dt>评估日期</dt><dd>{{ props.form.assessment_date || '未填写' }}</dd></div>
        <div><dt>评估类型</dt><dd>{{ props.form.assessment_type === 'initial' ? '首次评估' : '阶段复评' }}</dd></div>
        <div><dt>开始情况</dt><dd>{{ props.form.onset_date || props.form.onset_description || '未填写' }}</dd></div>
        <div class="summary-wide"><dt>主要问题</dt><dd>{{ props.form.chief_complaint || '未填写' }}</dd></div>
      </dl>
    </div>

    <div class="review-section">
      <h4>主观情况</h4>
      <div class="text-summary">
        <p v-if="props.form.aggravating_factors"><span>加重因素：</span>{{ props.form.aggravating_factors }}</p>
        <p v-if="props.form.relieving_factors"><span>缓解方式：</span>{{ props.form.relieving_factors }}</p>
        <p v-if="props.form.prior_care"><span>既往治疗：</span>{{ props.form.prior_care }}</p>
        <p v-if="props.form.medical_history"><span>病史：</span>{{ props.form.medical_history }}</p>
        <p v-if="props.form.sleep_impact"><span>睡眠影响：</span>{{ props.form.sleep_impact }}</p>
        <p v-if="!props.form.aggravating_factors && !props.form.relieving_factors && !props.form.prior_care && !props.form.medical_history && !props.form.sleep_impact" class="empty-summary">尚未填写额外主观情况</p>
      </div>
    </div>

    <div class="review-section">
      <div class="section-heading"><h4>客观评估</h4><span>{{ props.form.metrics.length }} 个项目</span></div>
      <div v-if="props.form.metrics.length" class="review-metrics">
        <div v-for="(metric, index) in props.form.metrics" :key="`${metric.metric_type}-${index}`" class="review-metric">
          <div class="review-metric-main">
            <strong>{{ metricTitle(metric) }}</strong>
            <span class="review-result">{{ metricResult(metric) }}</span>
          </div>
          <div v-if="metricMeta(metric)" class="review-meta">{{ metricMeta(metric) }}</div>
          <p v-if="metric.description">{{ metric.description }}</p>
        </div>
      </div>
      <p v-else class="empty-summary">尚未添加客观评估项目</p>
    </div>

    <div class="review-section">
      <h4>康复目标与备注</h4>
      <div class="text-summary">
        <p><span>康复目标：</span>{{ props.form.rehab_goal || '未填写' }}</p>
        <p v-if="props.form.current_status"><span>当前状态：</span>{{ props.form.current_status }}</p>
        <p v-if="props.form.note"><span>补充备注：</span>{{ props.form.note }}</p>
      </div>
    </div>
  </section>
</template>

<style scoped>
.assessment-step {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.step-intro h3 {
  margin: 4px 0 7px;
  font-size: 20px;
}

.step-intro p {
  margin: 0;
  color: var(--retrue-text-secondary);
  line-height: 1.7;
}

.step-intro .eyebrow {
  color: var(--retrue-primary);
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.08em;
}

.missing-list {
  margin: 0;
  padding-left: 18px;
  line-height: 1.8;
}

.review-section {
  border: 1px solid var(--retrue-border);
  border-radius: var(--retrue-radius-md);
  background: var(--retrue-surface-subtle);
  padding: 16px;
}

.review-section h4 {
  margin: 0 0 14px;
  font-size: 15px;
}

.summary-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px 20px;
  margin: 0;
}

.summary-grid > div {
  min-width: 0;
}

.summary-wide {
  grid-column: 1 / -1;
}

dt {
  margin-bottom: 4px;
  color: var(--retrue-text-muted);
  font-size: 12px;
}

dd {
  margin: 0;
  line-height: 1.6;
  overflow-wrap: anywhere;
}

.text-summary {
  color: var(--retrue-text-secondary);
  line-height: 1.7;
}

.text-summary p {
  margin: 7px 0;
}

.text-summary p:first-child {
  margin-top: 0;
}

.text-summary p:last-child {
  margin-bottom: 0;
}

.text-summary span {
  color: var(--retrue-text);
  font-weight: 600;
}

.empty-summary {
  color: var(--retrue-text-muted);
}

.section-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.section-heading span {
  color: var(--retrue-text-muted);
  font-size: 12px;
}

.review-metrics {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.review-metric {
  border-radius: var(--retrue-radius-sm);
  background: var(--retrue-surface);
  padding: 12px;
}

.review-metric-main {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.review-metric-main strong {
  min-width: 0;
  overflow-wrap: anywhere;
}

.review-result {
  flex: 0 0 auto;
  color: var(--retrue-primary-dark);
  font-weight: 700;
}

.review-meta,
.review-metric p {
  margin: 5px 0 0;
  color: var(--retrue-text-secondary);
  font-size: 12px;
  line-height: 1.6;
}

@media (max-width: 768px) {
  .summary-grid {
    grid-template-columns: minmax(0, 1fr);
  }

  .summary-wide {
    grid-column: auto;
  }

  .review-metric-main {
    align-items: flex-start;
    flex-direction: column;
    gap: 4px;
  }
}
</style>
