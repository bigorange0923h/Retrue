<script setup lang="ts">
/**
 * 训练补记工作区：负责自然语言解析、客户选择、草稿编辑和明确确认。
 *
 * 该组件同时供统一助理页面和旧的兼容入口使用，正式训练记录仍通过原有
 * 确认接口写入；在解析和确认过程中只更新可恢复的统一助理任务。
 */

import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'

import { apiCreateAssistantTask, apiGetAssistantTask, apiUpdateAssistantTask } from '@/api/assistant'
import {
  apiCancelDraft,
  apiConfirmDraft,
  apiCustomerCandidates,
  apiListDrafts,
  apiParseDraft,
} from '@/api/ai'
import { apiGetCourse } from '@/api/courses'
import type {
  AiDraft,
  AiDraftResult,
  AssistantTask,
  CustomerCandidate,
} from '@/types/api'

interface Props {
  customerId?: number | null
  courseSessionId?: number | null
  assistantTaskId?: number | null
  initialTask?: AssistantTask | null
  initialDraft?: AiDraft | null
  initialInputText?: string
  customerName?: string
  topic?: string
  skillLabel?: string
  invocationMode?: string
}

const props = withDefaults(defineProps<Props>(), {
  customerId: null,
  courseSessionId: null,
  assistantTaskId: null,
  initialTask: null,
  initialDraft: null,
  initialInputText: '',
  customerName: '未选择客户',
  topic: '训练补记',
  skillLabel: '训练记录整理',
  invocationMode: 'smart',
})

const emit = defineEmits<{
  'task-created': [task: AssistantTask]
  'task-updated': [task: AssistantTask]
  'customer-selected': [customer: CustomerCandidate]
  parsed: [draft: AiDraft]
  confirmed: [draft: AiDraft, customerId: number]
  cancelled: []
  input: [value: string]
}>()

const inputText = ref('')
const parsing = ref(false)
const confirming = ref(false)
const draft = ref<AiDraft | null>(null)
const localTaskId = ref<number | null>(props.assistantTaskId)
const localTask = ref<AssistantTask | null>(props.initialTask)
const courseDate = ref('')
const taskSyncing = ref(false)
const refreshingTask = ref(false)
const confirmationKey = ref<string | null>(null)
const taskRequestId = ref(createClientRequestId())
const parseRequestId = ref(createParseRequestId())
let taskPollTimer: ReturnType<typeof setInterval> | null = null
let taskPollAttempts = 0

const editForm = reactive<AiDraftResult>({
  training_date: '',
  customer_hint: null,
  exercises: [],
  customer_feedback: '',
  therapist_observation: '',
  next_plan: '',
})

const customerPickerVisible = ref(false)
const candidates = ref<CustomerCandidate[]>([])
const selectedCustomer = ref<CustomerCandidate | null>(null)
const customerKeyword = ref('')
const loadingCandidates = ref(false)

const taskCustomerId = computed(() => {
  const task = props.initialTask
  if (!task) return null
  const value = task.customer
  return typeof value === 'number' && value > 0 ? value : null
})

const effectiveCustomerId = computed(() => props.customerId || selectedCustomer.value?.id || taskCustomerId.value)

const taskInitialInput = computed(() => {
  if (props.initialInputText) return props.initialInputText
  if (props.initialTask?.input_text) return props.initialTask.input_text
  const value = props.initialTask?.state_data?.input_text
  return typeof value === 'string' ? value : ''
})

const taskInitialDraft = computed<AiDraft | null>(() => {
  if (props.initialDraft) return props.initialDraft
  if (props.initialTask?.draft) return props.initialTask.draft
  const candidate = props.initialTask?.state_data?.draft ?? props.initialTask?.state_data?.ai_draft
  return isAiDraft(candidate) ? candidate : null
})

const isConfirmed = computed(() => draft.value?.status === 'confirmed')
const taskStatus = computed(() => localTask.value?.status || props.initialTask?.status || null)
const isTaskRunning = computed(() => taskStatus.value === 'running')

/** 判断任务 payload 中的草稿是否具备 AiDraft 的最小结构。 */
function isAiDraft(value: unknown): value is AiDraft {
  if (!value || typeof value !== 'object') return false
  const item = value as Partial<AiDraft>
  return typeof item.id === 'number' && typeof item.status === 'string' && !!item.ai_result
}

/** 根据查询或任务恢复客户候选，手机号始终使用脱敏字段。 */
function setInitialCustomer(): void {
  const id = effectiveCustomerId.value
  if (!id) return
  const name = props.initialTask?.customer_name || ''
  selectedCustomer.value = { id, name, phone_masked: '' }
}

/** 将 AI 返回的结构复制到可编辑表单，避免直接修改服务端响应对象。 */
function hydrateDraft(value: AiDraft): void {
  draft.value = value
  const result = value.ai_result || {} as AiDraftResult
  editForm.training_date = courseDate.value || result.training_date || ''
  editForm.customer_hint = result.customer_hint || null
  editForm.exercises = (result.exercises || []).map((exercise, index) => ({
    ...exercise,
    sort_order: index,
  }))
  editForm.customer_feedback = result.customer_feedback || ''
  editForm.therapist_observation = result.therapist_observation || ''
  editForm.next_plan = result.next_plan || ''

  if (!selectedCustomer.value && value.customer) {
    selectedCustomer.value = {
      id: value.customer,
      name: value.customer_name || '',
      phone_masked: '',
    }
  }
}

/** 生成客户端任务幂等键，同一补记工作区的创建重试沿用该键。 */
function createClientRequestId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return `assistant-training-${crypto.randomUUID()}`
  }
  return `assistant-training-${Date.now()}-${Math.random().toString(36).slice(2)}`
}

/** 生成一次确认请求专用的幂等键，失败重试时沿用同一个键。 */
function createIdempotencyKey(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') return crypto.randomUUID()
  return `training-confirm-${Date.now()}-${Math.random().toString(36).slice(2)}`
}

/** 同一次 AI 解析的网络重试沿用该键，明确重新解析时再生成新键。 */
function createParseRequestId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return `training-parse-${crypto.randomUUID()}`
  }
  return `training-parse-${Date.now()}-${Math.random().toString(36).slice(2)}`
}

/** 从统一任务的资源引用中读取 AI 草稿 ID。 */
function taskDraftId(task: AssistantTask): number | null {
  const directId = Number(task.draft_resource_id || task.state_data?.draft_id || 0)
  return Number.isFinite(directId) && directId > 0 ? directId : null
}

/** 任务结束整理后重新加载服务端草稿，恢复到可编辑的待确认状态。 */
async function restoreDraftForTask(task: AssistantTask): Promise<void> {
  const draftId = taskDraftId(task)
  if (!draftId) return
  try {
    const drafts = await apiListDrafts()
    const restored = drafts.find((item) => item.id === draftId)
    if (restored) {
      hydrateDraft(restored)
      emit('parsed', restored)
    }
  } catch {
    // 草稿稍后仍可通过手动刷新任务恢复，不阻断当前页面。
  }
}

function stopTaskPolling(): void {
  if (taskPollTimer !== null) {
    clearInterval(taskPollTimer)
    taskPollTimer = null
  }
  taskPollAttempts = 0
}

/** 刷新运行中任务；不在前端伪造状态，状态变化始终以服务端返回为准。 */
async function refreshTask(): Promise<void> {
  if (localTaskId.value === null || refreshingTask.value) return
  refreshingTask.value = true
  try {
    const latest = await apiGetAssistantTask(localTaskId.value)
    localTask.value = latest
    emit('task-updated', latest)
    if (latest.status !== 'running') {
      stopTaskPolling()
      if (latest.status === 'waiting_confirmation') await restoreDraftForTask(latest)
    }
  } catch {
    // 任务仍可稍后手动刷新，网络失败不覆盖当前工作区。
  } finally {
    refreshingTask.value = false
  }
}

/** 运行中任务短轮询一段时间，页面离开或状态变化后立即停止。 */
function startTaskPolling(): void {
  stopTaskPolling()
  if (!isTaskRunning.value) return
  taskPollTimer = setInterval(() => {
    if (!isTaskRunning.value || taskPollAttempts >= 40) {
      stopTaskPolling()
      return
    }
    taskPollAttempts += 1
    void refreshTask()
  }, 3000)
}

/** 首次解析时创建任务，以便离开页面后能够继续。 */
async function ensureAssistantTask(): Promise<AssistantTask | null> {
  if (localTaskId.value !== null) return localTask.value

  taskSyncing.value = true
  try {
    const contextResourceType = props.courseSessionId
      ? 'course_session'
      : effectiveCustomerId.value
        ? 'customer'
        : ''
    const contextResourceId = props.courseSessionId
      ? String(props.courseSessionId)
      : effectiveCustomerId.value
        ? String(effectiveCustomerId.value)
        : ''
    const task = await apiCreateAssistantTask({
      task_type: 'training_record',
      skill_code: 'training_record',
      invocation_mode: props.invocationMode,
      origin: props.topic,
      context_resource_type: contextResourceType,
      context_resource_id: contextResourceId,
      customer: effectiveCustomerId.value,
      current_step: 'collect_training_description',
      client_request_id: taskRequestId.value,
      ...(props.courseSessionId
        ? { business_key: `training:course_session:${props.courseSessionId}` }
        : {}),
      state_data: {
        input_length: inputText.value.trim().length,
        topic: props.topic,
      },
    })
    localTaskId.value = task.id
    localTask.value = task
    emit('task-created', task)
    return task
  } catch {
    // 任务 API 暂不可用时仍允许康复师完成当前草稿，避免阻断核心记录流程。
    ElMessage.warning('暂时无法保存恢复进度，本次仍可继续生成草稿')
    return null
  } finally {
    taskSyncing.value = false
  }
}

/** 同步当前任务状态；任务回写失败不覆盖草稿或确认结果。 */
async function syncTask(
  extra: {
    draft_id?: number | null
    customer_id?: number | null
    payload?: Record<string, unknown>
    current_step?: string
  } = {},
): Promise<void> {
  if (localTaskId.value === null) return
  taskSyncing.value = true
  const safeState = (currentState: Record<string, unknown>): Record<string, unknown> => {
    const { input_text: _inputText, draft: _draft, ai_draft: _aiDraft, ...summary } = currentState
    return summary
  }
  const buildPayload = (version: number | undefined, currentState: Record<string, unknown>) => ({
    current_step: extra.current_step,
    customer: extra.customer_id ?? effectiveCustomerId.value,
    state_data: {
      ...safeState(currentState),
      ...(extra.draft_id != null ? { draft_id: extra.draft_id } : {}),
      ...(extra.payload || {}),
    },
    ...(version != null ? { version } : {}),
  })

  try {
    const task = await apiUpdateAssistantTask(
      localTaskId.value,
      buildPayload(localTask.value?.version, localTask.value?.state_data || {}),
    )
    localTask.value = task
    emit('task-updated', task)
  } catch {
    // 解析服务可能在本次 PATCH 前推进了任务版本；读取后合并并只重试一次。
    try {
      const latest = await apiGetAssistantTask(localTaskId.value)
      localTask.value = latest
      if (latest.status === 'completed' || latest.status === 'cancelled' || latest.status === 'expired') return
      const task = await apiUpdateAssistantTask(
        localTaskId.value,
        buildPayload(latest.version, latest.state_data || {}),
      )
      localTask.value = task
      emit('task-updated', task)
    } catch {
      // 任务状态是恢复辅助信息，不应使草稿或确认结果被误报为失败。
    }
  } finally {
    taskSyncing.value = false
  }
}

/** 解析自然语言训练描述，并把结果转成待确认草稿。 */
async function handleParse(): Promise<void> {
  const text = inputText.value.trim()
  if (isTaskRunning.value) {
    ElMessage.info('任务正在整理，请稍后返回或刷新状态')
    return
  }
  if (!text || parsing.value || confirming.value) {
    if (!text) ElMessage.warning('请输入训练描述')
    return
  }

  parsing.value = true
  try {
    confirmationKey.value = null
    await ensureAssistantTask()
    await syncTask({ payload: { input_length: text.length }, current_step: 'drafting' })
    const result = await apiParseDraft(
      text,
      effectiveCustomerId.value,
      {
        assistantTaskId: localTaskId.value,
        courseSessionId: props.courseSessionId,
        clientRequestId: parseRequestId.value,
      },
    )
    parseRequestId.value = createParseRequestId()
    hydrateDraft(result)
    emit('parsed', result)
    if (result.status === 'failed') {
      await syncTask({ payload: { error_message: result.error_message || '解析失败' }, current_step: 'parse_failed' })
      ElMessage.error(result.error_message || 'AI 解析失败，请调整描述后重试')
      return
    }

    await syncTask({
      draft_id: result.id,
    })
    if (!effectiveCustomerId.value) await openCustomerPicker()
  } catch {
    // 网络断开或浏览器超时不代表服务端一定停止。优先读取持久化任务；如果任务
    // 仍在运行，则进入恢复轮询，避免康复师再次提交同一段训练描述。
    if (localTaskId.value !== null) {
      try {
        const latest = await apiGetAssistantTask(localTaskId.value)
        localTask.value = latest
        emit('task-updated', latest)
        if (latest.status === 'running') {
          ElMessage.info('训练内容仍在整理中，可以稍后返回查看')
          startTaskPolling()
          return
        }
        if (latest.status === 'waiting_confirmation') {
          await restoreDraftForTask(latest)
          return
        }
      } catch {
        // 保留本地输入和任务编号，稍后仍可从未完成任务中继续。
      }
    }
  } finally {
    parsing.value = false
  }
}

/** 打开客户选择并按姓名提示查询。 */
async function openCustomerPicker(): Promise<void> {
  customerPickerVisible.value = true
  await loadCandidates()
}

/** 加载当前康复师可选客户。 */
async function loadCandidates(): Promise<void> {
  loadingCandidates.value = true
  try {
    candidates.value = await apiCustomerCandidates(customerKeyword.value.trim() || '')
  } finally {
    loadingCandidates.value = false
  }
}

/** 确认客户候选。 */
function pickCustomer(candidate: CustomerCandidate): void {
  selectedCustomer.value = candidate
  customerPickerVisible.value = false
  emit('customer-selected', candidate)
  void syncTask({ customer_id: candidate.id, current_step: 'confirm_customer' })
}

/** 确认人工编辑后的草稿，使用幂等键保障重复点击安全。 */
async function handleConfirm(): Promise<void> {
  if (isTaskRunning.value) {
    ElMessage.info('任务正在整理，完成后才能确认训练草稿')
    return
  }
  if (!draft.value || isConfirmed.value || confirming.value) return
  if (!selectedCustomer.value?.id) {
    ElMessage.warning('请先选择客户，再确认训练记录')
    await openCustomerPicker()
    return
  }

  confirming.value = true
  try {
    const payload: AiDraftResult = {
      ...editForm,
      exercises: editForm.exercises.map((exercise, index) => ({ ...exercise, sort_order: index })),
    }
    const result = await apiConfirmDraft(
      draft.value.id,
      selectedCustomer.value.id,
      payload,
      props.courseSessionId,
      {
        idempotencyKey: confirmationKey.value ?? (confirmationKey.value = createIdempotencyKey()),
      },
    )
    hydrateDraft(result)
    ElMessage.success('已确认并创建训练记录')
    emit('confirmed', result, selectedCustomer.value.id)
  } finally {
    confirming.value = false
  }
}

/** 取消草稿并放弃当前恢复任务。 */
async function handleCancel(): Promise<void> {
  if (!draft.value || confirming.value) return
  await apiCancelDraft(draft.value.id)
  ElMessage.info('草稿已取消')
  draft.value = null
  editForm.exercises = []
  localTaskId.value = null
  localTask.value = null
  confirmationKey.value = null
  taskRequestId.value = createClientRequestId()
  emit('cancelled')
}

/** 删除一行动作，至少保留一行便于继续编辑。 */
function removeExercise(index: number): void {
  if (editForm.exercises.length <= 1) return
  editForm.exercises.splice(index, 1)
  editForm.exercises.forEach((exercise, itemIndex) => { exercise.sort_order = itemIndex })
}

watch(
  () => props.assistantTaskId,
  (value) => {
    localTaskId.value = value ?? null
    localTask.value = props.initialTask
    if (!value) stopTaskPolling()
  },
)

watch(
  () => localTask.value?.status,
  (status) => {
    if (status === 'running') startTaskPolling()
    else stopTaskPolling()
  },
)

watch(
  () => inputText.value,
  (value) => emit('input', value),
)

onMounted(async () => {
  inputText.value = taskInitialInput.value
  setInitialCustomer()
  if (taskInitialDraft.value) hydrateDraft(taskInitialDraft.value)
  if (props.courseSessionId) {
    try {
      const course = await apiGetCourse(props.courseSessionId)
      courseDate.value = course.date
      if (!editForm.training_date) editForm.training_date = courseDate.value
    } catch {
      // 课程日期不是草稿编辑的必要条件，读取失败时允许手动选择日期。
    }
  }
  if (isTaskRunning.value) {
    await refreshTask()
    if (isTaskRunning.value) startTaskPolling()
  }
})

onBeforeUnmount(stopTaskPolling)
</script>

<template>
  <div class="training-draft-panel">
    <el-alert
      v-if="isTaskRunning"
      title="正在整理，可稍后返回"
      type="info"
      :closable="false"
      show-icon
      class="running-task-alert"
    >
      <template #default>
        <div class="running-task-body">
          <span>任务完成后会自动恢复训练草稿。</span>
          <el-button text type="primary" :loading="refreshingTask" @click="refreshTask">刷新状态</el-button>
        </div>
      </template>
    </el-alert>
    <el-card class="training-input-card retrue-card" shadow="never">
      <template #header>
        <div class="card-heading">
          <div>
            <strong>训练补记</strong>
            <p>用自然语言描述本次训练，生成草稿后由你检查并确认。</p>
          </div>
          <el-tag type="info" effect="plain">仅保存草稿</el-tag>
        </div>
      </template>
      <el-alert
        v-if="courseSessionId"
        title="确认后将完成对应课程并按业务规则扣减课时"
        type="info"
        :closable="false"
        show-icon
        class="session-alert"
      />
      <div class="training-input-context" aria-label="当前工作上下文">
        <span class="training-context-chip customer"><b>客户</b>{{ customerName }}</span>
        <span class="training-context-chip topic"><b>主题</b>{{ topic }}</span>
        <span class="training-context-chip skill"><b>技能</b>{{ skillLabel }}</span>
      </div>
      <el-input
        v-model="inputText"
        type="textarea"
        :disabled="isTaskRunning"
        :rows="5"
        maxlength="5000"
        show-word-limit
        placeholder="例如：今天做了臀桥 3 组 12 次，靠墙静蹲 3 组 30 秒。左膝下蹲还有一点疼，大概 2 分，比上次稳定。下次可以加单腿稳定训练。"
        @keydown.enter.exact.prevent="handleParse"
      />
      <div class="input-actions">
        <span class="input-hint">Enter 生成草稿，Shift + Enter 换行</span>
        <el-button
          type="primary"
          :loading="parsing || taskSyncing"
          :disabled="isTaskRunning || !inputText.trim()"
          @click="handleParse"
        >
          {{ draft ? '重新解析' : '生成训练草稿' }}
        </el-button>
      </div>
    </el-card>

    <el-card v-if="draft && draft.status !== 'failed'" class="draft-card retrue-card" shadow="never">
      <template #header>
        <div class="card-heading draft-heading">
          <div>
            <strong>{{ isConfirmed ? '训练记录已确认' : '训练草稿' }}</strong>
            <p>{{ isConfirmed ? '正式记录已创建，可继续查看客户时间线。' : '请逐项检查内容，确认后才会写入正式记录。' }}</p>
          </div>
          <el-tag :type="isConfirmed ? 'success' : 'warning'">{{ isConfirmed ? '已确认' : '待确认' }}</el-tag>
        </div>
      </template>

      <div class="customer-row">
        <span class="field-label">客户</span>
        <template v-if="selectedCustomer">
          <span class="customer-name">{{ selectedCustomer.name || '已选择客户' }}</span>
          <el-button v-if="!isConfirmed" link type="primary" @click="openCustomerPicker">更换</el-button>
        </template>
        <el-button v-else link type="primary" @click="openCustomerPicker">选择客户</el-button>
      </div>

      <el-form label-position="top" class="draft-form">
        <el-form-item label="训练日期">
          <el-date-picker v-model="editForm.training_date" type="date" value-format="YYYY-MM-DD" class="full-width" />
        </el-form-item>

        <el-divider content-position="left">训练动作</el-divider>
        <div v-if="editForm.exercises.length === 0" class="empty-exercises">暂无动作，可在下方记录其他内容。</div>
        <div v-for="(exercise, index) in editForm.exercises" :key="index" class="exercise-row">
          <el-input v-model="exercise.exercise_name" placeholder="动作名称" class="exercise-name" :disabled="isConfirmed" />
          <el-input-number v-model="exercise.sets" :min="0" placeholder="组数" class="exercise-number" :disabled="isConfirmed" />
          <el-input-number v-model="exercise.reps" :min="0" placeholder="次数" class="exercise-number" :disabled="isConfirmed" />
          <el-input v-model="exercise.weight" placeholder="重量/阻力" class="exercise-weight" :disabled="isConfirmed" />
          <el-button
            text
            type="danger"
            class="remove-exercise"
            :disabled="isConfirmed || editForm.exercises.length <= 1"
            @click="removeExercise(index)"
          >删除</el-button>
        </div>

        <el-divider content-position="left">记录内容</el-divider>
        <el-form-item label="客户感受">
          <el-input v-model="editForm.customer_feedback" type="textarea" :rows="2" :disabled="isConfirmed" />
        </el-form-item>
        <el-form-item label="康复师观察">
          <el-input v-model="editForm.therapist_observation" type="textarea" :rows="2" :disabled="isConfirmed" />
        </el-form-item>
        <el-form-item label="下次计划">
          <el-input v-model="editForm.next_plan" type="textarea" :rows="2" :disabled="isConfirmed" />
        </el-form-item>
      </el-form>

      <div v-if="!isConfirmed" class="draft-actions">
        <el-button @click="handleCancel">取消草稿</el-button>
        <el-button type="primary" :loading="confirming" :disabled="isTaskRunning" @click="handleConfirm">确认并保存</el-button>
      </div>
    </el-card>

    <el-dialog v-model="customerPickerVisible" title="选择客户" width="420px" destroy-on-close>
      <el-input v-model="customerKeyword" clearable placeholder="输入姓名搜索" @keyup.enter="loadCandidates" />
      <div v-loading="loadingCandidates" class="candidate-list">
        <el-button
          v-for="candidate in candidates"
          :key="candidate.id"
          text
          class="candidate-item"
          @click="pickCustomer(candidate)"
        >
          <span>{{ candidate.name }}</span>
          <span class="candidate-phone">{{ candidate.phone_masked }}</span>
        </el-button>
        <el-empty v-if="candidates.length === 0" description="没有匹配的客户" :image-size="60" />
      </div>
    </el-dialog>
  </div>
</template>

<style scoped>
.training-draft-panel { container-type: inline-size; display: flex; flex-direction: column; gap: 16px; }
.training-input-card, .draft-card { width: 100%; }
.running-task-alert { width: 100%; }
.running-task-body { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.card-heading { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; }
.card-heading strong { color: var(--retrue-text); font-size: 16px; }
.card-heading p { margin: 5px 0 0; color: var(--retrue-text-secondary); font-size: 13px; font-weight: 400; line-height: 1.5; }
.session-alert { margin-bottom: 12px; }
.training-input-context { display: flex; flex-wrap: wrap; gap: 6px; margin: 0 0 8px; font-size: 13px; line-height: 1.45; }
.training-context-chip { display: inline-flex; min-width: 0; align-items: center; gap: 5px; max-width: 100%; padding: 3px 8px; border-radius: 6px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.training-context-chip b { color: var(--retrue-text-muted); font-size: 12px; font-weight: 500; }
.training-context-chip.customer { background: color-mix(in srgb, var(--retrue-primary) 10%, transparent); color: var(--retrue-primary); }
.training-context-chip.topic { background: color-mix(in srgb, var(--retrue-success) 11%, transparent); color: var(--retrue-success); }
.training-context-chip.skill { background: var(--retrue-ai-light); color: var(--retrue-ai); }
.input-actions { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-top: 12px; }
.input-hint { color: var(--retrue-text-muted); font-size: 12px; }
.customer-row { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; margin-bottom: 16px; }
.field-label { color: var(--retrue-text-secondary); }
.customer-name { font-weight: 600; }
.draft-form { width: 100%; }
.full-width { width: 100%; }
.exercise-row { display: grid; grid-template-columns: minmax(120px, 1.35fr) minmax(92px, 0.7fr) minmax(92px, 0.7fr) minmax(110px, 0.9fr) auto; align-items: center; gap: 8px; margin-bottom: 8px; }
.exercise-number { width: 100%; }
.exercise-number :deep(.el-input__inner) { padding-right: 30px; }
.exercise-weight { width: 100%; }
.remove-exercise { justify-self: end; }
.empty-exercises { padding: 10px 0; color: var(--retrue-text-muted); font-size: 13px; }
.draft-actions { display: flex; justify-content: flex-end; gap: 12px; }
.candidate-list { display: flex; flex-direction: column; max-height: 320px; margin-top: 12px; overflow-y: auto; }
.candidate-item { display: flex; width: 100%; align-items: center; justify-content: space-between; margin: 0; padding: 10px 12px; border-radius: var(--retrue-radius-sm); color: var(--retrue-text); text-align: left; }
.candidate-item:hover { background: var(--retrue-bg); }
.candidate-phone { color: var(--retrue-text-muted); }

/* 聊天卡片的可用宽度通常小于页面宽度，使用容器查询而不是视口宽度。 */
@container (max-width: 560px) {
  .exercise-row { grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); }
  .exercise-name { grid-column: 1 / -1; }
  .exercise-weight { grid-column: 1 / 2; }
  .remove-exercise { grid-column: 2 / 3; }
}

@media (max-width: 768px) {
  .card-heading, .input-actions, .draft-actions { align-items: stretch; flex-direction: column; }
  .running-task-body { align-items: stretch; flex-direction: column; gap: 6px; }
  .running-task-body :deep(.el-button) { align-self: flex-start; margin-left: 0; }
  .card-heading { gap: 10px; }
  .card-heading :deep(.el-tag) { align-self: flex-start; }
  .input-actions :deep(.el-button), .draft-actions :deep(.el-button) { width: 100%; margin-left: 0; }
  .training-input-context { gap: 5px; }
  .input-hint { order: 2; }
  .exercise-row { grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); }
  .exercise-name { grid-column: 1 / -1; }
  .exercise-weight { grid-column: 1 / 2; }
  .remove-exercise { grid-column: 2 / 3; }
}
</style>
