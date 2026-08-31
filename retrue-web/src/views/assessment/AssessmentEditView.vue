<script setup lang="ts">
/**
 * 引导式评估编辑页。
 *
 * 页面级表单是唯一编辑状态，子组件只负责当前步骤的展示和录入；
 * 满分、单位、量表和完成校验由服务端规则决定，前端不提供可编辑满分。
 */

import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { onBeforeRouteLeave, useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'

import {
  apiCompleteAssessment,
  apiCreateAssessment,
  apiGetAssessment,
  apiGetMetricDefinitions,
  apiListAssessments,
  apiUpdateAssessment,
  toAssessmentMetricInput,
  type AssessmentForm,
} from '@/api/assessments'
import { apiGetCustomer } from '@/api/customers'
import type {
  Assessment,
  AssessmentMetric,
  AssessmentMetricDefinition,
  AssessmentMetricInput,
  MetricType,
} from '@/types/api'
import AssessmentStepper from '@/components/assessment/AssessmentStepper.vue'
import AssessmentProblemStep from '@/components/assessment/AssessmentProblemStep.vue'
import AssessmentSubjectiveStep from '@/components/assessment/AssessmentSubjectiveStep.vue'
import AssessmentMetricsStep from '@/components/assessment/AssessmentMetricsStep.vue'
import AssessmentGoalStep from '@/components/assessment/AssessmentGoalStep.vue'
import AssessmentReviewStep from '@/components/assessment/AssessmentReviewStep.vue'

const route = useRoute()
const router = useRouter()

const routeAssessmentId = Number(route.params.id || 0) || null
const routeCustomerId = Number(route.query.customerId || route.params.customerId || 0) || 0
const initialFlow = route.query.mode === 'initial' && !routeAssessmentId

const loading = ref(false)
const initialized = ref(false)
const dirty = ref(false)
const leaveConfirmed = ref(false)
const syncingSavedRoute = ref(false)
const currentStep = ref(0)
const savingAction = ref<'draft' | 'complete' | ''>('')
const currentAssessmentId = ref<number | null>(routeAssessmentId)
const customerName = ref('')
const missingItems = ref<string[]>([])
const metricDefinitions = ref<AssessmentMetricDefinition[]>([])
const previousMetricTemplates = ref<AssessmentMetricInput[]>([])
const previousAssessmentDate = ref('')

const steps = ['本次问题', '主观情况', '客观评估', '目标与备注', '检查并完成']

const form = reactive<AssessmentForm>({
  customer: routeCustomerId,
  assessment_type: route.query.mode === 'reassessment' ? 'reassessment' : 'initial',
  assessment_date: '',
  status: 'draft',
  onset_date: null,
  onset_description: '',
  onset_mode: 'unknown',
  chief_complaint: '',
  medical_history: '',
  aggravating_factors: '',
  relieving_factors: '',
  prior_care: '',
  surgery_history: '',
  medication: '',
  exercise_habits: '',
  work_demands: '',
  sleep_impact: '',
  rehab_goal: '',
  current_status: '',
  note: '',
  metrics: [],
})

const isEditing = computed(() => currentAssessmentId.value !== null)
const isAssessmentTypeLocked = computed(() => isEditing.value || initialFlow || form.assessment_type === 'initial')
const isBusy = computed(() => savingAction.value !== '')

function emptyMetric(metricType: MetricType): AssessmentMetricInput {
  return {
    metric_type: metricType,
    body_part: '',
    score: null,
    description: '',
    sort_order: 0,
    side: '',
    scale_code: '',
    unit: '',
    context: '',
    movement: '',
    measurement_mode: '',
    result_code: '',
    details: {},
  }
}

function metricInput(metric: AssessmentMetric): AssessmentMetricInput {
  const input = toAssessmentMetricInput(metric)
  return {
    ...emptyMetric(metric.metric_type),
    ...input,
    details: metric.details ? { ...metric.details } : {},
  }
}

function hydrateAssessment(assessment: Assessment): void {
  form.customer = assessment.customer
  form.assessment_type = assessment.assessment_type
  form.assessment_date = assessment.assessment_date
  form.status = assessment.status || 'completed'
  form.onset_date = assessment.onset_date || null
  form.onset_description = assessment.onset_description || ''
  form.onset_mode = assessment.onset_mode || 'unknown'
  form.chief_complaint = assessment.chief_complaint || ''
  form.medical_history = assessment.medical_history || ''
  form.aggravating_factors = assessment.aggravating_factors || ''
  form.relieving_factors = assessment.relieving_factors || ''
  form.prior_care = assessment.prior_care || ''
  form.surgery_history = assessment.surgery_history || ''
  form.medication = assessment.medication || ''
  form.exercise_habits = assessment.exercise_habits || ''
  form.work_demands = assessment.work_demands || ''
  form.sleep_impact = assessment.sleep_impact || ''
  form.rehab_goal = assessment.rehab_goal || ''
  form.current_status = assessment.current_status || ''
  form.note = assessment.note || ''
  form.metrics = (assessment.metrics || []).map((metric, index) => ({ ...metricInput(metric), sort_order: index }))
  customerName.value = assessment.customer_name || customerName.value
  dirty.value = false
}

async function loadMetricDefinitions(): Promise<void> {
  try {
    const response = await apiGetMetricDefinitions()
    // 兼容后端在统一响应 data 中返回数组或 { definitions: [] } 的实现。
    const maybeWrapped = response as unknown as AssessmentMetricDefinition[] | { definitions?: AssessmentMetricDefinition[] }
    metricDefinitions.value = Array.isArray(maybeWrapped) ? maybeWrapped : (maybeWrapped.definitions || [])
  } catch {
    // 定义接口不可用时，编辑器仍使用稳定的内置临床文案；范围校验仍以服务端为准。
    metricDefinitions.value = []
  }
}

async function loadForEdit(): Promise<void> {
  if (!routeAssessmentId) return
  const assessment = await apiGetAssessment(routeAssessmentId)
  hydrateAssessment(assessment)
}

async function loadCustomerName(): Promise<void> {
  if (!routeCustomerId || routeAssessmentId) return
  try {
    const customer = await apiGetCustomer(routeCustomerId)
    customerName.value = customer.name
  } catch {
    // 客户名称不是提交评估的必要条件，保留客户 ID 供页面继续工作。
  }
}

/** 新建复评时提供上一次已完成评估的同类项目结构，结果值必须重新测量。 */
async function loadPreviousMetricTemplates(): Promise<void> {
  if (routeAssessmentId || form.assessment_type !== 'reassessment' || !routeCustomerId) return
  const assessments = await apiListAssessments(routeCustomerId)
  const previous = assessments.find((item) => item.status === 'completed')
  if (!previous) return

  previousAssessmentDate.value = previous.assessment_date
  previousMetricTemplates.value = previous.metrics.map((metric, index) => {
    const template = metricInput(metric)
    const details = { ...(template.details || {}) }
    if (metric.metric_type === 'functional') delete details.pain_status
    return {
      ...template,
      score: null,
      result_code: '',
      description: '',
      details,
      sort_order: index,
    }
  })
}

function validateMetric(metric: AssessmentMetricInput, index: number): string | null {
  const position = `第 ${index + 1} 个评估项目`
  if (!metric.metric_type) return `${position}缺少项目类型`

  if (metric.metric_type === 'pain') {
    if (!metric.body_part.trim()) return `${position}请填写疼痛部位`
    if (!metric.side) return `${position}请选择疼痛侧别`
    if (!metric.context) return `${position}请选择疼痛出现的场景`
    if (metric.score === null || metric.score === undefined || !Number.isInteger(Number(metric.score)) || Number(metric.score) < 0 || Number(metric.score) > 10) {
      return `${position}请填写 0～10 的整数疼痛程度`
    }
  }

  if (metric.metric_type === 'strength') {
    if (!metric.body_part.trim()) return `${position}请填写肌群或部位`
    if (!metric.side) return `${position}请选择肌力侧别`
    if (!metric.movement?.trim()) return `${position}请填写肌力动作`
    if (metric.score === null || metric.score === undefined || !Number.isInteger(Number(metric.score)) || Number(metric.score) < 0 || Number(metric.score) > 5) {
      return `${position}请选择 0～5 的肌力等级`
    }
  }

  if (metric.metric_type === 'rom') {
    if (!metric.body_part.trim()) return `${position}请填写关节或部位`
    if (!metric.side) return `${position}请选择活动度侧别`
    if (!metric.movement?.trim()) return `${position}请填写动作方向`
    if (!metric.measurement_mode) return `${position}请选择主动或被动测量方式`
    if (metric.score === null || metric.score === undefined || Number.isNaN(Number(metric.score))) return `${position}请填写测量角度`
  }

  if (metric.metric_type === 'special_test') {
    const testName = typeof metric.details?.test_name === 'string' ? metric.details.test_name.trim() : ''
    if (!testName) return `${position}请填写测试名称`
    if (!metric.result_code) return `${position}请选择测试结果`
  }

  if (metric.metric_type === 'functional') {
    if (!metric.movement?.trim()) return `${position}请填写动作名称`
    if (!metric.result_code) return `${position}请选择动作完成情况`
  }

  return null
}

function validateStep(step: number, showMessage = true): boolean {
  let message = ''
  if (step === 0) {
    if (!form.customer || form.customer <= 0) message = '当前评估没有绑定有效客户，请从客户档案进入'
    else if (!form.assessment_date) message = '请选择评估日期'
    else if (!form.chief_complaint?.trim()) message = '请填写本次最困扰的问题或不适部位'
    else if (!form.onset_date && !form.onset_description?.trim()) message = '请填写症状开始日期，或补充大致开始时间'
  } else if (step === 2) {
    if (form.metrics.length === 0) message = '请至少添加一个客观评估项目'
    else message = form.metrics.map(validateMetric).find(Boolean) || ''
  } else if (step === 3) {
    if (!form.rehab_goal?.trim()) message = '请填写康复目标'
  }

  if (message && showMessage) ElMessage.warning(message)
  return !message
}

function validateForComplete(): boolean {
  missingItems.value = []
  if (!form.customer || form.customer <= 0) missingItems.value.push('未绑定有效客户')
  if (!form.assessment_date) missingItems.value.push('未填写评估日期')
  if (!form.chief_complaint?.trim()) missingItems.value.push('未填写本次最困扰的问题或不适部位')
  if (!form.onset_date && !form.onset_description?.trim()) missingItems.value.push('未填写症状开始日期或大致时间')
  if (form.metrics.length === 0) missingItems.value.push('至少添加一个客观评估项目')
  form.metrics.forEach((metric, index) => {
    const message = validateMetric(metric, index)
    if (message) missingItems.value.push(message)
  })
  if (!form.rehab_goal?.trim()) missingItems.value.push('未填写康复目标')
  return missingItems.value.length === 0
}

function cleanMetric(metric: AssessmentMetricInput, index: number): AssessmentMetricInput {
  const cleaned: AssessmentMetricInput = {
    // 保留已有指标 id，供服务端按 id 差异同步；新建指标无 id。
    ...(metric.id ? { id: metric.id } : {}),
    metric_type: metric.metric_type,
    body_part: metric.body_part || '',
    score: metric.score === null || metric.score === undefined ? null : Number(metric.score),
    description: metric.description || '',
    sort_order: index,
  }
  if (metric.side) cleaned.side = metric.side
  if (metric.scale_code) cleaned.scale_code = metric.scale_code
  if (metric.unit) cleaned.unit = metric.unit
  if (metric.context) cleaned.context = metric.context
  if (metric.movement) cleaned.movement = metric.movement
  if (metric.measurement_mode) cleaned.measurement_mode = metric.measurement_mode
  if (metric.result_code) cleaned.result_code = metric.result_code
  if (metric.details && Object.keys(metric.details).length > 0) cleaned.details = metric.details
  return cleaned
}

function draftPayload(): AssessmentForm {
  return {
    customer: form.customer,
    plan: form.plan || null,
    assessment_type: form.assessment_type,
    assessment_date: form.assessment_date,
    status: 'draft',
    onset_date: form.onset_date || null,
    onset_description: form.onset_description || '',
    onset_mode: form.onset_mode || '',
    chief_complaint: form.chief_complaint || '',
    medical_history: form.medical_history || '',
    aggravating_factors: form.aggravating_factors || '',
    relieving_factors: form.relieving_factors || '',
    prior_care: form.prior_care || '',
    surgery_history: form.surgery_history || '',
    medication: form.medication || '',
    exercise_habits: form.exercise_habits || '',
    work_demands: form.work_demands || '',
    sleep_impact: form.sleep_impact || '',
    rehab_goal: form.rehab_goal || '',
    current_status: form.current_status || '',
    note: form.note || '',
    metrics: form.metrics.map(cleanMetric),
  }
}

async function applySavedAssessment(assessment: Assessment): Promise<void> {
  const wasNew = currentAssessmentId.value === null
  currentAssessmentId.value = assessment.id
  hydrateAssessment(assessment)
  if (wasNew) {
    // 草稿第一次保存后切换到正确的编辑路由，避免再次提交时创建重复首评。
    syncingSavedRoute.value = true
    try {
      await router.replace({ name: 'assessment-revise', params: { id: assessment.id } })
    } finally {
      syncingSavedRoute.value = false
    }
  }
}

async function persistDraft(): Promise<Assessment> {
  const payload = draftPayload()
  const saved = currentAssessmentId.value
    ? await apiUpdateAssessment(currentAssessmentId.value, payload)
    : await apiCreateAssessment(payload)
  await applySavedAssessment(saved)
  return saved
}

async function completeAssessment(): Promise<void> {
  if (!validateForComplete()) {
    const firstMissing = missingItems.value[0]
    if (firstMissing?.includes('评估项目')) currentStep.value = 2
    else if (firstMissing?.includes('康复目标')) currentStep.value = 3
    else currentStep.value = 0
    ElMessage.warning(firstMissing || '请先补充必填内容')
    return
  }

  savingAction.value = 'complete'
  try {
    const saved = await persistDraft()
    const completed = await apiCompleteAssessment(saved.id)
    hydrateAssessment(completed)
    form.status = 'completed'
    dirty.value = false
    leaveConfirmed.value = true
    ElMessage.success('评估已完成')
    await router.push({ name: 'customer-detail', params: { id: form.customer } })
  } finally {
    savingAction.value = ''
  }
}

async function nextStep(): Promise<void> {
  if (currentStep.value >= steps.length - 1) return
  if (!validateStep(currentStep.value)) return

  // “下一步”同时承担自动保存：只有服务端保存成功才允许进入下一阶段。
  savingAction.value = 'draft'
  try {
    await persistDraft()
    currentStep.value += 1
  } catch {
    // HTTP 层已展示具体错误；停留当前步骤，避免产生“已经保存”的误解。
  } finally {
    savingAction.value = ''
  }
}

function previousStep(): void {
  if (currentStep.value > 0) currentStep.value -= 1
}

function goBack(): void {
  router.back()
}

function handleBeforeUnload(event: BeforeUnloadEvent): void {
  if (!dirty.value || leaveConfirmed.value) return
  event.preventDefault()
  event.returnValue = ''
}

watch(
  form,
  () => {
    if (initialized.value) dirty.value = true
  },
  { deep: true },
)

onBeforeRouteLeave(async () => {
  // 首次自动保存后只是把新建 URL 同步为编辑 URL，并非用户离开页面。
  if (syncingSavedRoute.value) return true
  if (!dirty.value || leaveConfirmed.value) return true
  try {
    await ElMessageBox.confirm('当前评估还有未保存的修改，确定离开吗？', '提示', {
      confirmButtonText: '离开页面',
      cancelButtonText: '继续填写',
      type: 'warning',
    })
    leaveConfirmed.value = true
    return true
  } catch {
    return false
  }
})

onMounted(async () => {
  loading.value = true
  try {
    if (!routeAssessmentId && !routeCustomerId) {
      ElMessage.warning('缺少客户信息，无法创建评估')
    }
    const today = new Date().toISOString().slice(0, 10)
    form.assessment_date = today
    await Promise.all([loadMetricDefinitions(), loadForEdit(), loadCustomerName(), loadPreviousMetricTemplates()])
  } finally {
    initialized.value = true
    dirty.value = false
    loading.value = false
  }
})

onBeforeUnmount(() => {
  window.removeEventListener('beforeunload', handleBeforeUnload)
})

window.addEventListener('beforeunload', handleBeforeUnload)
</script>

<template>
  <div v-loading="loading" class="assessment-edit-page">
    <div class="page-header">
      <div>
        <p class="page-eyebrow">康复评估</p>
        <h2>{{ isEditing ? '编辑评估' : '新建评估' }}</h2>
        <p class="page-subtitle">{{ customerName || (form.customer ? `客户 #${form.customer}` : '尚未绑定客户') }}</p>
      </div>
      <div class="header-actions">
        <el-tag v-if="form.status === 'draft'" type="warning">未完成</el-tag>
        <el-tag v-else type="success">已完成</el-tag>
        <el-button @click="goBack">返回</el-button>
      </div>
    </div>

    <el-card class="form-card" shadow="never">
      <AssessmentStepper v-model="currentStep" :steps="steps" />

      <main class="step-content">
        <AssessmentProblemStep
          v-if="currentStep === 0"
          :model-value="form"
          :locked-assessment-type="isAssessmentTypeLocked"
          :customer-name="customerName"
          @update:model-value="Object.assign(form, $event)"
        />
        <AssessmentSubjectiveStep
          v-else-if="currentStep === 1"
          :model-value="form"
          @update:model-value="Object.assign(form, $event)"
        />
        <AssessmentMetricsStep
          v-else-if="currentStep === 2"
          v-model="form.metrics"
          :definitions="metricDefinitions"
          :previous-metrics="previousMetricTemplates"
          :previous-assessment-date="previousAssessmentDate"
        />
        <AssessmentGoalStep
          v-else-if="currentStep === 3"
          :model-value="form"
          :reassessment="form.assessment_type === 'reassessment'"
          @update:model-value="Object.assign(form, $event)"
        />
        <AssessmentReviewStep v-else :form="form" :customer-name="customerName" :missing-items="missingItems" />
      </main>

      <div class="step-actions">
        <div class="step-actions-left">
          <el-button v-if="currentStep > 0" :disabled="isBusy" @click="previousStep">上一步</el-button>
        </div>
        <div class="step-actions-right">
          <el-button
            v-if="currentStep < steps.length - 1"
            type="primary"
            :loading="savingAction === 'draft'"
            :disabled="savingAction === 'complete'"
            @click="nextStep"
          >
            下一步
          </el-button>
          <el-button v-else type="primary" :loading="savingAction === 'complete'" :disabled="savingAction === 'draft'" @click="completeAssessment">
            {{ form.status === 'completed' ? '保存修改' : '完成评估' }}
          </el-button>
        </div>
      </div>
    </el-card>
  </div>
</template>

<style scoped>
.assessment-edit-page {
  width: 100%;
  max-width: 920px;
  margin: 0 auto;
  padding-bottom: 24px;
}

.page-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 18px;
  margin-bottom: 18px;
}

.page-header h2 {
  margin: 3px 0 4px;
  font-size: 24px;
  font-weight: 700;
}

.page-eyebrow {
  margin: 0;
  color: var(--retrue-primary);
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.08em;
}

.page-subtitle {
  margin: 0;
  color: var(--retrue-text-secondary);
  font-size: 13px;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

.form-card {
  overflow: visible;
  border: 1px solid var(--retrue-border);
  border-radius: var(--retrue-radius-lg);
  box-shadow: var(--retrue-shadow);
}

.step-content {
  min-height: 460px;
}

.step-actions {
  position: sticky;
  bottom: 0;
  z-index: 5;
  display: flex;
  justify-content: space-between;
  gap: 12px;
  margin: 24px -20px -20px;
  border-top: 1px solid var(--retrue-border);
  background: var(--retrue-surface-overlay);
  padding: 14px 20px;
  backdrop-filter: blur(8px);
}

.step-actions-left,
.step-actions-right {
  display: flex;
  gap: 10px;
}

.step-actions :deep(.el-button) {
  min-height: 44px;
}

@media (max-width: 768px) {
  .assessment-edit-page {
    padding: 0 0 18px;
  }

  .page-header {
    align-items: stretch;
    flex-direction: column;
    gap: 12px;
  }

  .header-actions {
    justify-content: space-between;
  }

  .form-card :deep(.el-card__body) {
    padding: 16px;
  }

  .step-content {
    min-height: 0;
  }

  .step-actions {
    align-items: stretch;
    flex-direction: column;
    margin: 20px -16px -16px;
    padding: 12px 16px;
  }

  .step-actions-left,
  .step-actions-right {
    width: 100%;
    min-width: 0;
    flex-direction: column;
  }

  .step-actions :deep(.el-button) {
    width: 100%;
    min-width: 0;
    margin: 0;
  }
}
</style>
