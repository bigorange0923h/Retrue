<script setup lang="ts">
/**
 * 引导式评估编辑页。
 *
 * 页面级表单是唯一编辑状态，子组件只负责当前步骤的展示和录入；
 * 满分、单位、量表和完成校验由服务端规则决定，前端不提供可编辑满分。
 */

import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { onBeforeRouteLeave, onBeforeRouteUpdate, useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'

import {
  apiCompleteAssessment,
  apiCreateAssessment,
  apiGetAssessment,
  apiGetInitialAssessment,
  apiGetMetricDefinitions,
  apiListAssessments,
  apiUpdateAssessment,
  toAssessmentMetricInput,
  type AssessmentForm,
  type AssessmentInputDraft,
} from '@/api/assessments'
import { ApiBusinessError } from '@/api/http'
import { adoptAssessmentInput, assessmentFieldLabels, assessmentValueSummary } from '@/utils/assessmentInput'
import AssessmentInputPanel from '@/components/assessment/AssessmentInputPanel.vue'
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

const routeAssessmentId = computed(() => Number(route.params.id || 0) || null)
const routeCustomerId = computed(() => Number(route.query.customerId || route.params.customerId || 0) || 0)
const initialFlow = computed(() => route.query.mode === 'initial' && !routeAssessmentId.value)
const pageSessionKey = ref(0)

const loading = ref(false)
const loadFailed = ref(false)
const initialized = ref(false)
const dirty = ref(false)
const leaveConfirmed = ref(false)
const syncingSavedRoute = ref(false)
const currentStep = ref(0)
const editMode = ref<'summary' | 'guided'>('summary')
const organizing = ref(false)
const inputUnsaved = ref(false)
const inputPanel = ref<InstanceType<typeof AssessmentInputPanel> | null>(null)
const savedVersion = ref('')
const conflict = ref(false)
const conflictVisible = ref(false)
const remoteAssessment = ref<Assessment | null>(null)
const keepLocalFields = ref<string[]>([])
const savedBaseline = ref<Record<string, unknown>>({})
const adoptedDraftIds = ref<number[]>([])
let autosaveTimer: ReturnType<typeof setTimeout> | null = null
const savingAction = ref<'draft' | 'complete' | ''>('')
const saveFailed = ref(false)
const currentAssessmentId = ref<number | null>(routeAssessmentId.value)
const customerName = ref('')
const missingItems = ref<string[]>([])
const metricDefinitions = ref<AssessmentMetricDefinition[]>([])
const previousMetricTemplates = ref<AssessmentMetricInput[]>([])
const previousAssessmentDate = ref('')

const steps = ['本次问题', '主观情况', '客观评估', '目标与备注', '检查并完成']

/** 每次切换客户/记录使用全新的草稿状态，不能残留上一客户的输入。 */
function emptyForm(): AssessmentForm { return {
  customer: routeCustomerId.value,
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
} }
const form = reactive<AssessmentForm>(emptyForm())

const isEditing = computed(() => currentAssessmentId.value !== null)
const isAssessmentTypeLocked = computed(() => isEditing.value || initialFlow.value || form.assessment_type === 'initial')
const isBusy = computed(() => loading.value || loadFailed.value || organizing.value || conflict.value || savingAction.value !== '')
const saveStatus = computed(() => loading.value ? '正在加载…' : loadFailed.value ? '加载失败，请重试后继续' : conflict.value ? '发现其他窗口的修改，尚未覆盖，请核对差异' : savingAction.value ? '正在保存…' : saveFailed.value ? '保存失败，内容仍在当前页面，请重试' : dirty.value ? '有未保存的修改' : isEditing.value ? '已保存' : '尚未保存')
const completionGaps = computed(() => {
  const items: { message: string; step: number }[] = []
  if (!form.assessment_date) items.push({ message: '评估日期', step: 0 })
  if (!form.chief_complaint?.trim()) items.push({ message: '主要问题', step: 0 })
  if (!form.onset_date && !form.onset_description?.trim()) items.push({ message: '开始时间', step: 0 })
  if (!form.rehab_goal?.trim()) items.push({ message: '康复目标', step: 3 })
  if (!form.metrics.length) items.push({ message: '客观评估项目', step: 2 })
  form.metrics.forEach((metric, index) => {
    const message = validateMetric(metric, index)
    if (message) items.push({ message, step: 2 })
  })
  return items
})
const conflictRows = computed(() => {
  if (!remoteAssessment.value) return []
  const local = draftPayload() as unknown as Record<string, unknown>
  const remote = remoteAssessment.value as unknown as Record<string, unknown>
  return [...Object.keys(assessmentFieldLabels), 'metrics'].filter((key) => {
    const latest = key === 'metrics' ? remoteAssessment.value!.metrics.map(metricInput) : remote[key]
    return JSON.stringify(local[key]) !== JSON.stringify(savedBaseline.value[key]) && JSON.stringify(local[key]) !== JSON.stringify(latest)
  }).map((key) => ({ key, label: key === 'metrics' ? '客观评估项目（整组）' : assessmentFieldLabels[key], local: local[key], remote: remote[key] }))
})

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
  savedVersion.value = assessment.updated_at
  form.customer = assessment.customer
  form.plan = assessment.plan
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
  savedBaseline.value = JSON.parse(JSON.stringify(draftPayload()))
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
  let id = routeAssessmentId.value
  if (!id && routeCustomerId.value && form.assessment_type === 'initial') {
    const initial = await apiGetInitialAssessment(routeCustomerId.value)
    id = initial.assessment_id
  }
  if (!id) return
  currentAssessmentId.value = id
  const assessment = await apiGetAssessment(id)
  hydrateAssessment(assessment)
  if (!routeAssessmentId.value) {
    syncingSavedRoute.value = true
    try { await router.replace({ name: 'assessment-revise', params: { id } }) }
    finally { syncingSavedRoute.value = false }
  }
}

async function loadCustomerName(): Promise<void> {
  if (!routeCustomerId.value || routeAssessmentId.value) return
  try {
    const customer = await apiGetCustomer(routeCustomerId.value)
    customerName.value = customer.name
  } catch {
    // 客户名称不是提交评估的必要条件，保留客户 ID 供页面继续工作。
  }
}

/** 新建复评时提供上一次已完成评估的同类项目结构，结果值必须重新测量。 */
async function loadPreviousMetricTemplates(): Promise<void> {
  if (routeAssessmentId.value || form.assessment_type !== 'reassessment' || !routeCustomerId.value) return
  const assessments = await apiListAssessments(routeCustomerId.value)
  const previous = assessments.find((item) => item.status === 'completed')
  if (!previous) return

  previousAssessmentDate.value = previous.assessment_date
  previousMetricTemplates.value = previous.metrics.map((metric, index) => {
    const template = metricInput(metric)
    const details = { ...(template.details || {}) }
    if (metric.metric_type === 'functional') delete details.pain_status
    return {
      ...template,
      id: undefined,
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
    ...(savedVersion.value ? { expected_updated_at: savedVersion.value } : {}),
    ...(adoptedDraftIds.value.length ? { ai_input_draft_ids: [...adoptedDraftIds.value] } : {}),
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
  let saved: Assessment
  try {
    saved = currentAssessmentId.value
      ? await apiUpdateAssessment(currentAssessmentId.value, payload)
      : await apiCreateAssessment(payload)
  } catch (error) {
    if (error instanceof ApiBusinessError && error.code === 409) conflict.value = true
    throw error
  }
  adoptedDraftIds.value = []
  await applySavedAssessment(saved)
  saveFailed.value = false
  return saved
}

async function completeAssessment(): Promise<void> {
  if (isBusy.value) return
  if (inputPanel.value && !await inputPanel.value.saveSource()) return
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
    const completed = await apiCompleteAssessment(saved.id, saved.updated_at)
    hydrateAssessment(completed)
    form.status = 'completed'
    dirty.value = false
    leaveConfirmed.value = true
    ElMessage.success('评估已完成')
    await router.push({ name: 'customer-detail', params: { id: form.customer } })
  } catch (error) {
    if (error instanceof ApiBusinessError && error.code === 409) conflict.value = true
    saveFailed.value = dirty.value
  } finally {
    savingAction.value = ''
    leaveConfirmed.value = false
  }
}

async function nextStep(): Promise<void> {
  if (isBusy.value) return
  if (currentStep.value >= steps.length - 1) return
  if (!validateStep(currentStep.value)) return

  // “下一步”同时承担自动保存：只有服务端保存成功才允许进入下一阶段。
  savingAction.value = 'draft'
  saveFailed.value = false
  try {
    await persistDraft()
    currentStep.value += 1
  } catch {
    saveFailed.value = true
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

async function saveAndLeave(): Promise<void> {
  if (isBusy.value || !form.customer) return
  if (inputPanel.value && !await inputPanel.value.saveSource()) return
  savingAction.value = 'draft'
  saveFailed.value = false
  try {
    await persistDraft()
  } catch {
    saveFailed.value = true
    return
  } finally {
    savingAction.value = ''
  }
  leaveConfirmed.value = true
  ElMessage.success('评估草稿已保存，可以稍后继续')
  try {
    await router.push({ name: 'customer-detail', params: { id: form.customer } })
  } finally {
    leaveConfirmed.value = false
  }
}

function handleBeforeUnload(event: BeforeUnloadEvent): void {
  if ((!dirty.value && !inputUnsaved.value) || leaveConfirmed.value) return
  event.preventDefault()
  event.returnValue = ''
}

watch(
  form,
  () => {
    if (initialized.value) {
      dirty.value = true
      scheduleAutosave()
    }
  },
  { deep: true, flush: 'sync' },
)
watch(organizing, (value) => { if (!value && dirty.value) scheduleAutosave() })

async function confirmLeave(): Promise<boolean> {
  // 首次自动保存后只是把新建 URL 同步为编辑 URL，并非用户离开页面。
  if (syncingSavedRoute.value) return true
  // 保存/加载期间不切换记录，避免旧请求晚返回后覆盖新客户的页面状态。
  if (loading.value || savingAction.value !== '') return false
  // 保存/加载期间不切换记录，避免旧请求晚返回后覆盖新客户的页面状态。
  if (loading.value || savingAction.value !== '') return false
  if ((!dirty.value && !inputUnsaved.value) || leaveConfirmed.value) return true
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
}
onBeforeRouteLeave(confirmLeave)
onBeforeRouteUpdate(confirmLeave)

watch(() => JSON.stringify([route.params.id, route.query.customerId, route.query.mode]), async () => {
  if (syncingSavedRoute.value) return
  initialized.value = false
  if (autosaveTimer) clearTimeout(autosaveTimer)
  currentAssessmentId.value = routeAssessmentId.value
  savedVersion.value = ''
  savedBaseline.value = {}
  adoptedDraftIds.value = []
  conflict.value = false
  conflictVisible.value = false
  remoteAssessment.value = null
  customerName.value = ''
  previousMetricTemplates.value = []
  previousAssessmentDate.value = ''
  leaveConfirmed.value = false
  saveFailed.value = false
  inputUnsaved.value = false
  organizing.value = false
  Object.assign(form, emptyForm())
  pageSessionKey.value++
  await loadPage()
})

async function loadPage(): Promise<void> {
  loading.value = true
  loadFailed.value = false
  initialized.value = false
  try {
    if (!routeAssessmentId.value && !routeCustomerId.value) {
      ElMessage.warning('缺少客户信息，无法创建评估')
    }
    const now = new Date()
    const today = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`
    form.assessment_date = today
    await loadForEdit()
    await Promise.all([loadMetricDefinitions(), loadCustomerName(), loadPreviousMetricTemplates()])
    currentStep.value = editMode.value === 'summary' ? 4 : 0
  } catch {
    loadFailed.value = true
  } finally {
    initialized.value = true
    dirty.value = false
    loading.value = false
  }
}

onMounted(loadPage)

onBeforeUnmount(() => {
  if (autosaveTimer) clearTimeout(autosaveTimer)
  window.removeEventListener('beforeunload', handleBeforeUnload)
})

window.addEventListener('beforeunload', handleBeforeUnload)

/** 空草稿不自动创建；输入或采用后的修改防抖保存，失败停下等待明确重试。 */
function scheduleAutosave(): void {
  if (autosaveTimer) clearTimeout(autosaveTimer)
  if (!initialized.value || form.status !== 'draft' || saveFailed.value || conflict.value) return
  autosaveTimer = setTimeout(() => { void saveInPlace() }, 1800)
}

async function saveInPlace(): Promise<void> {
  if (isBusy.value || !dirty.value || !form.customer || !form.assessment_date) return
  savingAction.value = 'draft'
  try { await persistDraft() }
  catch { saveFailed.value = true }
  finally { savingAction.value = '' }
}

/** 先确保描述能关联到持久草稿，避免刷新后只留下新建页上下文。 */
async function prepareSourceSave(): Promise<boolean> {
  if (isBusy.value) return false
  if (dirty.value || !currentAssessmentId.value) {
    savingAction.value = 'draft'
    try { await persistDraft() }
    catch { saveFailed.value = true; return false }
    finally { savingAction.value = '' }
  }
  return true
}

function adoptInput(draft: AssessmentInputDraft, fields: string[], metrics: number[]): void {
  adoptAssessmentInput(form, draft, fields, metrics)
  adoptedDraftIds.value = [...new Set([...adoptedDraftIds.value, draft.id])]
  dirty.value = true
  currentStep.value = 4
  scheduleAutosave()
}

function editGap(step: number): void { currentStep.value = step }

async function inspectConflict(): Promise<void> {
  if (!currentAssessmentId.value) return
  remoteAssessment.value = await apiGetAssessment(currentAssessmentId.value)
  keepLocalFields.value = conflictRows.value.filter((row) => {
    const latest = row.key === 'metrics' ? remoteAssessment.value!.metrics.map(metricInput) : row.remote
    return JSON.stringify(latest) === JSON.stringify(savedBaseline.value[row.key])
  }).map((row) => row.key)
  conflictVisible.value = true
}

/** 最新版为底稿；用户逐项选择保留本页值，合并后再正常保存和校验。 */
function resolveConflict(): void {
  if (!remoteAssessment.value) return
  const local = draftPayload() as unknown as Record<string, unknown>
  const selected = [...keepLocalFields.value]
  const pendingIds = [...adoptedDraftIds.value]
  hydrateAssessment(remoteAssessment.value)
  const writable = form as unknown as Record<string, unknown>
  for (const key of selected) writable[key] = local[key]
  adoptedDraftIds.value = pendingIds
  conflict.value = false
  conflictVisible.value = false
  saveFailed.value = false
  dirty.value = true
  scheduleAutosave()
}
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
        <el-button :disabled="loading || savingAction !== ''" @click="goBack">返回</el-button>
      </div>
    </div>

    <el-card class="form-card" shadow="never">
      <AssessmentInputPanel v-if="form.status === 'draft'" :key="pageSessionKey" ref="inputPanel" :form="form" :assessment-id="currentAssessmentId" :prepare-save="prepareSourceSave"
        :disabled="loading || loadFailed || conflict || savingAction !== ''" :ready="initialized && !loadFailed"
        @busy="organizing = $event" @unsaved="inputUnsaved = $event" @adopt="adoptInput" />
      <el-radio-group v-model="editMode" :disabled="isBusy" @change="currentStep = editMode === 'summary' ? 4 : 0">
        <el-radio-button value="summary">摘要与按需补充</el-radio-button>
        <el-radio-button value="guided">五步引导填写</el-radio-button>
      </el-radio-group>
      <div v-if="editMode === 'guided'" :inert="isBusy"><AssessmentStepper v-model="currentStep" :steps="steps" /></div>
      <div v-else class="section-shortcuts">
        <el-button v-for="(step, index) in steps" :key="step" :type="currentStep === index ? 'primary' : 'default'" :disabled="isBusy" @click="currentStep = index">{{ index === 4 ? '查看摘要' : `修改${step}` }}</el-button>
      </div>
      <p class="save-status" :class="{ 'save-error': saveFailed }" role="status" aria-live="polite">{{ saveStatus }}</p>
      <el-button v-if="conflict" type="warning" @click="inspectConflict">核对最新版本</el-button>
      <el-button v-else-if="saveFailed" link type="primary" :disabled="isBusy" @click="saveInPlace">重试保存</el-button>
      <div v-if="form.status === 'draft'" class="completion-gaps">
        <p>{{ completionGaps.length ? `完成前还需补充 ${completionGaps.length} 项` : '完成所需字段已填写，请核对内容后完成评估' }}</p>
        <el-button v-for="gap in completionGaps" :key="gap.message" link type="primary" :disabled="isBusy" @click="editGap(gap.step)">{{ gap.message }}</el-button>
        <p class="question-reminder">首评仍需核查：问题、开始时间、发生方式、加重/缓解、既往就医、运动/工作和目标。未记录的问诊内容不会视为已询问。</p>
      </div>
      <el-alert v-if="loadFailed" type="error" :closable="false" title="未能加载评估内容，重试后再继续填写。">
        <el-button text type="primary" @click="loadPage">重新加载</el-button>
      </el-alert>

      <main class="step-content" :inert="isBusy" :aria-busy="isBusy">
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
          @edit-problem="currentStep = 0"
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
        <AssessmentReviewStep v-else :form="form" :customer-name="customerName" :missing-items="completionGaps.map(gap => gap.message)" />
      </main>

      <div class="step-actions">
        <div class="step-actions-left">
          <el-button v-if="editMode === 'guided' && currentStep > 0" :disabled="isBusy" @click="previousStep">上一步</el-button>
          <el-button :disabled="isBusy || !dirty" @click="saveInPlace">{{ form.status === 'completed' ? '保存修改' : '保存草稿' }}</el-button>
          <el-button v-if="form.status === 'draft'" :disabled="isBusy || !form.customer" @click="saveAndLeave">保存并稍后继续</el-button>
        </div>
        <div class="step-actions-right">
          <el-button
            v-if="editMode === 'guided' && currentStep < steps.length - 1"
            type="primary"
            :loading="savingAction === 'draft'"
            :disabled="isBusy"
            @click="nextStep"
          >
            下一步
          </el-button>
          <el-button v-else type="primary" :loading="savingAction === 'complete'" :disabled="isBusy" @click="completeAssessment">
            {{ form.status === 'completed' ? '保存修改' : '完成评估' }}
          </el-button>
        </div>
      </div>
    </el-card>
    <el-dialog v-model="conflictVisible" title="核对其他窗口的修改" width="min(700px, 94vw)" :close-on-click-modal="false">
      <p>默认采用最新版本；仅选中需要保留的本页值。未选中的字段不会覆盖其他窗口。</p>
      <el-checkbox-group v-model="keepLocalFields">
        <article v-for="row in conflictRows" :key="row.key" class="conflict-row">
          <el-checkbox :value="row.key">保留本页的{{ row.label }}</el-checkbox>
          <p>本页：{{ assessmentValueSummary(row.key, row.local) }}</p>
          <p>最新：{{ assessmentValueSummary(row.key, row.remote) }}</p>
        </article>
      </el-checkbox-group>
      <template #footer><el-button @click="conflictVisible = false">暂不处理</el-button><el-button type="primary" @click="resolveConflict">按选择合并并保存草稿</el-button></template>
    </el-dialog>
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

.save-status { margin: -6px 0 18px; color: var(--retrue-text-secondary); font-size: 12px; }
.save-error { color: var(--el-color-danger); }
.section-shortcuts { display: flex; flex-wrap: wrap; gap: 8px; margin: 16px 0; }
.section-shortcuts :deep(.el-button) { margin: 0; }
.completion-gaps { margin-bottom: 18px; }
.completion-gaps p, .question-reminder { color: var(--retrue-text-secondary); font-size: 13px; line-height: 1.7; }
.conflict-row { padding: 12px 0; border-bottom: 1px solid var(--retrue-border); }
.conflict-row p { white-space: pre-wrap; overflow-wrap: anywhere; }

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
  flex-wrap: wrap;
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
