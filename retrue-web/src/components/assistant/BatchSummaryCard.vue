<script setup lang="ts">
/**
 * 多客户批量训练补记汇总卡片：展示本次批量处理结果（成功/跳过/失败明细）。
 */

import { computed } from 'vue'
import type { AssistantCard, BatchSummary } from '@/api/assistant'

interface Props {
  card: AssistantCard
}

const props = defineProps<Props>()

const summary = computed<BatchSummary | null>(() => props.card.batch_summary ?? null)

const statusLabel: Record<string, string> = {
  completed: '已保存',
  skipped: '已跳过',
  failed: '失败',
}
</script>

<template>
  <div v-if="summary" class="batch-summary-card assistant-card">
    <div class="card-title">
      <strong>批量补记完成</strong>
      <el-tag type="success" size="small">完成</el-tag>
    </div>
    <p class="card-hint">共 {{ summary.total_items }} 位客户：成功 {{ summary.succeeded }} 项，跳过 {{ summary.skipped }} 项，失败 {{ summary.failed }} 项。</p>
    <div class="summary-lines">
      <div v-for="line in summary.lines" :key="line.sequence" class="summary-line">
        <span class="line-seq">第 {{ line.sequence }} 项</span>
        <span class="line-name">{{ line.customer_name }}</span>
        <el-tag :type="line.status === 'completed' ? 'success' : line.status === 'skipped' ? 'info' : 'danger'" size="small">
          {{ statusLabel[line.status] || line.status }}
        </el-tag>
      </div>
    </div>
  </div>
</template>

<style scoped>
.batch-summary-card { display: flex; flex-direction: column; gap: 10px; }
.card-title { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.card-title strong { color: var(--retrue-text); font-size: 14px; }
.card-hint { margin: 0; color: var(--retrue-text-secondary); font-size: 12px; }
.summary-lines { display: flex; flex-direction: column; gap: 6px; }
.summary-line { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; padding: 6px 10px; border: 1px solid var(--retrue-border); border-radius: var(--retrue-radius-sm); background: var(--retrue-bg); }
.line-seq { color: var(--retrue-text-muted); font-size: 12px; }
.line-name { flex: 1; min-width: 0; color: var(--retrue-text); font-size: 13px; font-weight: 600; }
</style>
