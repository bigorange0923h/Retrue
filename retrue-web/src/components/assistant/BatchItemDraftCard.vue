<script setup lang="ts">
/**
 * 多客户批量训练补记的子项草稿卡片：展示/编辑单个客户的训练草稿，
 * 支持自动保存草稿、确认保存（正式写入并推进到下一项）与跳过。
 * 正式记录只有在康复师点击「确认保存」后才会写入。
 */

import { computed, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { apiConfirmBatchItem, apiSaveBatchItemDraft, apiSkipBatchItem } from '@/api/assistant'
import type { AssistantCard } from '@/api/assistant'
import type { AiDraftResult } from '@/types/api'

interface Props {
  card: AssistantCard
}

const props = defineProps<Props>()
const emit = defineEmits<{
  advance: [summary: unknown]
  skip: [summary: unknown]
}>()

const taskId = computed(() => {
  const id = props.card.resource_refs?.task_id
  return typeof id === 'number' ? id : Number(id) || 0
})
const itemId = computed(() => {
  const id = props.card.resource_refs?.item_id
  return typeof id === 'number' ? id : Number(id) || 0
})

const customerName = computed(() => {
  const name = props.card.resource_refs?.customer_name
  return typeof name === 'string' ? name : ''
})

const isCompleted = computed(() => props.card.status === 'completed')
const isSkipped = computed(() => props.card.status === 'cancelled')

const saving = ref(false)
const confirming = ref(false)
const skipping = ref(false)

const editForm = reactive<AiDraftResult>({
  training_date: '',
  customer_hint: null,
  exercises: [],
  customer_feedback: '',
  therapist_observation: '',
  next_plan: '',
})

function hydrate(result: AiDraftResult): void {
  editForm.training_date = result.training_date || ''
  editForm.customer_hint = result.customer_hint || null
  editForm.exercises = (result.exercises || []).map((exercise, index) => ({
    ...exercise,
    sort_order: index,
  }))
  editForm.customer_feedback = result.customer_feedback || ''
  editForm.therapist_observation = result.therapist_observation || ''
  editForm.next_plan = result.next_plan || ''
}

const initial = props.card.summary as unknown as AiDraftResult | undefined
if (initial) hydrate(initial)

function toPayload(): AiDraftResult {
  return {
    ...editForm,
    exercises: editForm.exercises.map((exercise, index) => ({ ...exercise, sort_order: index })),
  }
}

async function saveDraft(): Promise<void> {
  if (saving.value || confirming.value) return
  saving.value = true
  try {
    await apiSaveBatchItemDraft(taskId.value, itemId.value, toPayload() as unknown as Record<string, unknown>)
    ElMessage.success('草稿已保存')
  } catch {
    ElMessage.error('草稿保存失败，请稍后重试')
  } finally {
    saving.value = false
  }
}

async function confirm(): Promise<void> {
  if (confirming.value || saving.value) return
  confirming.value = true
  try {
    const result = await apiConfirmBatchItem(taskId.value, itemId.value, toPayload() as unknown as Record<string, unknown>)
    ElMessage.success('已保存此客户并继续')
    emit('advance', result.summary)
  } catch {
    ElMessage.error('保存失败，请稍后重试')
  } finally {
    confirming.value = false
  }
}

async function skip(): Promise<void> {
  if (skipping.value) return
  skipping.value = true
  try {
    const result = await apiSkipBatchItem(taskId.value, itemId.value)
    ElMessage.info('已跳过此项')
    emit('skip', result.summary)
  } catch {
    ElMessage.error('跳过失败，请稍后重试')
  } finally {
    skipping.value = false
  }
}
</script>

<template>
  <div class="batch-item-draft-card assistant-card">
    <div class="card-title">
      <strong>{{ isCompleted ? '训练记录已保存' : isSkipped ? '训练补记已跳过' : '训练补记草稿' }}{{ customerName ? ` · ${customerName}` : '' }}</strong>
      <el-tag :type="isCompleted ? 'success' : isSkipped ? 'info' : 'warning'" size="small">{{ isCompleted ? '已保存' : isSkipped ? '已跳过' : '待你确认' }}</el-tag>
    </div>
    <p v-if="!isCompleted && !isSkipped" class="card-hint">请逐项检查，确认保存后才会写入正式训练记录并进入下一位客户。</p>

    <div v-if="!isCompleted && !isSkipped" class="draft-form">
      <div class="form-row">
        <span class="field-label">训练日期</span>
        <el-date-picker v-model="editForm.training_date" type="date" value-format="YYYY-MM-DD" class="full-width" />
      </div>

      <div v-if="editForm.exercises.length" class="exercise-list">
        <div v-for="(exercise, index) in editForm.exercises" :key="index" class="exercise-row">
          <div class="exercise-head">
            <el-select v-model="exercise.activity_type" size="small" class="type-select">
              <el-option label="训练" value="exercise" />
              <el-option label="治疗" value="therapy" />
              <el-option label="按摩" value="massage" />
            </el-select>
            <el-input v-model="exercise.exercise_name" size="small" placeholder="动作名称" class="name-input" />
          </div>
          <div class="exercise-meta">
            <el-input-number v-model="exercise.sets" :min="0" placeholder="组" size="small" class="num" />
            <el-input-number v-model="exercise.reps" :min="0" placeholder="次" size="small" class="num" />
            <el-input-number v-model="exercise.quantity" :min="0" placeholder="数量" size="small" class="num" />
            <el-input v-model="exercise.unit" size="small" placeholder="单位" class="unit-input" />
          </div>
        </div>
      </div>
      <el-empty v-else description="未解析到训练动作" :image-size="60" />

      <div class="form-row">
        <span class="field-label">客户感受</span>
        <el-input v-model="editForm.customer_feedback" type="textarea" :rows="2" />
      </div>
      <div class="form-row">
        <span class="field-label">下次计划</span>
        <el-input v-model="editForm.next_plan" type="textarea" :rows="2" />
      </div>
    </div>

    <div v-if="!isCompleted && !isSkipped" class="card-actions">
      <el-button size="small" :loading="skipping" @click="skip">跳过此项</el-button>
      <el-button size="small" :loading="saving" @click="saveDraft">保存草稿</el-button>
      <el-button size="small" type="primary" :loading="confirming" @click="confirm">确认保存并继续</el-button>
    </div>
  </div>
</template>

<style scoped>
.batch-item-draft-card { display: flex; flex-direction: column; gap: 10px; }
.card-title { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.card-title strong { color: var(--retrue-text); font-size: 14px; }
.card-hint { margin: 0; color: var(--retrue-text-secondary); font-size: 12px; }
.draft-form { display: flex; flex-direction: column; gap: 10px; }
.form-row { display: flex; flex-direction: column; gap: 4px; }
.field-label { color: var(--retrue-text-muted); font-size: 12px; }
.full-width { width: 100%; }
.exercise-list { display: flex; flex-direction: column; gap: 8px; }
.exercise-row { display: flex; flex-direction: column; gap: 4px; padding: 8px; border: 1px solid var(--retrue-border); border-radius: var(--retrue-radius-sm); background: var(--retrue-bg); }
.exercise-head { display: flex; gap: 6px; }
.exercise-head .type-select { width: 90px; flex: none; }
.exercise-head .name-input { flex: 1; }
.exercise-meta { display: flex; flex-wrap: wrap; gap: 6px; }
.exercise-meta .num { width: 90px; }
.exercise-meta .unit-input { width: 80px; }
.card-actions { display: flex; justify-content: flex-end; gap: 8px; }
</style>
