<script setup lang="ts">
/**
 * 统一 AI 助理工作台：普通咨询与训练补记共用一个入口和一个工作区。
 * 页面只呈现康复师需要的业务语言，任务状态用于恢复未完成的工作。
 */

import { computed, nextTick, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'

import {
  apiCancelAssistantTask,
  apiGetAssistantTask,
  apiListAssistantTasks,
  apiLookupAssistantCustomers,
} from '@/api/assistant'
import { apiCreateConversation, apiGetConversation, apiSendConversationMessage } from '@/api/conversations'
import { apiGetCustomer } from '@/api/customers'
import { apiListDrafts } from '@/api/ai'
import TrainingDraftPanel from '@/components/assistant/TrainingDraftPanel.vue'
import { suggestAssistantIntent } from '@/utils/assistantIntent'
import type {
  AiConversationMessage,
  AiDraft,
  AssistantCustomerMatch,
  AssistantTask,
  AssistantTaskStatus,
  CustomerCandidate,
  ConversationOrigin,
  ConversationType,
} from '@/types/api'

type AssistantMode = 'chat' | 'training'
type AssistantTheme = 'smart' | 'guided'

interface ChatMessage {
  role: 'assistant' | 'user'
  content: string
  sources?: string[]
}

const route = useRoute()
const router = useRouter()

const activeTaskStatuses: AssistantTaskStatus[] = [
  'pending',
  'running',
  'waiting_user',
  'waiting_confirmation',
  'blocked',
  'failed',
]

const mode = ref<AssistantMode>(readMode(route.query.mode))
const theme = ref<AssistantTheme>(readTheme(route.query.theme))
const selectedCustomerId = ref<number | null>(readNumber(route.query.customerId, route.query.customer_id))
const courseSessionId = ref<number | null>(readNumber(route.query.courseSessionId, route.query.course_session_id))
const currentCustomerName = ref('')
const tasks = ref<AssistantTask[]>([])
const activeTask = ref<AssistantTask | null>(null)
const restoredDraft = ref<AiDraft | null>(null)
const loadingTasks = ref(false)
const trainingRenderKey = ref(0)
const suggestedTrainingInput = ref('')

const conversationId = ref<number | null>(readNumber(route.query.conversationId, route.query.conversation_id))
const messages = ref<ChatMessage[]>([])
const chatInput = ref('')
const sending = ref(false)
const loadingConversation = ref(false)
const messageList = ref<HTMLElement | null>(null)
const customerLookupVisible = ref(false)
const customerLookupName = ref('')
const customerLookupLoading = ref(false)
const customerMatches = ref<AssistantCustomerMatch[]>([])
const customerLookupMessage = ref('')

const modeLabel = computed(() => (mode.value === 'training' ? '训练补记' : '日常咨询'))
const topicLabel = computed(() => {
  if (mode.value === 'chat') return '日常咨询'
  return theme.value === 'guided' ? '引导补记' : '智能补记'
})
const currentCustomerLabel = computed(() => currentCustomerName.value || (selectedCustomerId.value ? '当前客户' : '未选择客户'))
/** 将内部技能代码翻译成康复师能理解的当前工作能力。 */
const skillLabel = computed(() => {
  const code = activeTask.value?.skill_code || ''
  const labels: Record<string, string> = {
    training_record: '训练记录整理',
    'training.note': '训练记录整理',
    assessment: '评估信息整理',
  }
  if (labels[code]) return labels[code]
  if (mode.value === 'training') return '训练记录整理'
  return selectedCustomerId.value ? '客户康复咨询' : '康复训练咨询'
})
const visibleTasks = computed(() => tasks.value.filter((task) => activeTaskStatuses.includes(task.status)))
const activeTaskMessage = computed(() => {
  const task = activeTask.value
  if (!task || !['blocked', 'failed'].includes(task.status)) return ''
  const state = task.state_data || {}
  const stateMessage = state.error_message
  if (typeof task.blocked_reason === 'string' && task.blocked_reason) return task.blocked_reason
  if (typeof task.error_message === 'string' && task.error_message) return task.error_message
  if (typeof stateMessage === 'string' && stateMessage) return stateMessage
  if (task.missing_fields?.length) return `请补充：${task.missing_fields.join('、')}`
  return '这项工作需要补充信息后才能继续。'
})

const statusLabels: Record<AssistantTaskStatus, string> = {
  pending: '待开始',
  running: '处理中',
  waiting_user: '待补充信息',
  waiting_confirmation: '待确认',
  blocked: '需要处理',
  completed: '已完成',
  failed: '处理失败',
  cancelled: '已取消',
  expired: '已过期',
}

function readQueryValue(...values: unknown[]): string {
  for (const value of values) {
    const item = Array.isArray(value) ? value[0] : value
    if (typeof item === 'string' && item.trim()) return item.trim()
  }
  return ''
}

function readNumber(...values: unknown[]): number | null {
  const value = Number(readQueryValue(...values))
  return Number.isFinite(value) && value > 0 ? value : null
}

function readMode(value: unknown): AssistantMode {
  return readQueryValue(value) === 'training' ? 'training' : 'chat'
}

function readTheme(value: unknown): AssistantTheme {
  return readQueryValue(value) === 'guided' ? 'guided' : 'smart'
}

function isTrainingTask(task: AssistantTask): boolean {
  return task.task_type === 'training_record' || task.skill_code === 'training_record'
}

function taskTitle(task: AssistantTask): string {
  if (isTrainingTask(task)) return '训练补记'
  if (task.task_type === 'conversation') return '日常咨询'
  return '待完成的助理事项'
}

/** 将服务端当前步骤翻译成康复师可理解的进度提示，不直接展示内部步骤码。 */
function taskStepLabel(step?: string): string {
  const labels: Record<string, string> = {
    collect_training_description: '等待补充训练描述',
    confirm_customer: '等待选择客户',
    parsing: '正在整理训练草稿',
    drafting: '正在整理训练草稿',
    waiting_confirmation: '等待检查训练草稿',
    confirming: '正在保存确认结果',
    parse_failed: '需要调整训练描述后重试',
  }
  return (step && labels[step]) || '等待继续处理'
}

function taskCustomerLabel(task: AssistantTask): string {
  return task.customer_name || (task.customer ? `客户 #${task.customer}` : '')
}

function taskInput(task: AssistantTask): string {
  const stateValue = task.state_data?.input_text
  if (typeof stateValue === 'string' && stateValue) return stateValue
  return task.input_text || ''
}

function taskDraftFromState(task: AssistantTask): AiDraft | null {
  if (task.draft) return task.draft
  const candidate = task.state_data?.draft ?? task.state_data?.ai_draft
  if (!candidate || typeof candidate !== 'object') return null
  const draft = candidate as Partial<AiDraft>
  return typeof draft.id === 'number' && typeof draft.status === 'string' && !!draft.ai_result
    ? candidate as AiDraft
    : null
}

function taskDraftId(task: AssistantTask): number | null {
  const directId = Number(task.draft_id || task.draft_resource_id || 0)
  if (Number.isFinite(directId) && directId > 0) return directId
  const stateId = Number(task.state_data?.draft_id || 0)
  return Number.isFinite(stateId) && stateId > 0 ? stateId : null
}

function taskUpdatedAt(task: AssistantTask): string {
  return task.last_activity_at || task.updated_at || task.created_at || ''
}

function formatTaskTime(value: string): string {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  return new Intl.DateTimeFormat('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' }).format(date)
}

function queryForAssistant(overrides: Record<string, string | undefined> = {}): Record<string, string> {
  const query: Record<string, string> = {
    mode: overrides.mode || mode.value,
    theme: overrides.theme || theme.value,
  }
  if (selectedCustomerId.value) query.customerId = String(selectedCustomerId.value)
  if (mode.value === 'training' && courseSessionId.value) query.courseSessionId = String(courseSessionId.value)
  if (overrides.taskId) query.taskId = overrides.taskId
  if (overrides.conversationId) query.conversationId = overrides.conversationId
  return query
}

/** 切换普通咨询与训练补记，并让地址栏保留可分享的工作上下文。 */
async function switchMode(nextMode: AssistantMode): Promise<void> {
  if (mode.value === nextMode) return
  mode.value = nextMode
  if (nextMode === 'chat') suggestedTrainingInput.value = ''
  activeTask.value = null
  restoredDraft.value = null
  trainingRenderKey.value += 1
  if (nextMode === 'chat') resetConversationGreeting()
  await router.replace({ name: 'assistant', query: queryForAssistant() })
}

/**
 * 普通输入疑似训练经过时，只提示康复师选择，不自动调用补记能力。
 * 返回 true 表示本次输入已切换到补记或被关闭，调用方不再发送普通消息。
 */
async function offerTrainingRecord(content: string): Promise<boolean> {
  const suggestion = suggestAssistantIntent(content)
  if (suggestion.intent !== 'training_record') return false
  try {
    await ElMessageBox.confirm(
      '这段内容看起来像一次训练经过。要帮你整理成训练草稿吗？草稿检查并确认后才会保存。',
      '整理为训练补记？',
      {
        confirmButtonText: '整理成补记',
        cancelButtonText: '按咨询发送',
        distinguishCancelAndClose: true,
        type: 'info',
      },
    )
    suggestedTrainingInput.value = content
    chatInput.value = ''
    await switchMode('training')
    return true
  } catch (action) {
    // 明确点“按咨询发送”才继续普通对话；关闭弹窗时保留输入，不替用户发送。
    return action === 'close'
  }
}

/** 加载当前客户名称，手机号等敏感资料不在助理页展示。 */
async function loadCustomer(): Promise<void> {
  if (!selectedCustomerId.value) {
    currentCustomerName.value = ''
    return
  }
  try {
    const customer = await apiGetCustomer(selectedCustomerId.value)
    currentCustomerName.value = customer.name
  } catch {
    currentCustomerName.value = ''
  }
}

/** 根据草稿资源引用恢复 AI 草稿。 */
async function loadTaskDraft(task: AssistantTask): Promise<AiDraft | null> {
  const fromState = taskDraftFromState(task)
  if (fromState) return fromState
  const draftId = taskDraftId(task)
  if (!draftId) return null
  try {
    const drafts = await apiListDrafts()
    return drafts.find((draft) => draft.id === draftId) || null
  } catch {
    return null
  }
}

/** 加载任务的最新状态；恢复只读取服务端状态，不在前端伪造状态转换。 */
async function resumeTask(task: AssistantTask, updateAddress = true): Promise<void> {
  let latest = task
  try {
    latest = await apiGetAssistantTask(task.id)
  } catch {
    // 列表数据已经足够渲染恢复入口，详情接口不可用时继续使用列表快照。
  }
  activeTask.value = latest
  mode.value = isTrainingTask(latest) ? 'training' : 'chat'
  selectedCustomerId.value = latest.customer || selectedCustomerId.value
  currentCustomerName.value = latest.customer_name || currentCustomerName.value
  if (latest.context_resource_type === 'course_session') {
    courseSessionId.value = readNumber(latest.context_resource_id)
  }
  const taskTopic = latest.state_data?.topic || latest.origin
  if (typeof taskTopic === 'string' && taskTopic.includes('引导')) theme.value = 'guided'
  restoredDraft.value = isTrainingTask(latest) ? await loadTaskDraft(latest) : null
  trainingRenderKey.value += 1
  if (updateAddress) {
    await router.replace({ name: 'assistant', query: queryForAssistant({ taskId: String(latest.id) }) })
  }
  if (mode.value === 'chat') await loadConversation()
}

/** 查询未完成任务，并在地址栏带 taskId 时自动打开对应任务。 */
async function loadTasks(): Promise<void> {
  loadingTasks.value = true
  try {
    const result = await apiListAssistantTasks({ resumable: true })
    tasks.value = result
      .filter((task) => activeTaskStatuses.includes(task.status))
      .sort((left, right) => taskUpdatedAt(right).localeCompare(taskUpdatedAt(left)))
    const taskId = readNumber(route.query.taskId, route.query.task_id, route.query.assistant_task_id)
    const requestedTask = taskId ? tasks.value.find((task) => task.id === taskId) : null
    if (requestedTask) await resumeTask(requestedTask, false)
  } catch {
    // 任务列表不可用时保留普通咨询和训练补记能力，页面仍可继续当前工作。
    tasks.value = []
  } finally {
    loadingTasks.value = false
  }
}

/** 新建任务后立即加入顶部待办列表，确保离开页面后可继续。 */
function handleTaskCreated(task: AssistantTask): void {
  activeTask.value = task
  if (!tasks.value.some((item) => item.id === task.id)) tasks.value = [task, ...tasks.value]
}

/** 保存任务上下文后的本地同步，仅更新后端允许的可恢复字段。 */
function handleTaskUpdated(task: AssistantTask): void {
  activeTask.value = task
  const nextTasks = tasks.value.filter((item) => item.id !== task.id)
  if (activeTaskStatuses.includes(task.status)) nextTasks.unshift(task)
  tasks.value = nextTasks
}

/** 暂时离开任务。稍后不改变任务生命周期状态，任务会继续出现在未完成列表中。 */
async function leaveTaskForLater(task?: AssistantTask): Promise<void> {
  if (task && activeTask.value?.id !== task.id) return
  activeTask.value = null
  restoredDraft.value = null
  trainingRenderKey.value += 1
  await router.replace({ name: 'assistant', query: queryForAssistant({ taskId: undefined }) })
}

/** 取消任务需要二次确认，取消不会删除任何正式业务记录。 */
async function abandonTask(task: AssistantTask): Promise<void> {
  try {
    await ElMessageBox.confirm('放弃后将不再保留这项待办，已存在的正式记录不会受影响。', '放弃这项任务？', {
      confirmButtonText: '放弃任务',
      cancelButtonText: '继续保留',
      type: 'warning',
    })
  } catch {
    return
  }
  await apiCancelAssistantTask(task.id)
  tasks.value = tasks.value.filter((item) => item.id !== task.id)
  if (activeTask.value?.id === task.id) {
    activeTask.value = null
    restoredDraft.value = null
    trainingRenderKey.value += 1
  }
  ElMessage.info('任务已放弃')
}

/** 从训练补记草稿组件接收客户选择，更新页面顶部上下文。 */
function handleCustomerSelected(candidate: CustomerCandidate): void {
  selectedCustomerId.value = candidate.id
  currentCustomerName.value = candidate.name
  if (activeTask.value) activeTask.value = { ...activeTask.value, customer: candidate.id, customer_name: candidate.name }
}

/** 按姓名查询当前康复师客户；同名时不自动猜测，交由康复师选择。 */
async function lookupCustomerByName(): Promise<void> {
  const name = customerLookupName.value.trim()
  if (!name || customerLookupLoading.value) return
  customerLookupLoading.value = true
  customerLookupMessage.value = ''
  customerMatches.value = []
  try {
    const matches = await apiLookupAssistantCustomers(name)
    if (matches.length === 0) {
      customerLookupMessage.value = '没有找到同名客户，请检查姓名。'
      return
    }
    if (matches.length === 1) {
      await chooseChatCustomer(matches[0])
      ElMessage.success(`已选择客户：${matches[0].name}`)
      return
    }
    customerMatches.value = matches
    customerLookupVisible.value = false
  } catch {
    customerLookupMessage.value = '查询失败，请稍后重试。'
  } finally {
    customerLookupLoading.value = false
  }
}

/** 选择具体同名客户后重建普通会话，防止把两位客户的上下文混在同一会话。 */
async function chooseChatCustomer(candidate: AssistantCustomerMatch): Promise<void> {
  const changed = selectedCustomerId.value !== candidate.id
  const pendingInput = chatInput.value
  selectedCustomerId.value = candidate.id
  currentCustomerName.value = candidate.name
  customerMatches.value = []
  customerLookupVisible.value = false
  if (changed && mode.value === 'chat') {
    resetConversationGreeting()
    chatInput.value = pendingInput
  }
  await router.replace({ name: 'assistant', query: queryForAssistant() })
}

/** 确认训练记录后移除待办卡片，但保留当前页面的完成结果。 */
function handleTrainingConfirmed(): void {
  if (activeTask.value) tasks.value = tasks.value.filter((task) => task.id !== activeTask.value?.id)
}

/** 训练草稿取消后回到空白补记工作区。 */
function handleTrainingCancelled(): void {
  if (activeTask.value) tasks.value = tasks.value.filter((task) => task.id !== activeTask.value?.id)
  activeTask.value = null
  restoredDraft.value = null
  trainingRenderKey.value += 1
}

function conversationScope(): { origin: ConversationOrigin; conversation_type: ConversationType } {
  if (selectedCustomerId.value) return { origin: 'customer_detail', conversation_type: 'customer_discussion' }
  return { origin: 'general', conversation_type: 'general' }
}

function greeting(): string {
  return selectedCustomerId.value
    ? '你好，这里可以围绕当前客户讨论训练、恢复进展和记录内容。'
    : '你好，我可以协助你整理训练记录，也可以回答康复训练相关问题。'
}

function resetConversationGreeting(): void {
  messages.value = [{ role: 'assistant', content: greeting() }]
  conversationId.value = null
  chatInput.value = ''
}

function mapConversationMessage(message: AiConversationMessage): ChatMessage | null {
  if (message.role !== 'assistant' && message.role !== 'user') return null
  const rawSources = message.metadata?.sources
  const sources = Array.isArray(rawSources) ? rawSources.filter((item): item is string => typeof item === 'string') : undefined
  return { role: message.role, content: message.content, sources }
}

/** 恢复地址栏指定的普通会话，否则从欢迎语开始。 */
async function loadConversation(): Promise<void> {
  if (!conversationId.value) {
    resetConversationGreeting()
    return
  }
  loadingConversation.value = true
  try {
    const conversation = await apiGetConversation(conversationId.value)
    const history = conversation.messages.map(mapConversationMessage).filter((item): item is ChatMessage => item !== null)
    messages.value = history.length ? history : [{ role: 'assistant', content: greeting() }]
  } catch {
    resetConversationGreeting()
  } finally {
    loadingConversation.value = false
    scrollToBottom()
  }
}

async function ensureConversation(): Promise<number> {
  if (conversationId.value !== null) return conversationId.value
  const scope = conversationScope()
  const conversation = await apiCreateConversation({
    customer: selectedCustomerId.value,
    ...scope,
    context_resource_type: 'assistant',
    context_resource_id: activeTask.value ? String(activeTask.value.id) : '',
  })
  conversationId.value = conversation.id
  await router.replace({ name: 'assistant', query: queryForAssistant({ conversationId: String(conversation.id) }) })
  return conversation.id
}

function scrollToBottom(): void {
  void nextTick(() => {
    if (messageList.value) messageList.value.scrollTop = messageList.value.scrollHeight
  })
}

/** 发送普通咨询消息，始终使用可追溯的 Conversation API。 */
async function sendChat(): Promise<void> {
  const content = chatInput.value.trim()
  if (!content || sending.value) return
  if (await offerTrainingRecord(content)) return
  messages.value.push({ role: 'user', content })
  chatInput.value = ''
  sending.value = true
  scrollToBottom()
  try {
    const id = await ensureConversation()
    const result = await apiSendConversationMessage(id, content)
    const assistantMessage = mapConversationMessage(result.assistant_message)
    if (assistantMessage) messages.value.push(assistantMessage)
    if (result.memory_candidates.length) ElMessage.info(`本轮发现 ${result.memory_candidates.length} 条待确认信息，可在客户知识库中处理`)
  } catch {
    ElMessage.error('暂时无法回答，请稍后重试')
  } finally {
    sending.value = false
    scrollToBottom()
  }
}

function goBack(): void {
  if (window.history.length > 1) router.back()
  else router.push({ name: 'dashboard' })
}

onMounted(async () => {
  await loadCustomer()
  await loadTasks()
  if (!activeTask.value && mode.value === 'chat') await loadConversation()
})
</script>

<template>
  <div class="assistant-page retrue-page">
    <header class="assistant-page-header">
      <div class="assistant-title-wrap">
        <span class="assistant-title-mark" aria-hidden="true"><el-icon><ChatDotRound /></el-icon></span>
        <div>
          <h1>智能助理</h1>
          <p>把咨询、训练补记和待办工作放在同一个地方。</p>
        </div>
      </div>
      <div class="assistant-header-actions">
        <el-button text aria-label="返回" @click="goBack"><el-icon><Close /></el-icon></el-button>
      </div>
    </header>

    <section class="assistant-mode-bar" aria-label="选择工作模式">
      <div>
        <strong>{{ modeLabel }}</strong>
        <span>{{ mode === 'training' ? '整理训练经过，检查草稿后再保存。' : '围绕训练与客户情况进行日常咨询。' }}</span>
      </div>
      <el-radio-group :model-value="mode" size="small" @change="switchMode">
        <el-radio-button value="chat">日常咨询</el-radio-button>
        <el-radio-button value="training">训练补记</el-radio-button>
      </el-radio-group>
    </section>

    <section v-if="loadingTasks" class="assistant-task-section">
      <el-skeleton :rows="2" animated />
    </section>
    <section v-else-if="visibleTasks.length" class="assistant-task-section" aria-labelledby="unfinished-heading">
      <div class="section-heading">
        <div>
          <h2 id="unfinished-heading">未完成的工作</h2>
          <p>可以继续处理，也可以先放到稍后。</p>
        </div>
        <el-tag type="warning" effect="plain">{{ visibleTasks.length }} 项</el-tag>
      </div>
      <div class="task-list">
        <el-card v-for="task in visibleTasks" :key="task.id" shadow="never" class="task-card retrue-card">
          <div class="task-card-heading">
            <div>
              <strong>{{ taskTitle(task) }}</strong>
              <span v-if="taskCustomerLabel(task)">{{ taskCustomerLabel(task) }}</span>
            </div>
            <el-tag :type="task.status === 'blocked' || task.status === 'failed' ? 'danger' : 'warning'" size="small">
              {{ statusLabels[task.status] || '待处理' }}
            </el-tag>
          </div>
          <p v-if="taskInput(task)" class="task-summary">{{ taskInput(task) }}</p>
          <p v-else-if="task.current_step" class="task-summary">{{ taskStepLabel(task.current_step) }}</p>
          <div class="task-card-footer">
            <span>{{ formatTaskTime(taskUpdatedAt(task)) }}</span>
            <div class="task-actions">
              <el-button link type="primary" @click="resumeTask(task)">继续</el-button>
              <el-button link @click="leaveTaskForLater(task)">稍后</el-button>
              <el-button link type="danger" @click="abandonTask(task)">放弃</el-button>
            </div>
          </div>
        </el-card>
      </div>
    </section>

    <el-alert
      v-if="activeTaskMessage"
      :title="activeTaskMessage"
      type="warning"
      :closable="false"
      show-icon
      class="assistant-blocked-alert"
    />

    <section class="assistant-workspace">
      <el-card v-if="mode === 'chat'" class="chat-workspace retrue-card" shadow="never">
        <template #header>
          <div class="workspace-heading">
            <div>
              <strong>{{ selectedCustomerId ? `与${currentCustomerLabel}讨论` : '康复训练咨询' }}</strong>
              <span>内容会保存在本次会话中，方便后续查看。</span>
            </div>
            <el-tag type="info" effect="plain">仅供专业辅助</el-tag>
          </div>
        </template>
        <main ref="messageList" class="message-list" aria-live="polite">
          <el-skeleton v-if="loadingConversation" :rows="3" animated />
          <template v-else>
            <div v-for="(message, index) in messages" :key="`${index}-${message.role}`" class="message-row" :class="message.role">
              <div class="message-bubble">{{ message.content }}</div>
              <small v-if="message.sources?.length">参考动作：{{ message.sources.join('、') }}</small>
            </div>
            <div v-if="sending" class="message-row assistant"><div class="message-bubble">正在整理回复…</div></div>
          </template>
        </main>
        <footer class="chat-input-area">
          <div class="assistant-input-context" aria-label="当前工作上下文">
            <el-popover v-model:visible="customerLookupVisible" placement="top-start" :width="320" trigger="click">
              <template #reference>
                <button type="button" class="context-inline-chip customer customer-context-trigger">
                  <b>客户</b>{{ currentCustomerLabel }}<span class="customer-context-arrow">⌄</span>
                </button>
              </template>
              <div class="customer-lookup-popover">
                <strong>按姓名定位客户</strong>
                <p>同名客户会让你选择具体档案。</p>
                <div class="customer-lookup-form">
                  <el-input v-model="customerLookupName" maxlength="64" placeholder="输入客户姓名" @keyup.enter="lookupCustomerByName" />
                  <el-button type="primary" :loading="customerLookupLoading" @click="lookupCustomerByName">查询</el-button>
                </div>
                <small v-if="customerLookupMessage">{{ customerLookupMessage }}</small>
              </div>
            </el-popover>
            <span class="context-inline-chip topic"><b>主题</b>{{ topicLabel }}</span>
            <span class="context-inline-chip skill"><b>技能</b>{{ skillLabel }}</span>
          </div>
          <div v-if="customerMatches.length > 1" class="customer-match-bar" aria-live="polite">
            <span>找到 {{ customerMatches.length }} 位同名客户，请选择：</span>
            <el-button
              v-for="candidate in customerMatches"
              :key="candidate.id"
              plain
              size="small"
              @click="chooseChatCustomer(candidate)"
            >
              {{ candidate.name }} · {{ candidate.phone_masked || '无手机号' }}<template v-if="candidate.main_issue"> · {{ candidate.main_issue }}</template>
            </el-button>
          </div>
          <el-input
            v-model="chatInput"
            type="textarea"
            :autosize="{ minRows: 2, maxRows: 5 }"
            maxlength="5000"
            show-word-limit
            placeholder="例如：臀桥怎么做？或帮我梳理一下今天的训练重点。"
            @keydown.enter.exact.prevent="sendChat"
          />
          <div class="chat-input-footer">
            <span>Enter 发送，Shift + Enter 换行</span>
            <el-button type="primary" :loading="sending" :disabled="!chatInput.trim()" @click="sendChat">发送</el-button>
          </div>
        </footer>
      </el-card>

      <TrainingDraftPanel
        v-else
        :key="trainingRenderKey"
        :customer-id="selectedCustomerId"
        :course-session-id="courseSessionId"
        :assistant-task-id="activeTask?.id || null"
        :initial-task="activeTask"
        :initial-draft="restoredDraft"
        :initial-input-text="suggestedTrainingInput"
        :customer-name="currentCustomerLabel"
        :topic="topicLabel"
        :skill-label="skillLabel"
        :invocation-mode="theme"
        @task-created="handleTaskCreated"
        @task-updated="handleTaskUpdated"
        @customer-selected="handleCustomerSelected"
        @confirmed="handleTrainingConfirmed"
        @cancelled="handleTrainingCancelled"
      />
    </section>

    <div v-if="activeTask" class="assistant-later-action">
      <el-button text @click="leaveTaskForLater">稍后继续</el-button>
    </div>
  </div>
</template>

<style scoped>
.assistant-page { display: flex; min-height: calc(100vh - 48px); flex-direction: column; gap: 18px; padding-bottom: 28px; }
.assistant-page-header { display: flex; align-items: center; justify-content: space-between; gap: 18px; }
.assistant-title-wrap, .assistant-header-actions, .workspace-heading, .task-card-heading, .task-card-footer, .task-actions, .chat-input-footer { display: flex; align-items: center; }
.assistant-title-wrap { gap: 12px; }
.assistant-title-mark { display: grid; width: 40px; height: 40px; place-items: center; border-radius: var(--retrue-radius-md); background: var(--retrue-ai-light); color: var(--retrue-ai); font-size: 20px; }
.assistant-page h1 { margin: 0; color: var(--retrue-text); font-size: 24px; }
.assistant-page-header p, .assistant-mode-bar span, .section-heading p, .workspace-heading span { margin: 4px 0 0; color: var(--retrue-text-secondary); font-size: 13px; }
.assistant-header-actions { gap: 16px; }
.assistant-mode-bar { display: flex; align-items: center; justify-content: space-between; gap: 16px; padding: 14px 18px; border: 1px solid var(--retrue-border); border-radius: var(--retrue-radius-lg); background: var(--retrue-surface); }
.assistant-mode-bar > div { display: flex; min-width: 0; flex-direction: column; gap: 2px; }
.assistant-task-section { display: flex; flex-direction: column; gap: 12px; }
.section-heading { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.section-heading h2 { margin: 0; color: var(--retrue-text); font-size: 17px; }
.task-list { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
.task-card { min-width: 0; }
.task-card-heading { align-items: flex-start; justify-content: space-between; gap: 12px; }
.task-card-heading > div { display: flex; min-width: 0; flex-direction: column; gap: 4px; }
.task-card-heading span, .task-card-footer > span { color: var(--retrue-text-muted); font-size: 12px; }
.task-summary { display: -webkit-box; margin: 14px 0; overflow: hidden; color: var(--retrue-text-secondary); font-size: 13px; line-height: 1.55; -webkit-box-orient: vertical; -webkit-line-clamp: 2; }
.task-card-footer { justify-content: space-between; gap: 8px; }
.task-actions { flex-wrap: wrap; justify-content: flex-end; }
.assistant-blocked-alert { margin-top: -4px; }
.assistant-workspace { display: flex; min-width: 0; flex: 1; flex-direction: column; }
.chat-workspace { display: flex; min-height: 560px; flex: 1; flex-direction: column; }
.workspace-heading { align-items: flex-start; justify-content: space-between; gap: 16px; }
.workspace-heading > div { display: flex; min-width: 0; flex-direction: column; gap: 2px; }
.message-list { display: flex; min-height: 320px; flex: 1; flex-direction: column; gap: 12px; padding: 18px 4px; overflow-y: auto; }
.message-row { display: flex; max-width: min(720px, 86%); flex-direction: column; gap: 4px; }
.message-row.user { align-self: flex-end; align-items: flex-end; }
.message-bubble { padding: 11px 14px; border-radius: var(--retrue-radius-md); background: var(--retrue-bg); color: var(--retrue-text); font-size: 14px; line-height: 1.6; white-space: pre-wrap; }
.message-row.user .message-bubble { background: var(--retrue-primary); color: var(--retrue-on-primary); }
.message-row small { color: var(--retrue-text-muted); font-size: 11px; }
.chat-input-area { padding-top: 12px; border-top: 1px solid var(--retrue-border); }
.assistant-input-context { display: flex; flex-wrap: wrap; gap: 6px; margin: 0 0 8px; font-size: 13px; line-height: 1.45; }
.context-inline-chip { display: inline-flex; min-width: 0; align-items: center; gap: 5px; max-width: 100%; padding: 3px 8px; border-radius: 6px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.context-inline-chip b { color: var(--retrue-text-muted); font-size: 12px; font-weight: 500; }
.context-inline-chip.customer { background: color-mix(in srgb, var(--retrue-primary) 10%, transparent); color: var(--retrue-primary); }
.context-inline-chip.topic { background: color-mix(in srgb, var(--retrue-success) 11%, transparent); color: var(--retrue-success); }
.context-inline-chip.skill { background: var(--retrue-ai-light); color: var(--retrue-ai); }
.customer-context-trigger { border: 0; cursor: pointer; font: inherit; }
.customer-context-trigger:hover { filter: brightness(.96); }
.customer-context-arrow { margin-left: 1px; color: var(--retrue-text-muted); font-size: 12px; }
.customer-lookup-popover { display: flex; flex-direction: column; gap: 8px; }
.customer-lookup-popover strong { color: var(--retrue-text); font-size: 14px; }
.customer-lookup-popover p, .customer-lookup-popover small { margin: 0; color: var(--retrue-text-secondary); font-size: 12px; line-height: 1.5; }
.customer-lookup-form { display: flex; gap: 8px; }
.customer-lookup-form :deep(.el-button) { flex: 0 0 auto; margin-left: 0; }
.customer-match-bar { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; margin: 0 0 8px; padding: 7px 8px; border: 1px solid color-mix(in srgb, var(--retrue-ai) 24%, var(--retrue-border)); border-radius: var(--retrue-radius-sm); background: var(--retrue-ai-light); color: var(--retrue-text-secondary); font-size: 13px; line-height: 1.45; }
.customer-match-bar :deep(.el-button) { max-width: 100%; margin-left: 0; overflow: hidden; text-overflow: ellipsis; }
.chat-input-footer { justify-content: space-between; gap: 12px; margin-top: 8px; }
.chat-input-footer span { color: var(--retrue-text-muted); font-size: 12px; }
.assistant-later-action { display: flex; justify-content: flex-end; }

@media (max-width: 768px) {
  .assistant-page { min-height: calc(100dvh - 104px); gap: 12px; padding-bottom: 12px; }
  .assistant-page-header, .assistant-mode-bar, .workspace-heading, .task-card-footer { align-items: stretch; flex-direction: column; }
  .assistant-page-header { gap: 10px; }
  .assistant-header-actions { justify-content: flex-end; }
  .assistant-page h1 { font-size: 21px; }
  .assistant-mode-bar { gap: 12px; padding: 14px; }
  .assistant-mode-bar :deep(.el-radio-group) { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); width: 100%; }
  .assistant-mode-bar :deep(.el-radio-button), .assistant-mode-bar :deep(.el-radio-button__inner) { width: 100%; }
  .task-list { grid-template-columns: minmax(0, 1fr); }
  .assistant-input-context { gap: 5px; }
  .customer-lookup-form { align-items: stretch; flex-direction: column; }
  .customer-lookup-form :deep(.el-button) { width: 100%; }
  .task-actions { justify-content: flex-start; }
  .chat-workspace { min-height: 0; }
  .message-list { min-height: 260px; padding: 14px 0; }
  .message-row { max-width: 94%; }
  .chat-input-footer { align-items: stretch; flex-direction: column; }
  .chat-input-footer :deep(.el-button) { width: 100%; margin-left: 0; }
}
</style>
