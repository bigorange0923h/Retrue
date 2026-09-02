<script setup lang="ts">
/**
 * 客户信息摘要卡片：展示后端只读 Tool 的受控摘要，不默认展示完整病史或手机号。
 * 操作继续在聊天中创建新卡片，不跳转独立工作模式。
 */

import { computed } from 'vue'
import type { AssistantCard, CustomerSummary } from '@/api/assistant'

interface Props {
  card: AssistantCard
}

const props = defineProps<Props>()
const emit = defineEmits<{
  action: [action: string]
}>()

const summary = computed<CustomerSummary>(() => (props.card.summary ?? {}) as CustomerSummary)
const hasData = computed(() => Boolean(summary.value.name || summary.value.recent_training_count != null))
</script>

<template>
  <div class="customer-summary-card assistant-card">
    <div class="card-title">
      <strong>{{ summary.name || '客户' }}</strong>
      <span>客户信息摘要</span>
    </div>
    <div v-if="hasData" class="summary-grid">
      <div v-if="summary.phone_masked" class="summary-item"><span>手机号</span><b>{{ summary.phone_masked }}</b></div>
      <div v-if="summary.gender_display" class="summary-item"><span>性别</span><b>{{ summary.gender_display }}</b></div>
      <div v-if="summary.main_issue" class="summary-item"><span>主要问题</span><b>{{ summary.main_issue }}</b></div>
      <div class="summary-item"><span>近期训练</span><b>{{ summary.recent_training_count ?? 0 }} 次</b></div>
      <div class="summary-item">
        <span>首次评估</span>
        <b>{{ summary.initial_assessment?.exists ? (summary.initial_assessment.status_display || '已完成') : '尚未完成' }}</b>
      </div>
      <div v-if="summary.active_plan" class="summary-item summary-wide">
        <span>当前计划</span><b>{{ summary.active_plan.name }}</b>
      </div>
    </div>
    <div class="card-actions">
      <el-button link type="primary" @click="emit('action', 'view_recent_training')">查看近期训练</el-button>
      <el-button link type="primary" @click="emit('action', 'view_schedule')">查看课程安排</el-button>
      <el-button link type="primary" @click="emit('action', 'start_record')">开始补记</el-button>
      <el-button link type="primary" @click="emit('action', 'start_assessment')">发起评估</el-button>
    </div>
  </div>
</template>

<style scoped>
.customer-summary-card { display: flex; flex-direction: column; gap: 10px; }
.card-title { display: flex; align-items: baseline; gap: 8px; }
.card-title strong { color: var(--retrue-text); font-size: 14px; }
.card-title span { color: var(--retrue-text-muted); font-size: 12px; }
.summary-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; }
.summary-item { display: flex; flex-direction: column; gap: 2px; padding: 8px 10px; border-radius: var(--retrue-radius-sm); background: var(--retrue-bg); }
.summary-item span { color: var(--retrue-text-muted); font-size: 11px; }
.summary-item b { color: var(--retrue-text); font-size: 13px; font-weight: 600; }
.summary-wide { grid-column: 1 / -1; }
.card-actions { display: flex; flex-wrap: wrap; gap: 4px; }
@media (max-width: 768px) {
  .summary-grid { grid-template-columns: minmax(0, 1fr); }
}
</style>
