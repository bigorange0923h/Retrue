<script setup lang="ts">
/** 智能工作台组件：备课建议、阶段进展参考、风险提醒。 */

import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'

import { apiAnalyzeProgress, apiListRiskAlerts, apiPrepareLesson, apiUpdateRiskAlert } from '@/api/ai'
import type { LessonPreparation, ProgressAnalysis, RiskAlert } from '@/types/api'

const props = defineProps<{ customerId: number }>()

const loading = ref(false)
const lesson = ref<LessonPreparation | null>(null)
const progress = ref<ProgressAnalysis | null>(null)
const risks = ref<RiskAlert[]>([])

async function load(): Promise<void> {
  loading.value = true
  try {
    const [lessonRes, progressRes, riskRes] = await Promise.all([
      apiPrepareLesson(props.customerId).catch(() => null),
      apiAnalyzeProgress(props.customerId).catch(() => null),
      apiListRiskAlerts(props.customerId).catch(() => []),
    ])
    lesson.value = lessonRes
    progress.value = progressRes
    risks.value = riskRes
  } finally {
    loading.value = false
  }
}

async function confirmRisk(risk: RiskAlert): Promise<void> {
  await apiUpdateRiskAlert(risk.id, { is_confirmed: true, outcome: '已确认处理' })
  ElMessage.success('风险已确认')
  await load()
}

function riskTagType(level: string): 'danger' | 'warning' | 'info' {
  return level === 'high' ? 'danger' : level === 'medium' ? 'warning' : 'info'
}

function trendTagType(trend: string | null): 'success' | 'danger' | 'info' {
  return trend === '改善' ? 'success' : trend === '加重' ? 'danger' : 'info'
}

onMounted(load)
</script>

<template>
  <div v-loading="loading" class="lesson-prep">
    <div class="prep-header">
      <span class="section-title">智能工作台</span>
      <el-button size="small" @click="load">刷新</el-button>
    </div>

    <!-- 风险提醒（置顶展示） -->
    <div v-if="risks.length" class="risk-section">
      <div v-for="risk in risks.filter((r) => !r.is_confirmed)" :key="risk.id" class="risk-alert">
        <div class="risk-title">
          <el-tag :type="riskTagType(risk.risk_level)" size="small">{{ risk.risk_level_display }}风险</el-tag>
          <span class="risk-evidence">{{ risk.evidence }}</span>
        </div>
        <div class="risk-actions">
          <el-tag type="danger" effect="plain" size="small">建议：{{ risk.suggested_action_display }}</el-tag>
          <el-button link type="primary" size="small" @click="confirmRisk(risk)">确认处理</el-button>
        </div>
      </div>
    </div>

    <el-empty v-if="!loading && !lesson && !progress && risks.length === 0" description="暂无智能分析数据" :image-size="60" />

    <!-- 备课建议 -->
    <div v-if="lesson" class="block-card">
      <div class="sub-title">AI 备课建议 <el-tag size="small" type="warning">AI</el-tag></div>
      <div v-if="lesson.customer_summary.current_stage" class="summary-row">
        <span class="row-label">当前阶段</span>
        <el-tag size="small" type="primary">{{ lesson.customer_summary.current_stage }}</el-tag>
      </div>
      <div v-if="lesson.ai_suggestions.suggested_checks.length" class="suggest-list">
        <div v-for="check in lesson.ai_suggestions.suggested_checks" :key="check" class="suggest-item">· {{ check }}</div>
      </div>
    </div>

    <!-- 阶段进展参考 -->
    <div v-if="progress" class="block-card">
      <div class="sub-title">
        阶段进展参考
        <el-tag v-if="progress.pain_trend" :type="trendTagType(progress.pain_trend)" size="small">
          {{ progress.pain_trend }}
        </el-tag>
      </div>
      <div v-for="obs in progress.observations" :key="obs" class="progress-item">· {{ obs }}</div>
      <div class="progress-recommend">{{ progress.recommendation }}</div>
    </div>
  </div>
</template>

<style scoped>
.prep-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.section-title {
  font-weight: 600;
}

.sub-title {
  font-weight: 500;
  margin-bottom: 8px;
  display: flex;
  align-items: center;
  gap: 8px;
}

.block-card {
  background: #fafafa;
  border-radius: var(--retrue-radius-md);
  border: 1px solid var(--retrue-border);
  padding: 14px 16px;
  margin-bottom: 12px;
}

.risk-section {
  margin-bottom: 12px;
}

.risk-alert {
  background: #fef3e9;
  border: 1px solid #fbd8b0;
  border-radius: var(--retrue-radius-md);
  padding: 12px 14px;
  margin-bottom: 8px;
}

.risk-title {
  display: flex;
  align-items: center;
  gap: 8px;
}

.risk-evidence {
  font-size: 13px;
  color: var(--retrue-text);
}

.risk-actions {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 6px;
}

.summary-row {
  display: flex;
  gap: 10px;
  margin-bottom: 6px;
  font-size: 13px;
}

.row-label {
  color: var(--retrue-text-muted);
  width: 60px;
}

.suggest-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.suggest-item,
.progress-item {
  font-size: 13px;
  color: #333;
}

.progress-recommend {
  margin-top: 8px;
  font-size: 13px;
  color: #07a358;
  background: #f0f9eb;
  border-radius: 6px;
  padding: 8px 10px;
}
</style>
