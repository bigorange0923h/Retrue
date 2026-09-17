<script setup lang="ts">
/**
 * 客户详情内的长期记忆管理：集中展示待审核候选与已存储记忆。
 * 候选处理和条目启停均复用知识库既有受控接口，AI 不会在此直接写入记忆。
 */

import { computed, onMounted, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  apiDecideKnowledgeCandidate,
  apiDeleteKnowledgeItem,
  apiListKnowledgeCandidates,
  apiListKnowledgeItems,
  apiUpdateKnowledgeItem,
} from '@/api/knowledge'
import type { KnowledgeCandidate, KnowledgeItem } from '@/types/api'

const props = defineProps<{ customerId: number }>()

const candidates = ref<KnowledgeCandidate[]>([])
const memories = ref<KnowledgeItem[]>([])
const loading = ref(false)
const pendingCandidates = computed(() => candidates.value.filter((item) => ['pending', 'deferred'].includes(item.status)))
const storedMemories = computed(() => memories.value.filter((item) => item.status !== 'deleted'))

function tagType(category: string): 'danger' | 'warning' | 'success' | 'info' {
  return ({ safety: 'danger', medical: 'warning', recovery: 'success', preference: 'info' } as Record<string, 'danger' | 'warning' | 'success' | 'info'>)[category] || 'info'
}

async function load(): Promise<void> {
  loading.value = true
  try {
    const [candidateResult, itemResult] = await Promise.all([
      apiListKnowledgeCandidates(props.customerId, 'open'),
      apiListKnowledgeItems(props.customerId),
    ])
    candidates.value = candidateResult
    memories.value = itemResult
  } finally {
    loading.value = false
  }
}

async function decide(candidate: KnowledgeCandidate, action: 'confirm' | 'reject' | 'replace' | 'keep_existing' | 'coexist' | 'defer'): Promise<void> {
  const labels = {
    confirm: '确认写入', reject: '拒绝候选', replace: '替换旧记忆',
    keep_existing: '保留旧记忆', coexist: '条件并存', defer: '稍后处理',
  }
  if (action !== 'defer') {
    try {
      await ElMessageBox.confirm(
        ['confirm', 'replace', 'coexist'].includes(action)
          ? '确认后该信息将成为客户有效长期记忆，并可用于后续 AI 建议。'
          : '处理后该候选不会成为有效长期记忆。',
        `确认${labels[action]}？`,
        { confirmButtonText: '确认', cancelButtonText: '取消', type: 'warning' },
      )
    } catch {
      return
    }
  }
  await apiDecideKnowledgeCandidate(candidate.id, action)
  ElMessage.success(action === 'defer' ? '已移至稍后处理列表' : `已${labels[action]}`)
  await load()
}

async function toggleMemory(item: KnowledgeItem): Promise<void> {
  await apiUpdateKnowledgeItem(item.id, { is_active: !item.is_active })
  ElMessage.success(item.is_active ? '记忆已停用，不会进入 AI 上下文' : '记忆已启用')
  await load()
}

async function removeMemory(item: KnowledgeItem): Promise<void> {
  try {
    await ElMessageBox.confirm('删除后不会再进入 AI 上下文，但会保留审计与来源追溯。', '确认删除这条记忆？', {
      confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning',
    })
  } catch {
    return
  }
  await apiDeleteKnowledgeItem(item.id)
  ElMessage.success('记忆已删除')
  await load()
}

watch(() => props.customerId, () => void load())
onMounted(() => void load())
</script>

<template>
  <section v-loading="loading" class="memory-manager">
    <div class="memory-manager-head">
      <div>
        <h3>客户长期记忆</h3>
        <p>仅已确认且启用的记忆会进入后续 AI 上下文。</p>
      </div>
      <el-button size="small" @click="load">刷新</el-button>
    </div>

    <div class="memory-section">
      <div class="section-title">
        <strong>待审核与稍后处理</strong>
        <el-tag type="warning" size="small">{{ pendingCandidates.length }}</el-tag>
      </div>
      <el-empty v-if="pendingCandidates.length === 0" description="暂无待处理记忆候选" :image-size="56" />
      <article v-for="candidate in pendingCandidates" :key="candidate.id" class="candidate-row">
        <div class="memory-row-main">
          <div class="row-tags">
            <el-tag :type="tagType(candidate.category)" size="small">{{ candidate.category_display }}</el-tag>
            <el-tag v-if="candidate.status === 'deferred'" type="info" size="small">稍后处理</el-tag>
          </div>
          <p>{{ candidate.content }}</p>
          <small>依据：{{ candidate.evidence || candidate.source_ref || 'AI 建议' }} · 可信度 {{ candidate.confidence }}</small>
          <div v-if="candidate.conflict_type === 'conflict'" class="conflict-box">
            与现有记忆冲突：{{ candidate.conflict_memory_content || '请手动核对' }}
          </div>
        </div>
        <div class="row-actions">
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
      </article>
    </div>

    <el-divider />

    <div class="memory-section">
      <div class="section-title">
        <strong>已存储记忆</strong>
        <el-tag type="success" size="small">{{ storedMemories.length }}</el-tag>
      </div>
      <el-empty v-if="storedMemories.length === 0" description="暂无已存储长期记忆" :image-size="56" />
      <article v-for="memory in storedMemories" :key="memory.id" class="memory-row">
        <div class="memory-row-main">
          <div class="row-tags">
            <el-tag :type="tagType(memory.category)" size="small">{{ memory.category_display }}</el-tag>
            <el-tag :type="memory.is_active ? 'success' : 'info'" size="small">{{ memory.is_active ? '生效中' : memory.status_display }}</el-tag>
          </div>
          <p>{{ memory.content }}</p>
          <small>来源：{{ memory.source || '人工确认' }} · 可信度 {{ memory.confidence }}</small>
        </div>
        <div class="row-actions">
          <el-button size="small" :type="memory.is_active ? 'warning' : 'success'" @click="toggleMemory(memory)">
            {{ memory.is_active ? '停用' : '启用' }}
          </el-button>
          <el-button size="small" type="danger" plain @click="removeMemory(memory)">删除</el-button>
        </div>
      </article>
    </div>
  </section>
</template>

<style scoped>
.memory-manager { display: flex; flex-direction: column; gap: 12px; }
.memory-manager-head, .section-title, .row-tags, .row-actions { display: flex; align-items: center; gap: 8px; }
.memory-manager-head { justify-content: space-between; }
.memory-manager h3 { margin: 0; font-size: 16px; }
.memory-manager-head p, .memory-row-main p, .memory-row-main small { margin: 0; }
.memory-manager-head p, .memory-row-main small { color: var(--retrue-text-muted); font-size: 12px; line-height: 1.5; }
.memory-section { display: flex; flex-direction: column; gap: 10px; }
.candidate-row, .memory-row { display: flex; justify-content: space-between; gap: 16px; padding: 12px; border: 1px solid var(--retrue-border); border-radius: var(--retrue-radius-md); background: var(--retrue-surface); }
.candidate-row { border-color: color-mix(in srgb, var(--retrue-warning, #e6a23c) 45%, var(--retrue-border)); }
.memory-row-main { display: flex; min-width: 0; flex: 1; flex-direction: column; gap: 6px; }
.memory-row-main p { color: var(--retrue-text); font-size: 14px; line-height: 1.6; }
.row-actions { flex-wrap: wrap; align-content: flex-start; justify-content: flex-end; }
.conflict-box { padding: 7px 8px; border-radius: var(--retrue-radius-sm); background: color-mix(in srgb, var(--retrue-warning, #e6a23c) 12%, var(--retrue-surface)); color: var(--retrue-text-secondary); font-size: 12px; line-height: 1.5; }
@media (max-width: 720px) { .candidate-row, .memory-row { flex-direction: column; } .row-actions { justify-content: flex-start; } }
</style>
