<script setup lang="ts">
/**
 * 统一 AI 助理工作台：聊天即工作台。
 * 康复师在一个聊天页中完成咨询、选择客户、查看客户信息、补记训练、填写评估、
 * 随访、课程相关操作、草稿修改和正式确认。消息与可交互业务卡片按时间顺序
 * 显示在同一消息流中，页面关闭后可从任务恢复。
 */

import { computed, nextTick, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'

import {
  apiCancelAssistantTask,
  apiGetAssistantTask,
  apiGetBatchState,
  apiListAssistantTasks,
  apiResumeAssistantTurn,
  apiSearchBatchItemCustomer,
  apiSelectAssistantCustomer,
  apiSelectBatchItemCustomer,
  apiSendAssistantTurn,
} from '@/api/assistant'
import type { AssistantCard, AssistantTurnResult, BatchItem, BatchState, BatchSummary } from '@/api/assistant'
import { apiListDrafts } from '@/api/ai'
import { apiCreateConversation, apiGetConversation } from '@/api/conversations'
import { apiGetCustomer } from '@/api/customers'
import AssistantCardRenderer from '@/components/assistant/AssistantCardRenderer.vue'
import type {
  AiConversationMessage,
  AssistantCustomerMatch,
  AiDraft,
  AssistantTask,
  AssistantTaskStatus,
  ConversationOrigin,
  ConversationType,
} from '@/types/api'

interface ChatMessage {
  role: 'assistant' | 'user'
  content: string
  sources?: string[]
}

type ChatItem =
  | { kind: 'message'; message: ChatMessage }
  | { kind: 'card'; card: AssistantCard }

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

const selectedCustomerId = ref<number | null>(readNumber(route.query.customerId, route.query.customer_id))
const courseSessionId = ref<number | null>(readNumber(route.query.courseSessionId, route.query.course_session_id))
const currentCustomerName = ref('')
const tasks = ref<AssistantTask[]>([])
const activeTask = ref<AssistantTask | null>(null)
const loadingTasks = ref(false)

const conversationId = ref<number | null>(readNumber(route.query.conversationId, route.query.conversation_id))
const items = ref<ChatItem[]>([])
const chatInput = ref('')
const sending = ref(false)
const loadingConversation = ref(false)
const messageList = ref<HTMLElement | null>(null)

const currentCustomerLabel = computed(() => currentCustomerName.value || (selectedCustomerId.value ? '当前客户' : '未选择客户'))

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

function taskTitle(task: AssistantTask): string {
  if (task.task_type === 'training_record' || task.skill_code === 'training_record') return '训练补记'
  if (task.task_type === 'conversation') return '日常咨询'
  if (task.task_type === 'assistant_turn') return 'AI 助理事项'
  return '待完成的助理事项'
}

function taskCustomerLabel(task: AssistantTask): string {
  return task.customer_name || (task.customer ? `客户 #${task.customer}` : '')
}

function taskInput(task: AssistantTask): string {
  const stateValue = task.state_data?.input_text
  if (typeof stateValue === 'string' && stateValue) return stateValue
  return task.input_text || ''
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
  const query: Record<string, string> = {}
  if (selectedCustomerId.value) query.customerId = String(selectedCustomerId.value)
  if (courseSessionId.value) query.courseSessionId = String(courseSessionId.value)
  if (overrides.taskId) query.taskId = overrides.taskId
  if (overrides.conversationId) query.conversationId = overrides.conversationId
  return query
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

/** 从卡片集合中取出客户选择候选。 */
function customerCandidatesFrom(cards: AssistantCard[]): AssistantCustomerMatch[] {
  const card = cards.find((item) => item.type === 'customer_selection')
  return card?.customer_candidates ?? []
}

/** 判断聊天流中是否已经存在指定卡片，避免刷新或重复回合重复插入。 */
function hasCard(cardId: string): boolean {
  return items.value.some((item) => item.kind === 'card' && item.card.id === cardId)
}

/** 向聊天流追加卡片；相同引用只保留一张，保证恢复不会重复展示待办。 */
function appendCard(card: AssistantCard): void {
  const existingIndex = items.value.findIndex((item) => item.kind === 'card' && item.card.id === card.id)
  if (existingIndex >= 0) {
    const existing = items.value[existingIndex]
    if (existing?.kind === 'card') existing.card = { ...existing.card, ...card }
    return
  }
  items.value.push({ kind: 'card', card })
}

/** 应用统一回合返回结果：回复文本 + 业务卡片按序追加到消息流。 */
async function applyTurnResult(result: AssistantTurnResult): Promise<void> {
  if (result.reply_content) {
    items.value.push({ kind: 'message', message: { role: 'assistant', content: result.reply_content } })
  }
  const cards = result.cards ?? []
  for (const card of cards) {
    appendCard(card)
  }

  // 批量任务创建后直接开始第一项；概览卡只是进度展示，不再要求康复师先点击“开始”。
  if (result.intent === 'multi_customer_training_record' || cards.some((card) => card.type === 'batch_overview')) {
    await restoreBatchTask(result.task_id, { appendOverview: false, announceProgress: false })
  }
  const candidates = customerCandidatesFrom(cards)
  if (candidates.length > 1) {
    items.value.push({ kind: 'message', message: { role: 'assistant', content: '找到多位同名客户，请在上面选择具体的档案。' } })
  } else if (result.current_step === 'wait_customer_name' && candidates.length === 0) {
    items.value.push({ kind: 'message', message: { role: 'assistant', content: '请告诉我客户姓名，我来帮你定位客户档案。' } })
  }
}

/** 发送消息，统一走受控的回合编排接口。 */
async function sendChat(): Promise<void> {
  const content = chatInput.value.trim()
  if (!content || sending.value) return
  items.value.push({ kind: 'message', message: { role: 'user', content } })
  chatInput.value = ''
  sending.value = true
  scrollToBottom()
  try {
    const id = await ensureConversation()
    const result = await apiSendAssistantTurn({
      message: content,
      conversation_id: id,
      customer_id: selectedCustomerId.value,
    })
    if (result.task_id) activeTask.value = { ...(activeTask.value || {}), id: result.task_id, status: result.status } as AssistantTask
    await applyTurnResult(result)
  } catch {
    ElMessage.error('暂时无法回答，请稍后重试')
  } finally {
    sending.value = false
    scrollToBottom()
  }
}

/** 选择同名客户，通过服务端从暂停节点继续，不本地伪造状态。 */
async function selectCustomer(card: AssistantCard, candidate: AssistantCustomerMatch): Promise<void> {
  const taskId = card.resource_refs?.task_id
  if (typeof taskId !== 'number') return
  // 批量补记子项的客户选择走批量确认逻辑。
  if (card.resource_refs?.item_id != null) {
    await selectBatchCustomer(card, candidate)
    return
  }
  selectedCustomerId.value = candidate.id
  currentCustomerName.value = candidate.name
  try {
    const result = await apiSelectAssistantCustomer(taskId, candidate.id)
    // 选择成功后立即锁定原选择卡，避免再次选择或继续显示“取消”。
    // 后续流程以服务端返回的草稿卡为准。
    card.status = 'completed'
    card.allowed_actions = []
    card.resource_refs = { ...card.resource_refs, customer_id: candidate.id, customer_name: candidate.name }
    await applyTurnResult(result)
    scrollToBottom()
  } catch {
    ElMessage.error('选择客户失败，请稍后重试')
  }
}

/** 客户预选卡的「确认」：仅把该预选卡收起为只读，不改变任务生命周期。
 *  正式保存仍由草稿卡的人工确认完成。 */
function handleConfirmed(card: AssistantCard): void {
  if (card.type === 'customer_preselected') {
    card.status = 'completed'
    card.allowed_actions = []
  }
}

/** 卡片操作（风险核查的补充/继续/暂不处理，客户摘要的查看/发起操作等）。 */
async function handleCardAction(_card: AssistantCard, action: string): Promise<void> {
  if (action === 'dismiss' || action === 'cancel') {
    // 暂不处理/取消：不改变任务生命周期，保留在未完成列表中。
    return
  }
  if (action === 'supplement' || action === 'continue') {
    chatInput.value = ''
    return
  }
  // 客户摘要卡片上的「开始补记/发起评估/查看训练/查看课程」：以自然语言发起新回合。
  const promptMap: Record<string, string> = {
    start_record: '帮客户补记今天的训练',
    start_assessment: '帮客户做评估',
    view_recent_training: '查看这个客户最近的训练记录',
    view_schedule: '查看这个客户的课程安排',
  }
  const prompt = promptMap[action]
  if (prompt) {
    chatInput.value = prompt
    await sendChat()
  }
}

/** 根据批量状态生成完成汇总；只有没有当前子项时才允许展示。 */
function batchSummaryFromState(state: BatchState): BatchSummary {
  const succeeded = state.items.filter((item) => item.status === 'completed').length
  const skipped = state.items.filter((item) => item.status === 'skipped').length
  const failed = state.items.filter((item) => item.status === 'failed').length
  return {
    task_id: state.task_id,
    total_items: state.total_items,
    succeeded,
    skipped,
    failed,
    lines: state.items.map((item) => ({
      sequence: item.sequence,
      customer_name: item.customer_name || item.customer_name_hint,
      status: item.status,
      training_record_id: item.training_record_id,
    })),
  }
}

/** 把批量概览卡加入聊天流；概览只负责显示进度，不允许操作后续子项。 */
function appendBatchOverview(state: BatchState): void {
  appendCard({
    id: `batch_overview:${state.task_id}`,
    type: 'batch_overview',
    status: state.current_item_id == null ? 'completed' : 'waiting_user',
    resource_refs: { task_id: state.task_id, total_items: state.total_items },
    allowed_actions: state.current_item_id == null ? [] : ['continue', 'cancel'],
  })
}

/** 恢复指定批量子项的草稿卡，不重新确认客户或创建新草稿。 */
async function restoreBatchDraftCard(taskId: number, item: BatchItem): Promise<void> {
  if (!item.draft_id) {
    // 服务端状态已绑定客户但缺少草稿引用时，回到当前项搜索入口，避免伪造草稿。
    await startBatchItem({} as AssistantCard, taskId, item)
    return
  }
  const cardId = `batch_draft:${taskId}:${item.id}`
  if (hasCard(cardId)) return
  try {
    const drafts = await apiListDrafts()
    const draft: AiDraft | undefined = drafts.find((candidate) => candidate.id === item.draft_id)
    if (!draft) {
      ElMessage.error('找不到当前客户的待确认草稿，请稍后重试')
      return
    }
    appendCard({
      id: cardId,
      type: 'batch_draft',
      status: 'waiting_confirmation',
      resource_refs: {
        task_id: taskId,
        item_id: item.id,
        draft_id: draft.id,
        customer_id: item.customer_id,
        customer_name: item.customer_name || item.customer_name_hint,
      },
      summary: draft.ai_result as unknown as Record<string, unknown>,
      allowed_actions: ['edit', 'confirm', 'retry', 'cancel'],
    })
    if (item.customer_id) {
      selectedCustomerId.value = item.customer_id
      currentCustomerName.value = item.customer_name || item.customer_name_hint
    }
  } catch {
    ElMessage.error('加载当前客户草稿失败，请稍后重试')
  }
}

/** 批量补记：开始/继续当前子项，搜索客户候选并展示客户选择卡片。 */
async function startBatchItem(_card: AssistantCard, taskId: number, item: BatchItem): Promise<void> {
  if (!taskId || !item.id) return
  try {
    const state = await apiGetBatchState(taskId)
    // 前端不允许越过当前子项；后端也会再次校验顺序。
    if (state.current_item_id !== item.id) {
      ElMessage.info('请先完成当前客户的记录，再处理后续客户')
      return
    }
    const latestItem = state.items.find((candidate) => candidate.id === item.id) || item
    if (latestItem.status === 'waiting_draft') {
      await restoreBatchDraftCard(taskId, latestItem)
      return
    }
    const selectionCardId = `batch_customer_selection:${taskId}:${item.id}`
    if (hasCard(selectionCardId)) return
    const { candidates } = await apiSearchBatchItemCustomer(taskId, item.id)
    appendCard({
      id: selectionCardId,
      type: 'customer_selection',
      status: 'waiting_user',
      resource_refs: {
        task_id: taskId,
        item_id: item.id,
        customer_name_hint: latestItem.customer_name_hint,
        sequence: latestItem.sequence,
        total_items: state.total_items,
      },
      customer_candidates: candidates,
      allowed_actions: ['select_customer', 'cancel'],
    })
  } catch {
    ElMessage.error('客户查询失败，请稍后重试')
  }
}

/** 批量补记：确认子项客户，展示训练草稿卡片。 */
async function selectBatchCustomer(card: AssistantCard, candidate: AssistantCustomerMatch): Promise<void> {
  const taskId = card.resource_refs?.task_id
  const itemId = card.resource_refs?.item_id
  if (typeof taskId !== 'number' || typeof itemId !== 'number') return
  try {
    const result = await apiSelectBatchItemCustomer(taskId, itemId, candidate.id)
    selectedCustomerId.value = result.customer_id
    currentCustomerName.value = result.customer_name || candidate.name
    // 客户确认卡变为只读状态，再在其后追加当前客户的草稿卡。
    card.status = 'completed'
    card.allowed_actions = []
    appendCard({
      id: `batch_draft:${taskId}:${itemId}`,
      type: 'batch_draft',
      status: 'waiting_confirmation',
      resource_refs: {
        task_id: taskId,
        item_id: itemId,
        draft_id: result.draft_id,
        customer_id: result.customer_id,
        customer_name: result.customer_name,
      },
      summary: (result.ai_result ?? {}) as Record<string, unknown>,
      allowed_actions: ['edit', 'confirm', 'retry', 'cancel'],
    })
    scrollToBottom()
  } catch {
    ElMessage.error('确认客户失败，请稍后重试')
  }
}

/** 批量补记：当前子项保存后自动进入下一项，只有全部终态才展示汇总。 */
async function handleBatchAdvance(card: AssistantCard, summary: BatchSummary): Promise<void> {
  card.status = 'completed'
  card.allowed_actions = []
  await advanceBatch(summary.task_id)
}

/** 批量补记：跳过当前子项后自动进入下一项，只有全部终态才展示汇总。 */
async function handleBatchSkip(card: AssistantCard, summary: BatchSummary): Promise<void> {
  card.status = 'cancelled'
  card.allowed_actions = []
  await advanceBatch(summary.task_id)
}

/** 推进批量任务：刷新服务端状态，自动搜索下一项或展示最终汇总。 */
async function advanceBatch(taskId: number): Promise<void> {
  try {
    const state = await apiGetBatchState(taskId)
    appendBatchOverview(state)
    if (state.current_item_id != null) {
      const current = state.items.find((item) => item.id === state.current_item_id)
      if (current) {
        items.value.push({
          kind: 'message',
          message: { role: 'assistant', content: `当前客户已处理，接下来处理第 ${current.sequence} 项：${current.customer_name || current.customer_name_hint}。` },
        })
        await startBatchItem({} as AssistantCard, taskId, current)
      }
      scrollToBottom()
      return
    }
    // current_item_id 为空说明所有子项均已进入终态（成功、跳过、失败或取消）。
    await showBatchSummary(batchSummaryFromState(state))
  } catch {
    ElMessage.error('读取批量任务进度失败，请稍后重试')
  }
}

/** 展示最终批量汇总卡片；相同任务只展示一次。 */
async function showBatchSummary(summary: BatchSummary): Promise<void> {
  appendCard({
    id: `batch_summary:${summary.task_id}`,
    type: 'batch_summary',
    status: 'completed',
    resource_refs: { task_id: summary.task_id },
    batch_summary: summary,
    allowed_actions: [],
  })
  scrollToBottom()
}

/** 批量补记：取消全部。 */
async function cancelBatch(_card: AssistantCard, taskId: number): Promise<void> {
  await apiCancelAssistantTask(taskId)
  ElMessage.info('批量任务已取消')
}

/** 恢复批量任务当前子项，并在聊天流中补齐对应的客户确认/草稿卡。 */
async function restoreBatchTask(
  taskId: number,
  options: { appendOverview?: boolean; announceProgress?: boolean } = {},
): Promise<void> {
  const { appendOverview = true, announceProgress = true } = options
  try {
    const state = await apiGetBatchState(taskId)
    if (appendOverview) appendBatchOverview(state)

    if (state.current_item_id == null) {
      await showBatchSummary(batchSummaryFromState(state))
      return
    }

    const current = state.items.find((item) => item.id === state.current_item_id)
    if (!current) return

    if (announceProgress) {
      items.value.push({
        kind: 'message',
        message: { role: 'assistant', content: `继续处理第 ${current.sequence} 项：${current.customer_name || current.customer_name_hint}。` },
      })
    }
    await startBatchItem({} as AssistantCard, taskId, current)
    scrollToBottom()
  } catch {
    ElMessage.error('恢复批量任务失败，请稍后重试')
  }
}

/** 加载任务详情并恢复：编排聊天任务通过 /resume/ 推进，恢复卡片到原位置。 */
async function resumeTask(task: AssistantTask, updateAddress = true): Promise<void> {
  let latest = task
  try {
    latest = await apiGetAssistantTask(task.id)
  } catch {
    // 列表数据已经足够渲染恢复入口，详情接口不可用时继续使用列表快照。
  }
  activeTask.value = latest
  selectedCustomerId.value = latest.customer || selectedCustomerId.value
  currentCustomerName.value = latest.customer_name || currentCustomerName.value
  if (latest.context_resource_type === 'course_session') {
    courseSessionId.value = readNumber(latest.context_resource_id)
  }
  if (updateAddress) {
    await router.replace({ name: 'assistant', query: queryForAssistant({ taskId: String(latest.id) }) })
  }
  if (latest.task_type === 'multi_customer_training_record') {
    await restoreBatchTask(latest.id)
  } else if (latest.task_type === 'assistant_turn') {
    try {
      const result = await apiResumeAssistantTurn(latest.id)
      await applyTurnResult(result)
    } catch {
      // 恢复失败保持现状，康复师可稍后重试。
    }
  }
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
    tasks.value = []
  } finally {
    loadingTasks.value = false
  }
}

/** 放弃任务需要二次确认，取消不会删除任何正式业务记录。 */
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
  ElMessage.info('任务已放弃')
}

function conversationScope(): { origin: ConversationOrigin; conversation_type: ConversationType } {
  if (selectedCustomerId.value) return { origin: 'customer_detail', conversation_type: 'customer_discussion' }
  return { origin: 'general', conversation_type: 'general' }
}

function greeting(): string {
  return selectedCustomerId.value
    ? '你好，这里可以围绕当前客户讨论训练、恢复进展和记录内容。'
    : '你好，我可以协助你整理训练记录、填写评估、安排随访，也可以回答康复训练相关问题。'
}

function resetConversationGreeting(): void {
  items.value = [{ kind: 'message', message: { role: 'assistant', content: greeting() } }]
  conversationId.value = null
  chatInput.value = ''
}

function mapConversationMessage(message: AiConversationMessage): ChatMessage | null {
  if (message.role !== 'assistant' && message.role !== 'user') return null
  const rawSources = message.metadata?.sources
  const sources = Array.isArray(rawSources) ? rawSources.filter((item): item is string => typeof item === 'string') : undefined
  return { role: message.role, content: message.content, sources }
}

async function loadConversation(): Promise<void> {
  if (!conversationId.value) {
    resetConversationGreeting()
    return
  }
  loadingConversation.value = true
  try {
    const conversation = await apiGetConversation(conversationId.value)
    const history = conversation.messages.map(mapConversationMessage).filter((item): item is ChatMessage => item !== null)
    items.value = history.length ? history.map((message) => ({ kind: 'message', message })) : [{ kind: 'message', message: { role: 'assistant', content: greeting() } }]
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

function goBack(): void {
  if (window.history.length > 1) router.back()
  else router.push({ name: 'dashboard' })
}

onMounted(async () => {
  await loadCustomer()
  await loadTasks()
  if (!activeTask.value) await loadConversation()
})
</script>

<template>
  <div class="assistant-page retrue-page">
    <header class="assistant-page-header">
      <div class="assistant-title-wrap">
        <span class="assistant-title-mark" aria-hidden="true"><el-icon><ChatDotRound /></el-icon></span>
        <div>
          <h1>智能助理</h1>
          <p>在同一个聊天里完成咨询、补记、评估、随访与确认。</p>
        </div>
      </div>
      <div class="assistant-header-actions">
        <el-button text aria-label="返回" @click="goBack"><el-icon><Close /></el-icon></el-button>
      </div>
    </header>

    <section v-if="loadingTasks" class="assistant-task-section">
      <el-skeleton :rows="2" animated />
    </section>
    <section v-else-if="tasks.length" class="assistant-task-section" aria-labelledby="unfinished-heading">
      <div class="section-heading">
        <div>
          <h2 id="unfinished-heading">未完成的工作</h2>
          <p>可以继续处理，也可以先放到稍后。</p>
        </div>
        <el-tag type="warning" effect="plain">{{ tasks.length }} 项</el-tag>
      </div>
      <div class="task-list">
        <el-card v-for="task in tasks" :key="task.id" shadow="never" class="task-card retrue-card">
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
          <div class="task-card-footer">
            <span>{{ formatTaskTime(taskUpdatedAt(task)) }}</span>
            <div class="task-actions">
              <el-button link type="primary" @click="resumeTask(task)">继续</el-button>
              <el-button link type="danger" @click="abandonTask(task)">放弃</el-button>
            </div>
          </div>
        </el-card>
      </div>
    </section>

    <section class="assistant-workspace">
      <el-card class="chat-workspace retrue-card" shadow="never">
        <template #header>
          <div class="workspace-heading">
            <div>
              <strong>{{ selectedCustomerId ? `与${currentCustomerLabel}讨论` : 'AI 助理工作台' }}</strong>
              <span>内容会保存在本次会话中，方便后续查看。</span>
            </div>
            <el-tag type="info" effect="plain">仅供专业辅助</el-tag>
          </div>
        </template>
        <main ref="messageList" class="message-list" aria-live="polite">
          <el-skeleton v-if="loadingConversation" :rows="3" animated />
          <template v-else>
            <template v-for="(item, index) in items" :key="`${index}-${item.kind}`">
              <div v-if="item.kind === 'message'" class="message-row" :class="item.message.role">
                <div class="message-bubble">{{ item.message.content }}</div>
                <small v-if="item.message.sources?.length">参考动作：{{ item.message.sources.join('、') }}</small>
              </div>
              <div v-else class="card-row">
                <AssistantCardRenderer
                  :card="item.card"
                  :customer-id="selectedCustomerId"
                  :course-session-id="courseSessionId"
                  @select-customer="selectCustomer"
                  @card-action="handleCardAction"
                  @confirmed="handleConfirmed"
                  @cancelled="() => {}"
                  @batch-start="startBatchItem"
                  @batch-cancel="cancelBatch"
                  @batch-advance="handleBatchAdvance"
                  @batch-skip="handleBatchSkip"
                />
              </div>
            </template>
            <div v-if="sending" class="message-row assistant"><div class="message-bubble">正在整理回复…</div></div>
          </template>
        </main>
        <footer class="chat-input-area">
          <div class="assistant-input-context" aria-label="当前工作上下文">
            <span class="context-inline-chip customer"><b>客户</b>{{ currentCustomerLabel }}</span>
          </div>
          <el-input
            v-model="chatInput"
            type="textarea"
            :autosize="{ minRows: 2, maxRows: 5 }"
            maxlength="5000"
            show-word-limit
            placeholder="例如：臀桥怎么做？或 补记张三今天的训练，或 给张三做评估。"
            @keydown.enter.exact.prevent="sendChat"
          />
          <div class="chat-input-footer">
            <span>Enter 发送，Shift + Enter 换行</span>
            <el-button type="primary" :loading="sending" :disabled="!chatInput.trim()" @click="sendChat">发送</el-button>
          </div>
        </footer>
      </el-card>
    </section>
  </div>
</template>

<style scoped>
.assistant-page { display: flex; min-height: calc(100vh - 48px); flex-direction: column; gap: 18px; padding-bottom: 28px; }
.assistant-page-header { display: flex; align-items: center; justify-content: space-between; gap: 18px; }
.assistant-title-wrap, .assistant-header-actions, .workspace-heading, .task-card-heading, .task-card-footer, .task-actions, .chat-input-footer { display: flex; align-items: center; }
.assistant-title-wrap { gap: 12px; }
.assistant-title-mark { display: grid; width: 40px; height: 40px; place-items: center; border-radius: var(--retrue-radius-md); background: var(--retrue-ai-light); color: var(--retrue-ai); font-size: 20px; }
.assistant-page h1 { margin: 0; color: var(--retrue-text); font-size: 24px; }
.assistant-page-header p, .section-heading p, .workspace-heading span { margin: 4px 0 0; color: var(--retrue-text-secondary); font-size: 13px; }
.assistant-header-actions { gap: 16px; }
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
.card-row { max-width: min(860px, 100%); align-self: flex-start; width: min(860px, 100%); padding: 12px 14px; border: 1px solid var(--retrue-border); border-radius: var(--retrue-radius-md); background: var(--retrue-surface); }
.chat-input-area { padding-top: 12px; border-top: 1px solid var(--retrue-border); }
.assistant-input-context { display: flex; flex-wrap: wrap; gap: 6px; margin: 0 0 8px; font-size: 13px; line-height: 1.45; }
.context-inline-chip { display: inline-flex; min-width: 0; align-items: center; gap: 5px; max-width: 100%; padding: 3px 8px; border-radius: 6px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.context-inline-chip b { color: var(--retrue-text-muted); font-size: 12px; font-weight: 500; }
.context-inline-chip.customer { background: color-mix(in srgb, var(--retrue-primary) 10%, transparent); color: var(--retrue-primary); }
.chat-input-footer { justify-content: space-between; gap: 12px; margin-top: 8px; }
.chat-input-footer span { color: var(--retrue-text-muted); font-size: 12px; }

@media (max-width: 768px) {
  .assistant-page { min-height: calc(100dvh - 104px); gap: 12px; padding-bottom: 12px; }
  .assistant-page-header, .workspace-heading, .task-card-footer { align-items: stretch; flex-direction: column; }
  .assistant-page-header { gap: 10px; }
  .assistant-header-actions { justify-content: flex-end; }
  .assistant-page h1 { font-size: 21px; }
  .task-list { grid-template-columns: minmax(0, 1fr); }
  .task-actions { justify-content: flex-start; }
  .chat-workspace { min-height: 0; }
  .message-list { min-height: 260px; padding: 14px 0; }
  .message-row { max-width: 94%; }
  .card-row { max-width: 94%; width: 94%; }
  .chat-input-footer { align-items: stretch; flex-direction: column; }
  .chat-input-footer :deep(.el-button) { width: 100%; margin-left: 0; }
}
</style>
