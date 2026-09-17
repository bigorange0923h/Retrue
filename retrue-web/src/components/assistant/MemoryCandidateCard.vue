<script setup lang="ts">
/**
 * 长期记忆候选卡片：只展示本轮服务端生成的候选，由康复师在聊天中决定是否正式生效。
 * 有冲突的候选必须选择冲突处置方式，不能绕过旧记忆直接确认。
 */

import { computed } from 'vue'
import type { AssistantCard, AssistantMemoryCandidate } from '@/api/assistant'

interface Props {
  card: AssistantCard
}

const props = defineProps<Props>()
const emit = defineEmits<{
  action: [action: string]
}>()

const candidates = computed(() => props.card.memory_candidates ?? [])
const hasPending = computed(() => candidates.value.some((candidate) => candidate.status === 'pending'))
const handledSummary = computed(() => {
  const counts = candidates.value.reduce<Record<string, number>>((result, candidate) => {
    result[candidate.status] = (result[candidate.status] || 0) + 1
    return result
  }, {})
  const parts: string[] = []
  if (counts.confirmed) parts.push(`已确认 ${counts.confirmed} 条`)
  if (counts.rejected) parts.push(`已拒绝 ${counts.rejected} 条`)
  if (counts.deferred) parts.push(`已移至稍后处理 ${counts.deferred} 条`)
  return parts.join('；') || '本轮候选已处理。'
})

/** 已处理候选的状态需要说明实际结果，避免“已确认”被理解为仍待人工确认。 */
function statusText(candidate: AssistantMemoryCandidate): string {
  const labels: Record<string, string> = {
    confirmed: '已确认并写入长期记忆',
    rejected: '已拒绝，不会写入长期记忆',
    deferred: '已移至稍后处理，不会进入 AI 上下文',
  }
  return labels[candidate.status] || candidate.status_display || candidate.status
}

/** 把候选操作编码为卡片事件，实际写入仍由父级调用既有受控接口。 */
function decide(candidate: AssistantMemoryCandidate, action: string): void {
  emit('action', `memory:${action}:${candidate.id}`)
}

function isPending(candidate: AssistantMemoryCandidate): boolean {
  return candidate.status === 'pending'
}
</script>

<template>
  <section :class="['memory-candidate-card', 'assistant-card', { handled: !hasPending }]">
    <div class="memory-heading">
      <strong>{{ hasPending ? '待确认长期记忆' : '长期记忆已处理' }}</strong>
      <span>{{ hasPending ? (card.notice || '请核对后处理。') : handledSummary }}</span>
    </div>

    <article v-for="candidate in candidates" :key="candidate.id" class="memory-item">
      <p class="memory-content">{{ candidate.content }}</p>
      <p class="memory-meta">
        {{ candidate.memory_type_display || '长期信息' }} · 可信度 {{ candidate.confidence }} · 重要度 {{ candidate.importance_score }}/5
      </p>
      <p v-if="candidate.evidence" class="memory-evidence">依据：{{ candidate.evidence }}</p>

      <div v-if="candidate.conflict_type === 'conflict'" class="memory-conflict">
        <strong>与现有有效记忆冲突</strong>
        <span v-if="candidate.conflict_memory_content">现有：{{ candidate.conflict_memory_content }}</span>
        <span v-else>{{ candidate.conflict_type_display }}</span>
      </div>

      <div v-if="isPending(candidate)" class="card-actions">
        <template v-if="candidate.conflict_type === 'conflict'">
          <el-button size="small" type="primary" @click="decide(candidate, 'replace')">替换旧记忆</el-button>
          <el-button size="small" @click="decide(candidate, 'keep_existing')">保留旧记忆</el-button>
          <el-button size="small" @click="decide(candidate, 'coexist')">条件并存</el-button>
        </template>
        <template v-else>
          <el-button size="small" type="primary" @click="decide(candidate, 'confirm')">确认写入</el-button>
          <el-button size="small" @click="decide(candidate, 'reject')">拒绝</el-button>
        </template>
        <el-button size="small" text @click="decide(candidate, 'defer')">稍后处理</el-button>
      </div>
      <p v-else class="memory-status">{{ statusText(candidate) }}</p>
    </article>
  </section>
</template>

<style scoped>
.memory-candidate-card { display: flex; flex-direction: column; gap: 10px; padding: 12px; border: 1px solid color-mix(in srgb, var(--retrue-primary) 38%, var(--retrue-border)); border-radius: var(--retrue-radius-md); background: color-mix(in srgb, var(--retrue-primary) 5%, var(--retrue-surface)); }
.memory-candidate-card.handled { border-color: color-mix(in srgb, var(--retrue-success, #67c23a) 40%, var(--retrue-border)); background: color-mix(in srgb, var(--retrue-success, #67c23a) 6%, var(--retrue-surface)); }
.memory-heading { display: flex; flex-wrap: wrap; align-items: baseline; gap: 8px; }
.memory-heading strong { color: var(--retrue-primary); font-size: 14px; }
.memory-heading span, .memory-meta, .memory-evidence, .memory-status { margin: 0; color: var(--retrue-text-muted); font-size: 12px; line-height: 1.5; }
.memory-item { display: flex; flex-direction: column; gap: 6px; padding-top: 10px; border-top: 1px solid var(--retrue-border); }
.memory-content { margin: 0; color: var(--retrue-text); font-size: 14px; line-height: 1.6; }
.memory-conflict { display: flex; flex-direction: column; gap: 3px; padding: 8px; border-radius: var(--retrue-radius-sm); background: color-mix(in srgb, var(--retrue-warning, #e6a23c) 12%, var(--retrue-surface)); color: var(--retrue-text-secondary); font-size: 12px; line-height: 1.5; }
.card-actions { display: flex; flex-wrap: wrap; gap: 8px; }
</style>
