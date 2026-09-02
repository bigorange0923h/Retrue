<script setup lang="ts">
/**
 * 风险核查卡片：显示非技术化的人工核查提醒，不自动诊断、不自动写正式记录。
 * 提供补充情况、继续咨询、暂不处理等安全选项。
 */

import type { AssistantCard } from '@/api/assistant'

interface Props {
  card: AssistantCard
}

defineProps<Props>()
const emit = defineEmits<{
  action: [action: string]
}>()
</script>

<template>
  <div class="risk-review-card assistant-card">
    <div class="risk-heading">
      <el-icon><WarningFilled /></el-icon>
      <strong>需要人工核查</strong>
    </div>
    <p class="risk-notice">{{ card.notice || '这段描述可能涉及需要人工核查的情况，请结合客户资料确认后再继续。' }}</p>
    <p class="risk-hint">系统不会自动诊断、不会自动调整训练方案，也不会写入正式记录。</p>
    <div class="card-actions">
      <el-button size="small" @click="emit('action', 'supplement')">补充情况</el-button>
      <el-button size="small" type="primary" plain @click="emit('action', 'continue')">继续咨询</el-button>
      <el-button size="small" text @click="emit('action', 'dismiss')">暂不处理</el-button>
    </div>
  </div>
</template>

<style scoped>
.risk-review-card { display: flex; flex-direction: column; gap: 8px; padding: 12px; border: 1px solid color-mix(in srgb, var(--retrue-danger, #f56c6c) 40%, var(--retrue-border)); border-radius: var(--retrue-radius-md); background: color-mix(in srgb, var(--retrue-danger, #f56c6c) 6%, var(--retrue-surface)); }
.risk-heading { display: flex; align-items: center; gap: 6px; color: var(--retrue-danger, #f56c6c); }
.risk-heading strong { font-size: 14px; }
.risk-notice { margin: 0; color: var(--retrue-text); font-size: 13px; line-height: 1.6; }
.risk-hint { margin: 0; color: var(--retrue-text-muted); font-size: 12px; }
.card-actions { display: flex; flex-wrap: wrap; gap: 8px; }
</style>
