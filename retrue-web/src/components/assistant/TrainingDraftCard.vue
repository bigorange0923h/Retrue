<script setup lang="ts">
/**
 * 训练补记草稿卡片：在聊天消息流内展示可编辑草稿并明确确认。
 * AI 永远只创建 pending 草稿；确认走既有正式确认 API，重复点击幂等安全。
 */

import { computed, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { apiCancelDraft, apiConfirmDraft, apiListDrafts } from '@/api/ai'
import type { AssistantCard } from '@/api/assistant'
import type { AiDraft, AiDraftResult } from '@/types/api'

interface Props {
  card: AssistantCard
  customerId: number | null
  courseSessionId?: number | null
}

const props = defineProps<Props>()
const emit = defineEmits<{
  confirmed: [draft: AiDraft]
  cancelled: []
  taskUpdated: [taskId: number]
}>()

const draft = ref<AiDraft | null>(null)
const loading = ref(false)
const confirming = ref(false)
const loaded = ref(false)

const draftId = computed(() => {
  const id = props.card.resource_refs?.draft_id
  return typeof id === 'number' ? id : Number(id) || null
})

const editForm = reactive<AiDraftResult>({
  training_date: '',
  customer_hint: null,
  exercises: [],
  customer_feedback: '',
  therapist_observation: '',
  next_plan: '',
})

const isConfirmed = computed(() => draft.value?.status === 'confirmed')

function hydrate(value: AiDraft): void {
  draft.value = value
  const result = value.ai_result || ({} as AiDraftResult)
  editForm.training_date = result.training_date || ''
  editForm.customer_hint = result.customer_hint || null
  editForm.exercises = (result.exercises || []).map((exercise, index) => ({ ...exercise, sort_order: index }))
  editForm.customer_feedback = result.customer_feedback || ''
  editForm.therapist_observation = result.therapist_observation || ''
  editForm.next_plan = result.next_plan || ''
}

async function loadDraft(): Promise<void> {
  if (loaded.value || !draftId.value) return
  loading.value = true
  try {
    const drafts = await apiListDrafts()
    const found = drafts.find((item) => item.id === draftId.value)
    if (found) hydrate(found)
    loaded.value = true
  } catch {
    ElMessage.error('加载草稿失败，请稍后重试')
  } finally {
    loading.value = false
  }
}

async function confirm(): Promise<void> {
  if (!draft.value || isConfirmed.value || confirming.value) return
  if (!props.customerId) {
    ElMessage.warning('请先选择客户，再确认训练记录')
    return
  }
  confirming.value = true
  try {
    const payload: AiDraftResult = {
      ...editForm,
      exercises: editForm.exercises.map((exercise, index) => ({ ...exercise, sort_order: index })),
    }
    const result = await apiConfirmDraft(draft.value.id, props.customerId, payload, props.courseSessionId)
    hydrate(result)
    ElMessage.success('已确认并创建训练记录')
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
  <div class="training-draft-card assistant-card">
    <div class="card-title">
      <strong>{{ isConfirmed ? '训练记录已确认' : '训练补记草稿' }}</strong>
      <el-tag :type="isConfirmed ? 'success' : 'warning'" size="small">{{ isConfirmed ? '已确认' : '待你确认' }}</el-tag>
    </div>
    <p v-if="!isConfirmed" class="card-hint">请逐项检查，确认后才会写入正式训练记录。</p>

    <div v-if="draft && !isConfirmed" class="draft-form">
      <div class="form-row">
        <span class="field-label">训练日期</span>
        <el-date-picker v-model="editForm.training_date" type="date" value-format="YYYY-MM-DD" class="full-width" />
      </div>
      <div v-if="editForm.exercises.length" class="exercise-list">
        <div v-for="(exercise, index) in editForm.exercises" :key="index" class="exercise-row">
          <el-input v-model="exercise.exercise_name" placeholder="动作名称" />
          <el-input-number v-model="exercise.sets" :min="0" placeholder="组" class="num" />
          <el-input-number v-model="exercise.reps" :min="0" placeholder="次" class="num" />
          <el-input v-model="exercise.weight" placeholder="重量/阻力" />
        </div>
      </div>
      <div class="form-row">
        <span class="field-label">客户感受</span>
        <el-input v-model="editForm.customer_feedback" type="textarea" :rows="2" />
      </div>
      <div class="form-row">
        <span class="field-label">下次计划</span>
        <el-input v-model="editForm.next_plan" type="textarea" :rows="2" />
      </div>
    </div>

    <div v-if="!isConfirmed" class="card-actions">
      <el-button size="small" :loading="loading" @click="loadDraft">刷新草稿</el-button>
      <el-button size="small" @click="cancel">取消</el-button>
      <el-button size="small" type="primary" :loading="confirming" @click="confirm">确认保存</el-button>
    </div>
  </div>
</template>

<style scoped>
.training-draft-card { display: flex; flex-direction: column; gap: 10px; }
.card-title { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.card-title strong { color: var(--retrue-text); font-size: 14px; }
.card-hint { margin: 0; color: var(--retrue-text-secondary); font-size: 12px; }
.draft-form { display: flex; flex-direction: column; gap: 10px; }
.form-row { display: flex; flex-direction: column; gap: 4px; }
.field-label { color: var(--retrue-text-muted); font-size: 12px; }
.full-width { width: 100%; }
.exercise-list { display: flex; flex-direction: column; gap: 6px; }
.exercise-row { display: flex; flex-wrap: wrap; gap: 6px; }
.exercise-row :deep(.el-input) { flex: 1 1 120px; }
.exercise-row .num { width: 90px; }
.card-actions { display: flex; justify-content: flex-end; gap: 8px; }
</style>
