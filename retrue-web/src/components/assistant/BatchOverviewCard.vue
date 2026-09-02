<script setup lang="ts">
/**
 * 多客户批量训练补记概览卡片：展示子项顺序与状态，支持逐项开始/继续处理。
 */

import { computed, onMounted, ref } from 'vue'
import { apiGetBatchState } from '@/api/assistant'
import type { AssistantCard, BatchItem } from '@/api/assistant'

interface Props {
  card: AssistantCard
}

const props = defineProps<Props>()
const emit = defineEmits<{
  start: [taskId: number, item: BatchItem]
  cancel: [taskId: number]
}>()

const taskId = computed(() => {
  const id = props.card.resource_refs?.task_id
  return typeof id === 'number' ? id : Number(id) || 0
})

const items = ref<BatchItem[]>([])
const currentItemId = ref<number | null>(null)
const loading = ref(false)

const totalItems = computed(() => {
  const total = props.card.resource_refs?.total_items
  return typeof total === 'number' ? total : items.value.length
})

const statusLabel: Record<string, string> = {
  pending: '待处理',
  searching_customer: '查找客户',
  waiting_customer: '等待客户确认',
  waiting_draft: '等待草稿确认',
  saving: '保存中',
  completed: '已保存',
  skipped: '已跳过',
  failed: '失败',
  cancelled: '已取消',
}

async function load(): Promise<void> {
  if (!taskId.value) return
  loading.value = true
  try {
    const state = await apiGetBatchState(taskId.value)
    items.value = state.items
    currentItemId.value = state.current_item_id
  } finally {
    loading.value = false
  }
}

function start(item: BatchItem): void {
  emit('start', taskId.value, item)
}

onMounted(load)
</script>

<template>
  <div class="batch-overview-card assistant-card">
    <div class="card-title">
      <strong>批量训练补记</strong>
      <el-tag size="small" type="info">共 {{ totalItems }} 项</el-tag>
    </div>
    <p class="card-hint">已按原文顺序拆分为 {{ totalItems }} 位客户，请逐项确认客户并保存。</p>

    <div v-loading="loading" class="item-list">
      <div v-for="item in items" :key="item.id" class="batch-item" :class="item.status">
        <span class="item-seq">第 {{ item.sequence }} 项</span>
        <span class="item-name">{{ item.customer_name || item.customer_name_hint }}</span>
        <el-tag size="small" :type="item.status === 'completed' ? 'success' : item.status === 'failed' ? 'danger' : 'warning'">
          {{ statusLabel[item.status] || item.status }}
        </el-tag>
        <el-button
          v-if="item.status !== 'completed' && item.status !== 'skipped'"
          size="small"
          type="primary"
          link
          @click="start(item)"
        >
          {{ currentItemId === item.id ? '继续处理' : '开始' }}
        </el-button>
      </div>
    </div>

    <div class="card-actions">
      <el-button link type="danger" @click="emit('cancel', taskId)">取消全部</el-button>
    </div>
  </div>
</template>

<style scoped>
.batch-overview-card { display: flex; flex-direction: column; gap: 10px; }
.card-title { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.card-title strong { color: var(--retrue-text); font-size: 14px; }
.card-hint { margin: 0; color: var(--retrue-text-secondary); font-size: 12px; }
.item-list { display: flex; flex-direction: column; gap: 6px; }
.batch-item { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; padding: 8px 10px; border: 1px solid var(--retrue-border); border-radius: var(--retrue-radius-sm); background: var(--retrue-bg); }
.item-seq { color: var(--retrue-text-muted); font-size: 12px; }
.item-name { flex: 1; min-width: 0; color: var(--retrue-text); font-size: 13px; font-weight: 600; }
.card-actions { display: flex; justify-content: flex-end; }
</style>
