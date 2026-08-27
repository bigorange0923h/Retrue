<script setup lang="ts">
/** 备课助手组件：汇总客户历史并展示 AI 备课建议。 */

import { onMounted, ref } from 'vue'

import { apiPrepareLesson } from '@/api/ai'
import type { LessonPreparation } from '@/types/api'

const props = defineProps<{ customerId: number }>()

const loading = ref(false)
const data = ref<LessonPreparation | null>(null)

async function load(): Promise<void> {
  loading.value = true
  try {
    data.value = await apiPrepareLesson(props.customerId)
  } catch {
    data.value = null
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <div v-loading="loading" class="lesson-prep">
    <div class="prep-header">
      <span class="section-title">课前备课</span>
      <el-button size="small" @click="load">刷新</el-button>
    </div>

    <el-empty v-if="!loading && !data" description="暂无备课数据" :image-size="60" />

    <template v-if="data">
      <!-- 客户历史汇总 -->
      <div class="summary-card">
        <div class="sub-title">历史回顾</div>
        <div class="summary-row">
          <span class="row-label">上次训练</span>
          <span class="row-value">
            {{ data.customer_summary.last_exercises.join('、') || '无记录' }}
          </span>
        </div>
        <div v-if="data.customer_summary.customer_feedback" class="summary-row">
          <span class="row-label">客户感受</span>
          <span class="row-value">{{ data.customer_summary.customer_feedback }}</span>
        </div>
        <div v-if="data.customer_summary.therapist_observation" class="summary-row">
          <span class="row-label">上次观察</span>
          <span class="row-value">{{ data.customer_summary.therapist_observation }}</span>
        </div>
        <div v-if="data.customer_summary.next_plan" class="summary-row">
          <span class="row-label">上次计划</span>
          <span class="row-value">{{ data.customer_summary.next_plan }}</span>
        </div>
        <div v-if="data.customer_summary.current_stage" class="summary-row">
          <span class="row-label">当前阶段</span>
          <el-tag size="small" type="primary">{{ data.customer_summary.current_stage }}</el-tag>
        </div>
      </div>

      <!-- AI 建议 -->
      <div class="suggest-card">
        <div class="sub-title">
          AI 备课建议
          <el-tag size="small" type="warning" class="ai-tag">AI</el-tag>
        </div>

        <div v-if="data.ai_suggestions.risk_reminders.length" class="risk-box">
          <div v-for="risk in data.ai_suggestions.risk_reminders" :key="risk" class="risk-item">
            {{ risk }}
          </div>
        </div>

        <div v-if="data.ai_suggestions.suggested_checks.length" class="suggest-list">
          <div v-for="check in data.ai_suggestions.suggested_checks" :key="check" class="suggest-item">
            · {{ check }}
          </div>
        </div>

        <el-empty
          v-if="data.ai_suggestions.suggested_checks.length === 0 && data.ai_suggestions.risk_reminders.length === 0"
          description="暂无 AI 建议"
          :image-size="60"
        />
      </div>
    </template>
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

.ai-tag {
  vertical-align: middle;
}

.summary-card,
.suggest-card {
  background: #fafafa;
  border-radius: 8px;
  padding: 12px 14px;
  margin-bottom: 12px;
}

.summary-row {
  display: flex;
  gap: 10px;
  margin-bottom: 6px;
  font-size: 13px;
}

.row-label {
  color: #888;
  width: 60px;
  flex-shrink: 0;
}

.row-value {
  color: #333;
}

.risk-box {
  background: #fef0f0;
  border: 1px solid #fde2e2;
  border-radius: 8px;
  padding: 8px 12px;
  margin-bottom: 10px;
}

.risk-item {
  color: #d4380d;
  font-size: 13px;
  margin-bottom: 4px;
}

.suggest-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.suggest-item {
  font-size: 13px;
  color: #333;
}
</style>
