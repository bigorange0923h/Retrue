<script setup lang="ts">
/** 领域候选的中文摘要与编辑；评估确认仅创建评估草稿。 */
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { apiCancelDraft, apiConfirmDraft, apiGetDraft } from '@/api/ai'
import type { AssistantCard } from '@/api/assistant'
import type { AiDraft } from '@/types/api'

const props = defineProps<{ card: AssistantCard; customerId: number | null }>()
const emit = defineEmits<{ confirmed: [draft: AiDraft]; cancelled: [] }>()
const router = useRouter()
const draft = ref<AiDraft | null>(null)
const loading = ref(false)
const confirming = ref(false)
const cancelling = ref(false)
const loadError = ref('')
const editing = ref(false)
const editForm = ref<Record<string, string>>({})
const draftId = computed(() => Number(props.card.resource_refs?.draft_id) || null)
const draftType = computed(() => draft.value?.draft_type || String(props.card.resource_refs?.draft_type || ''))
const isAssessment = computed(() => draftType.value === 'assessment')
const isConfirmed = computed(() => draft.value?.status === 'confirmed')
const isPending = computed(() => draft.value?.status === 'pending')
const busy = computed(() => loading.value || confirming.value || cancelling.value)
const typeLabels: Record<string, string> = { assessment: '评估内容', followup: '随访内容', training_revision: '训练修订' }
const typeLabel = computed(() => typeLabels[draftType.value] || '待确认内容')
const statusLabels: Record<string, string> = { pending: '待核对', cancelled: '已取消', failed: '整理失败' }
const statusLabel = computed(() => isConfirmed.value ? (isAssessment.value ? '已存为评估草稿' : '已保存') : (statusLabels[draft.value?.status || ''] || '正在加载'))

interface DraftField { key: string; label: string; type?: 'date' | 'followup_type' }
const fieldDefinitions: Record<string, DraftField[]> = {
  assessment: [
    { key: 'assessment_date', label: '评估日期', type: 'date' },
    { key: 'chief_complaint', label: '本次主要问题' },
    { key: 'medical_history', label: '既往相关情况' },
    { key: 'rehab_goal', label: '康复目标' },
    { key: 'current_status', label: '当前状态' },
    { key: 'note', label: '补充备注' },
  ],
  followup: [
    { key: 'followup_type', label: '随访类型', type: 'followup_type' },
    { key: 'due_date', label: '计划日期', type: 'date' },
    { key: 'content', label: '随访内容' },
  ],
  training_revision: [
    { key: 'customer_feedback', label: '客户感受' },
    { key: 'therapist_observation', label: '康复师观察' },
    { key: 'next_plan', label: '下次计划' },
    { key: 'note', label: '补充备注' },
  ],
}
const fields = computed(() => fieldDefinitions[draftType.value] || [])
const hasDefaultDate = computed(() => isPending.value && fields.value.some(field => field.type === 'date' && !editForm.value[field.key]))
const assessmentRoute = computed(() => draft.value?.assessment ? { name: 'assessment-revise', params: { id: draft.value.assessment } } : null)

function hydrate(result: AiDraft): void {
  draft.value = result
  const values = (result.status === 'confirmed' ? result.confirmed_result : result.ai_result) as unknown as Record<string, unknown>
  editForm.value = Object.fromEntries(fields.value.map(field => [field.key, typeof values[field.key] === 'string' ? values[field.key] : ''])) as Record<string, string>
}
function displayValue(field: DraftField): string {
  const value = editForm.value[field.key] || ''
  const followupLabels: Record<string, string> = { visit: '回访', review: '复查', other: '其他' }
  return field.type === 'followup_type' ? (followupLabels[value] || value || '尚未记录') : (value || '尚未记录')
}
async function loadDraft(): Promise<void> {
  loading.value = true
  loadError.value = ''
  try {
    if (!draftId.value) throw new Error('missing draft')
    hydrate(await apiGetDraft(draftId.value))
  } catch {
    loadError.value = '暂时无法加载内容，请重试'
  } finally {
    loading.value = false
  }
}
async function confirm(): Promise<void> {
  if (!draft.value || !isPending.value || busy.value || !fields.value.length) return
  if (!props.customerId || (draft.value.customer && draft.value.customer !== props.customerId)) {
    ElMessage.warning('请先选择这份草稿对应的客户')
    return
  }
  confirming.value = true
  try {
    const result = await apiConfirmDraft(draft.value.id, props.customerId, { ...draft.value.ai_result, ...editForm.value })
    hydrate(result)
    editing.value = false
    ElMessage.success(isAssessment.value ? '已存为评估草稿，请继续补充并完成评估' : '已确认保存')
    emit('confirmed', result)
  } finally {
    confirming.value = false
  }
}
async function cancel(): Promise<void> {
  if (!draft.value || !isPending.value || busy.value) return
  cancelling.value = true
  try {
    hydrate(await apiCancelDraft(draft.value.id))
    editing.value = false
    ElMessage.info('草稿已取消')
    emit('cancelled')
  } finally {
    cancelling.value = false
  }
}
void loadDraft()
</script>

<template>
  <div v-loading="loading" class="domain-draft-card assistant-card">
    <div class="card-title">
      <strong>{{ typeLabel }}</strong>
      <el-tag :type="isConfirmed ? (isAssessment ? 'warning' : 'success') : 'info'" size="small">{{ statusLabel }}</el-tag>
    </div>
    <p v-if="draft?.customer_name" class="card-hint">客户：{{ draft.customer_name }}</p>
    <p v-if="isPending" class="card-hint">{{ isAssessment ? '核对内容后保存为评估草稿，开始时间和客观指标可继续补充；尚未完成评估。' : '核对或修改下面的内容，确认后保存。' }}</p>
    <p v-if="isConfirmed && isAssessment" class="card-hint">本卡片已存为评估草稿。请进入评估页查看最新状态，补充后完成评估。</p>
    <p v-if="hasDefaultDate" class="card-hint">日期尚未指定，保存时会预填当天；可在“修改内容”中选择实际日期。</p>
    <div v-if="loadError" class="load-error" role="alert"><span>{{ loadError }}</span><el-button text type="primary" :disabled="busy" @click="loadDraft">重试</el-button></div>
    <p v-if="draft?.status === 'failed'" class="card-hint">{{ draft.error_message || '整理失败，请重新提供描述' }}</p>

    <el-form v-if="draft && editing && isPending" label-position="top" :disabled="busy">
      <el-form-item v-for="field in fields" :key="field.key" :label="field.label">
        <el-date-picker v-if="field.type === 'date'" v-model="editForm[field.key]" type="date" value-format="YYYY-MM-DD" placeholder="选择实际日期" class="full-width" />
        <el-select v-else-if="field.type === 'followup_type'" v-model="editForm[field.key]" class="full-width">
          <el-option label="回访" value="visit" /><el-option label="复查" value="review" /><el-option label="其他" value="other" />
        </el-select>
        <el-input v-else v-model="editForm[field.key]" type="textarea" :rows="2" placeholder="尚未记录，可补充" maxlength="5000" />
      </el-form-item>
      <p class="card-hint">修改将在下方保存时一起提交。</p>
    </el-form>
    <div v-else-if="draft && fields.length" class="field-list">
      <div v-for="field in fields" :key="field.key" class="field-item">
        <span>{{ field.label }}</span><b :class="{ empty: !editForm[field.key] }">{{ displayValue(field) }}</b>
      </div>
    </div>
    <div v-if="isPending" class="card-actions">
      <el-button size="small" :disabled="busy" :loading="cancelling" @click="cancel">取消</el-button>
      <el-button size="small" :disabled="busy" @click="editing = !editing">{{ editing ? '收起编辑' : '修改内容' }}</el-button>
      <el-button size="small" type="primary" :loading="confirming" :disabled="busy || !fields.length" @click="confirm">{{ isAssessment ? '保存为评估草稿' : '确认保存' }}</el-button>
    </div>
    <el-button v-if="isConfirmed && assessmentRoute" type="primary" size="small" @click="router.push(assessmentRoute)">继续评估 / 查看状态</el-button>
  </div>
</template>

<style scoped>
.domain-draft-card { display: flex; flex-direction: column; gap: 10px; }
.card-title { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.card-title strong { color: var(--retrue-text); font-size: 14px; }
.card-hint { margin: 0; color: var(--retrue-text-secondary); font-size: 12px; line-height: 1.6; }
.field-list { display: flex; flex-direction: column; gap: 6px; }
.field-item { display: flex; flex-direction: column; gap: 2px; padding: 8px 10px; border-radius: var(--retrue-radius-sm); background: var(--retrue-bg); }
.field-item span { color: var(--retrue-text-muted); font-size: 11px; }
.field-item b { color: var(--retrue-text); font-size: 13px; font-weight: 500; white-space: pre-wrap; overflow-wrap: anywhere; }
.field-item .empty { color: var(--retrue-text-muted); }
.card-actions { display: flex; justify-content: flex-end; flex-wrap: wrap; gap: 8px; }
.full-width { width: 100%; }
.load-error { display: flex; align-items: center; gap: 8px; color: var(--el-color-danger); font-size: 13px; }
</style>
