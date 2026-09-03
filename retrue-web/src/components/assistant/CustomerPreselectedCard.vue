<script setup lang="ts">
/**
 * 客户预选卡片：系统据原文在康复师目录中唯一精确命中客户，已据此生成待确认草稿。
 * 展示预选客户供核对；「确认」接受该客户并收起，不改变任务生命周期
 * （正式保存仍由草稿卡的人工确认完成）。若不是此客户，引导在下方草稿中调整或告知正确姓名。
 */

import { computed } from 'vue'
import type { AssistantCard } from '@/api/assistant'

interface Props {
  card: AssistantCard
}

const props = defineProps<Props>()
const emit = defineEmits<{
  confirmed: []
}>()

const isResolved = computed(() => props.card.status === 'completed' || props.card.status === 'cancelled')
const customerName = computed(() => String(props.card.resource_refs?.customer_name || ''))
const gender = computed(() => String(props.card.resource_refs?.gender || ''))
const notice = computed(() => props.card.notice || '')
</script>

<template>
  <div class="customer-preselected-card assistant-card">
    <div class="card-head">
      <span class="tag">已识别客户</span>
      <el-tag v-if="isResolved" type="success" size="small">已确认</el-tag>
    </div>
    <div v-if="!isResolved" class="preselected-body">
      <div class="preselected-customer">
        <b>{{ customerName || '所选客户' }}</b>
        <span v-if="gender" class="customer-meta">{{ gender }}</span>
      </div>
      <p class="card-notice">{{ notice }}</p>
      <p class="card-hint">草稿已据此客户生成，待你核对并确认保存后才会写入正式训练记录。</p>
    </div>
    <div v-else class="preselected-body">
      <div class="preselected-customer">
        <b>{{ customerName || '所选客户' }}</b>
      </div>
      <p class="card-hint">已确认客户，可在下方草稿卡片继续编辑或保存。</p>
    </div>
    <div v-if="!isResolved" class="card-actions">
      <el-button size="small" type="primary" @click="emit('confirmed')">确认，继续编辑草稿</el-button>
    </div>
  </div>
</template>

<style scoped>
.customer-preselected-card { display: flex; flex-direction: column; gap: 10px; }
.card-head { display: flex; align-items: center; justify-content: space-between; }
.card-head .tag { color: var(--retrue-text); font-size: 14px; font-weight: 600; }
.preselected-body { display: flex; flex-direction: column; gap: 6px; }
.preselected-customer { display: flex; align-items: center; gap: 8px; padding: 9px 12px; border: 1px solid var(--retrue-border); border-radius: var(--retrue-radius-sm); background: var(--retrue-surface); }
.preselected-customer b { color: var(--retrue-text); font-size: 14px; }
.customer-meta { color: var(--retrue-text-secondary); font-size: 12px; }
.card-notice { margin: 0; color: var(--retrue-text-secondary); font-size: 12px; }
.card-hint { margin: 0; color: var(--retrue-text-muted); font-size: 12px; }
.card-actions { display: flex; justify-content: flex-end; }
</style>
