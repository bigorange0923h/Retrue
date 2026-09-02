<script setup lang="ts">
/**
 * 客户选择卡片：同名客户或未绑定客户时展示候选，绝不自动猜测。
 * 选择后通过父组件调用 /customer-selection/，以服务端任务状态为准。
 */

import { computed } from 'vue'
import type { AssistantCard } from '@/api/assistant'
import type { AssistantCustomerMatch } from '@/types/api'

interface Props {
  card: AssistantCard
  selecting?: boolean
}

const props = defineProps<Props>()
const emit = defineEmits<{
  select: [candidate: AssistantCustomerMatch]
  cancel: []
}>()

const candidates = computed(() => props.card.customer_candidates ?? [])
const hasCandidates = computed(() => candidates.value.length > 0)
</script>

<template>
  <div class="customer-selection-card assistant-card">
    <div class="card-title">
      <strong>{{ hasCandidates ? '请选择客户' : '请补充客户姓名' }}</strong>
      <span v-if="hasCandidates">找到 {{ candidates.length }} 位客户，同名客户需要你确认具体档案。</span>
      <span v-else>请告诉我客户姓名，我来帮你定位档案。</span>
    </div>
    <div v-if="hasCandidates" class="candidate-list">
      <button
        v-for="candidate in candidates"
        :key="candidate.id"
        type="button"
        class="candidate-item"
        :disabled="selecting"
        @click="emit('select', candidate)"
      >
        <span class="candidate-main">
          <b>{{ candidate.name }}</b>
          <span class="candidate-phone">{{ candidate.phone_masked || '无手机号' }}</span>
        </span>
        <span v-if="candidate.gender" class="candidate-meta">{{ candidate.gender }}</span>
        <span v-if="candidate.main_issue" class="candidate-issue">{{ candidate.main_issue }}</span>
      </button>
    </div>
    <div class="card-actions">
      <el-button link type="danger" @click="emit('cancel')">取消</el-button>
    </div>
  </div>
</template>

<style scoped>
.customer-selection-card { display: flex; flex-direction: column; gap: 10px; }
.card-title { display: flex; flex-direction: column; gap: 3px; }
.card-title strong { color: var(--retrue-text); font-size: 14px; }
.card-title span { color: var(--retrue-text-secondary); font-size: 12px; }
.candidate-list { display: flex; flex-direction: column; gap: 6px; }
.candidate-item { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; width: 100%; padding: 9px 12px; border: 1px solid var(--retrue-border); border-radius: var(--retrue-radius-sm); background: var(--retrue-surface); color: var(--retrue-text); text-align: left; cursor: pointer; }
.candidate-item:hover { border-color: var(--retrue-primary); }
.candidate-main { display: flex; align-items: center; gap: 8px; }
.candidate-phone { color: var(--retrue-text-muted); font-size: 12px; }
.candidate-meta, .candidate-issue { color: var(--retrue-text-secondary); font-size: 12px; }
.card-actions { display: flex; justify-content: flex-end; }
</style>
