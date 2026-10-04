<script setup lang="ts">
/** 两端共用的真实待办：未回填排课、今日/逾期回访、待确认草稿。 */
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { apiGetPendingCourseRecords } from '@/api/courses'
import { apiListFollowUps } from '@/api/followups'
import { apiListAssistantTasks } from '@/api/assistant'
import { apiListDrafts } from '@/api/ai'
import { pendingDraftEntries, type PendingDraftEntry } from '@/utils/pendingDrafts'
import type { CourseSessionItem, FollowUpTask } from '@/types/api'

const props = defineProps<{ mobile?: boolean }>()
const router = useRouter()
const loading = ref(false)
const failed = ref(false)
const pending = ref<CourseSessionItem[]>([])
const pendingTotal = ref(0)
const followups = ref<FollowUpTask[]>([])
const drafts = ref<PendingDraftEntry[]>([])
const expanded = ref(false)
let page = 0
let generation = 0
const today = (() => { const date = new Date(); return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}` })()
const limit = computed(() => expanded.value ? Number.POSITIVE_INFINITY : props.mobile ? 5 : 20)
const visiblePending = computed(() => pending.value.slice(0, limit.value))
const visibleFollowups = computed(() => followups.value.slice(0, limit.value))
const visibleDrafts = computed(() => drafts.value.slice(0, limit.value))
const hiddenLoaded = computed(() => pending.value.length > limit.value || followups.value.length > limit.value || drafts.value.length > limit.value)

/** 独立失败不会被显示成“没有待办”；重试重新读取服务端状态。 */
async function load(): Promise<void> {
  const current = ++generation
  loading.value = true; failed.value = false
  try {
    const [records, visits, tasks, oldDrafts] = await Promise.all([
      apiGetPendingCourseRecords(), apiListFollowUps({ status: 'pending' }), apiListAssistantTasks({ status: 'waiting_confirmation' }), apiListDrafts(),
    ])
    if (current !== generation) return
    pending.value = records.items; pendingTotal.value = records.total; page = 1
    followups.value = visits.filter((item) => item.status === 'pending' && item.due_date <= today).sort((a, b) => a.due_date.localeCompare(b.due_date) || a.id - b.id)
    drafts.value = pendingDraftEntries(tasks, oldDrafts)
  } catch { if (current === generation) failed.value = true }
  finally { if (current === generation) loading.value = false }
}
async function loadMore(): Promise<void> {
  if (loading.value) return
  const current = generation
  loading.value = true
  try {
    const records = await apiGetPendingCourseRecords(page + 1)
    if (current !== generation) return
    const ids = new Set(pending.value.map((item) => item.id))
    pending.value.push(...records.items.filter((item) => !ids.has(item.id)))
    pendingTotal.value = records.total; page += 1; expanded.value = true
  } catch { /* 已有结果保留，错误由 API 层提示，可再次加载。 */ }
  finally { if (current === generation) loading.value = false }
}
function openCourse(course: CourseSessionItem): void {
  if (['initial_assessment', 'reassessment'].includes(course.arrangement_type || '')) {
    router.push({ name: 'assessment-edit', query: { customerId: course.customer, mode: course.arrangement_type === 'reassessment' ? 'reassessment' : 'initial' } })
  } else router.push({ name: 'assistant', query: { mode: 'training', theme: 'guided', entryAction: 'fill_course_training_record', customerId: course.customer, courseSessionId: course.id } })
}
function courseLabel(course: CourseSessionItem): string {
  return course.arrangement_type === 'reassessment' ? '已安排待复评' : course.arrangement_type === 'initial_assessment' ? '已安排待首评' : '待回填训练'
}
function openFollowup(task: FollowUpTask): void { router.push({ name: 'customer-detail', params: { id: task.customer }, query: { focus: 'followup', followupId: task.id } }) }
function openDraft(item: PendingDraftEntry): void {
  if (item.taskId) router.push({ name: 'assistant', query: { taskId: item.taskId } })
  else if (item.draftId) router.push({ name: 'assistant', query: { draftId: item.draftId } })
  else if (item.assessmentId) router.push({ name: 'assessment-revise', params: { id: item.assessmentId } })
  else router.push({ name: 'assessment-edit', query: { customerId: item.customerId, mode: item.assessmentType } })
}
onMounted(load)
onBeforeUnmount(() => { generation += 1 })
</script>

<template>
  <el-card v-loading="loading" class="workdesk-card" shadow="never">
    <template #header><div class="task-header"><strong>待处理事项</strong><el-button link type="primary" :disabled="loading" @click="load">刷新</el-button></div></template>
    <el-alert v-if="failed" title="待办加载失败，请重试。" type="error" :closable="false"><el-button link @click="load">重试</el-button></el-alert>
    <template v-else>
      <el-empty v-if="!loading && !pendingTotal && !followups.length && !drafts.length" description="当前没有待处理事项" :image-size="60" />
      <section v-if="pendingTotal"><h4>今日与跨日未回填安排（{{ pendingTotal }}）</h4>
        <div v-for="item in visiblePending" :key="item.id" class="task-row">
          <div><strong>{{ item.customer_name }}</strong><p>{{ item.date }} {{ item.start_time?.slice(0, 5) }} · {{ courseLabel(item) }}<span v-if="item.date < today"> · 逾期</span></p></div>
          <el-button size="small" type="primary" @click="openCourse(item)">{{ item.arrangement_type === 'reassessment' ? '进入复评' : item.arrangement_type === 'initial_assessment' ? '进入首评' : '回填训练' }}</el-button>
        </div>
        <el-button v-if="pending.length < pendingTotal" link type="primary" :disabled="loading" @click="loadMore">还有 {{ pendingTotal - pending.length }} 项，加载更多</el-button>
      </section>
      <section v-if="followups.length"><h4>今日与逾期回访 / 复查（{{ followups.length }}）</h4>
        <div v-for="item in visibleFollowups" :key="item.id" class="task-row"><div><strong>{{ item.customer_name }}</strong><p>{{ item.due_date }} · {{ item.followup_type_display }}{{ item.due_date < today ? ' · 逾期' : '' }}</p><p v-if="item.content">{{ item.content }}</p></div><el-button size="small" @click="openFollowup(item)">记录结果</el-button></div>
      </section>
      <section v-if="drafts.length"><h4>待确认草稿与评估描述（{{ drafts.length }}）</h4>
        <div v-for="item in visibleDrafts" :key="item.key" class="task-row"><div><strong>{{ item.customerName }}</strong><p>{{ item.label }}</p></div><el-button size="small" @click="openDraft(item)">继续复核</el-button></div>
      </section>
      <el-button v-if="hiddenLoaded" link type="primary" @click="expanded = true">展开全部已加载事项</el-button>
    </template>
  </el-card>
</template>

<style scoped>
.workdesk-card { margin-top: 16px; border-color: var(--retrue-border); border-radius: var(--retrue-radius-lg); }
.task-header, .task-row { display: flex; justify-content: space-between; align-items: center; gap: 12px; }
.task-row { padding: 10px 0; border-bottom: 1px solid var(--retrue-border); }
.task-row > div { min-width: 0; overflow-wrap: anywhere; }
.task-row p { margin: 4px 0 0; font-size: 13px; color: var(--retrue-text-secondary); }
h4 { margin: 16px 0 4px; font-size: 14px; }
.task-row .el-button { flex-shrink: 0; }
@media (max-width: 767px) { .task-row { flex-wrap: wrap; } }
</style>
