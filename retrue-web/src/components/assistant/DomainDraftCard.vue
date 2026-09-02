<script setup lang="ts">
/**
 * 领域草稿卡片：评估 / 随访 / 训练修订草稿的通用展示与确认。
 * 所有操作先生成可审阅草稿，正式写入在确认后经领域服务完成。
 */

import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { apiCancelDraft, apiConfirmDraft, apiListDrafts } from '@/api/ai'
import type { AssistantCard } from '@/api/assistant'
import type { AiDraft, AiDraftResult } from '@/types/api'

interface Props {
  card: AssistantCard
  customerId: number | null
}

const props = defineProps<Props>()
const emit = defineEmits<{
  confirmed: [draft: AiDraft]
  cancelled: []
}>()

const draft = ref<AiDraft | null>(null)
const loading = ref(false)
const confirming = ref(false)

const draftId = computed(() => {
  const id = props.card.resource_refs?.draft_id
  return typeof id === 'number' ? id : Number(id) || null
})

const typeLabel = computed(() => {
  const type = props.card.resource_refs?.draft_type
  return ({ assessment: '评估草稿', followup: '随访草稿', training_revision: '训练修订草稿' } as Record<string, string>)[String(type)] || '待确认草稿'
})

const isConfirmed = computed(() => draft.value?.status === 'confirmed')

const fields = computed(() => {
  if (!draft.value?.ai_result) return []
  const result = draft.value.ai_result as Record<string, unknown>
  return Object.entries(result)
    .filter(([key, value]) => !['target_record_id', 'assessment_type'].includes(key) && value != null && value !== '')
    .map(([key, value]) => ({ key, value: String(value) }))
})

async function loadDraft(): Promise<void> {
  if (!draftId.value) return
  loading.value = true
  try {
    const drafts = await apiListDrafts()
    const found = drafts.find((item) => item.id === draftId.value)
    if (found) draft.value = found
  } catch {
    ElMessage.error('加载草稿失败，请稍后重试')
  } finally {
    loading.value = false
  }
}

async function confirm(): Promise<void> {
  if (!draft.value || isConfirmed.value || confirming.value) return
  if (!props.customerId) {
    ElMessage.warning('请先选择客户，再确认保存')
    return
  }
  confirming.value = true
  try {
    const result = await apiConfirmDraft(
      draft.value.id,
      props.customerId,
      (draft.value.ai_result ?? {}) as AiDraftResult,
    )
    draft.value = result
    ElMessage.success('已确认并写入正式记录')
    emit('confirmed', result)
  } finally {
    confirming.value = false
  }
}

async function cancel(): Promise<void> {
  if (!draft.value) return
  await apiCancelDraft(draft.value.id)
  ElMessage.info('草稿已取消')
  emit('cancelled')
}

void loadDraft()
</script>

<template>
  <div class="domain-draft-card assistant-card">
    <div class="card-title">
      <strong>{{ typeLabel }}</strong>
      <el-tag :type="isConfirmed ? 'success' : 'warning'" size="small">{{ isConfirmed ? '已保存' : '待你确认' }}</el-tag>
    </div>
    <p v-if="!isConfirmed" class="card-hint">请检查草稿内容，确认后才会正式写入；未确认前不会保存。</p>

    <div v-if="draft && fields.length" class="field-list">
      <div v-for="field in fields" :key="field.key" class="field-item">
        <span>{{ field.key }}</span>
        <b>{{ field.value }}</b>
      </div>
    </div>
    <el-empty v-else-if="draft && !fields.length" description="草稿暂无内容" :image-size="50" />

    <div v-if="!isConfirmed" class="card-actions">
      <el-button size="small" @click="cancel">取消</el-button>
      <el-button size="small" type="primary" :loading="confirming" @click="confirm">确认保存</el-button>
    </div>
  </div>
</template>

<style scoped>
.domain-draft-card { display: flex; flex-direction: column; gap: 10px; }
.card-title { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.card-title strong { color: var(--retrue-text); font-size: 14px; }
.card-hint { margin: 0; color: var(--retrue-text-secondary); font-size: 12px; }
.field-list { display: flex; flex-direction: column; gap: 6px; }
.field-item { display: flex; flex-direction: column; gap: 2px; padding: 8px 10px; border-radius: var(--retrue-radius-sm); background: var(--retrue-bg); }
.field-item span { color: var(--retrue-text-muted); font-size: 11px; }
.field-item b { color: var(--retrue-text); font-size: 13px; font-weight: 600; white-space: pre-wrap; }
.card-actions { display: flex; justify-content: flex-end; gap: 8px; }
</style>
