<script setup lang="ts">
/**
 * 课程计划批量安排向导。
 *
 * 这个组件只呈现康复师需要做的选择：从哪天开始、每周几次、哪几天和几点开始。
 * 预览与确认分别调用服务端接口，确认前不会占用课表名额。
 */

import { computed, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'

import {
  apiConfirmCourseSchedule,
  apiPreviewCourseSchedule,
  type CourseScheduleBatchPayload,
} from '@/api/courses'
import { apiListCustomers } from '@/api/customers'
import { apiListRehabPlanCourses } from '@/api/rehab'
import type {
  CourseScheduleConflict,
  CourseSchedulePreview,
  CourseSchedulePreviewItem,
  CustomerListItem,
  RehabPlanCourse,
} from '@/types/api'

const props = withDefaults(
  defineProps<{
    modelValue: boolean
    initialCustomerId?: number
    initialPlanCourseId?: number
    title?: string
  }>(),
  { title: '安排课程' },
)

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  confirmed: []
}>()

const customers = ref<CustomerListItem[]>([])
const planCourses = ref<RehabPlanCourse[]>([])
const loadingOptions = ref(false)
const previewing = ref(false)
const confirming = ref(false)
const step = ref<'form' | 'preview'>('form')
const preview = ref<CourseSchedulePreview | null>(null)

const form = reactive({
  customer: undefined as number | undefined,
  plan_course: undefined as number | undefined,
  start_date: new Date().toISOString().slice(0, 10),
  weekly_count: 2,
  weekdays: [1, 3] as number[],
  start_time: '18:00:00',
})

const weekdays = [
  { value: 1, label: '周一' },
  { value: 2, label: '周二' },
  { value: 3, label: '周三' },
  { value: 4, label: '周四' },
  { value: 5, label: '周五' },
  { value: 6, label: '周六' },
  { value: 0, label: '周日' },
]

const activePlanCourses = computed(() =>
  planCourses.value.filter((item) => {
    const statusAvailable = item.rehab_plan_status === 'active' && item.status === 'active'
    const remaining = item.unscheduled_count ?? item.remaining_count
    return statusAvailable && remaining > 0
  }),
)

const selectedPlanCourse = computed(() =>
  planCourses.value.find((item) => item.id === form.plan_course),
)

const scheduledItems = computed<CourseSchedulePreviewItem[]>(() => {
  if (!preview.value) return []
  // 后端以 items 返回；兼容少量实现使用 sessions 的情况，避免预览空白。
  const value = preview.value as CourseSchedulePreview & {
    sessions?: CourseSchedulePreviewItem[]
  }
  return value.items ?? value.sessions ?? []
})

const conflicts = computed(() => preview.value?.conflicts ?? [])

function resetForm(): void {
  form.customer = props.initialCustomerId
  form.plan_course = props.initialPlanCourseId
  form.start_date = new Date().toISOString().slice(0, 10)
  form.weekly_count = 2
  form.weekdays = [1, 3]
  form.start_time = '18:00:00'
  step.value = 'form'
  preview.value = null
}

async function loadOptions(): Promise<void> {
  loadingOptions.value = true
  try {
    const customerResult = await apiListCustomers({ status: 'active', page: 1, page_size: 100 })
    customers.value = customerResult.items
    if (!form.customer && props.initialCustomerId) form.customer = props.initialCustomerId
    await loadPlanCourses(form.customer)
    if (form.plan_course && !planCourses.value.some((item) => item.id === form.plan_course)) {
      form.plan_course = undefined
    }
  } finally {
    loadingOptions.value = false
  }
}

async function loadPlanCourses(customerId: number | undefined): Promise<void> {
  if (!customerId) {
    planCourses.value = []
    form.plan_course = undefined
    return
  }
  planCourses.value = await apiListRehabPlanCourses({ customer_id: customerId })
  const initialCourse = props.initialPlanCourseId
  if (initialCourse && planCourses.value.some((item) => item.id === initialCourse)) {
    form.plan_course = initialCourse
    return
  }
  if (!form.plan_course || !planCourses.value.some((item) => item.id === form.plan_course)) {
    // 新建计划通常只有一门课程，直接帮康复师选上；多门课程保留选择权。
    form.plan_course = activePlanCourses.value.length === 1 ? activePlanCourses.value[0]?.id : undefined
  }
}

async function handleCustomerChange(): Promise<void> {
  form.plan_course = undefined
  await loadPlanCourses(form.customer)
}

function handleWeeklyCountChange(): void {
  if (form.weekly_count < 1) form.weekly_count = 1
  if (form.weekdays.length > form.weekly_count) {
    form.weekdays = form.weekdays.slice(0, form.weekly_count)
  }
}

function formatTime(value: string | null): string {
  return value ? value.slice(0, 5) : '待定'
}

function formatPreviewDate(value: string): string {
  if (!value) return ''
  const [, month, day] = value.split('-')
  return month && day ? `${Number(month)}月${Number(day)}日` : value
}

function conflictText(item: CourseScheduleConflict | string): string {
  if (typeof item === 'string') return item
  return item.message || `${formatPreviewDate(item.date)} ${formatTime(item.start_time)} 已有其他客户课程，请调整时间`
}

function payload(): CourseScheduleBatchPayload | null {
  if (!form.customer || !form.plan_course) {
    ElMessage.warning('请选择客户和要安排的课程')
    return null
  }
  if (!form.start_date || !form.start_time) {
    ElMessage.warning('请选择开始日期和时间')
    return null
  }
  if (form.weekdays.length !== form.weekly_count) {
    ElMessage.warning(`请选择 ${form.weekly_count} 个上课日`)
    return null
  }
  const course = selectedPlanCourse.value
  const remaining = course ? course.unscheduled_count ?? course.remaining_count : 0
  if (remaining <= 0) {
    ElMessage.warning('该课程已全部安排，无需重复安排')
    return null
  }
  return {
    customer: form.customer,
    plan_course: form.plan_course,
    start_date: form.start_date,
    weekly_count: form.weekly_count,
    weekdays: [...form.weekdays],
    start_time: form.start_time,
  }
}

async function previewSchedule(): Promise<void> {
  const data = payload()
  if (!data) return
  previewing.value = true
  try {
    preview.value = await apiPreviewCourseSchedule(data)
    step.value = 'preview'
  } finally {
    previewing.value = false
  }
}

async function confirmSchedule(): Promise<void> {
  const data = payload()
  if (!data) return
  if (conflicts.value.length > 0) {
    ElMessage.warning('请先调整有冲突的时间，再确认加入课表')
    return
  }
  confirming.value = true
  try {
    const result = await apiConfirmCourseSchedule(data)
    const count = result.created_count ?? result.items?.length ?? result.sessions?.length ?? scheduledItems.value.length
    ElMessage.success(`已安排 ${count} 节课程`)
    emit('confirmed')
    emit('update:modelValue', false)
  } finally {
    confirming.value = false
  }
}

function goBack(): void {
  step.value = 'form'
}

function close(): void {
  emit('update:modelValue', false)
}

watch(
  () => props.modelValue,
  async (visible) => {
    if (!visible) return
    resetForm()
    await loadOptions()
  },
)

watch(
  () => props.initialPlanCourseId,
  (value) => {
    if (props.modelValue && value) form.plan_course = value
  },
)
</script>

<template>
  <el-dialog
    :model-value="modelValue"
    :title="step === 'form' ? title : '确认课程安排'"
    width="min(600px, calc(100vw - 24px))"
    destroy-on-close
    class="schedule-wizard-dialog"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <el-skeleton v-if="loadingOptions" :rows="5" animated />
    <template v-else-if="step === 'form'">
      <p class="wizard-intro">设置好固定的上课时间后，系统会先给出安排预览，确认后才会加入课表。</p>
      <el-form :model="form" label-position="top" class="wizard-form">
        <el-form-item label="客户" required>
          <el-select
            v-model="form.customer"
            filterable
            placeholder="搜索并选择客户"
            class="full-width"
            @change="handleCustomerChange"
          >
            <el-option v-for="customer in customers" :key="customer.id" :label="customer.name" :value="customer.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="安排哪门课程" required>
          <el-select v-model="form.plan_course" placeholder="选择进行中的计划课程" class="full-width">
            <el-option
              v-for="course in activePlanCourses"
              :key="course.id"
              :label="`${course.rehab_plan_name} · ${course.course_type_name}（待安排 ${course.unscheduled_count ?? course.remaining_count} 次）`"
              :value="course.id"
            />
          </el-select>
          <div v-if="form.customer && activePlanCourses.length === 0" class="field-hint warning-hint">
            该客户暂时没有可以安排的进行中课程，请先回到客户详情补充课程计划。
          </div>
        </el-form-item>
        <div class="wizard-grid">
          <el-form-item label="从哪天开始" required>
            <el-date-picker v-model="form.start_date" type="date" value-format="YYYY-MM-DD" class="full-width" />
          </el-form-item>
          <el-form-item label="每周上几次" required>
            <el-input-number v-model="form.weekly_count" :min="1" :max="7" class="full-width" @change="handleWeeklyCountChange" />
          </el-form-item>
        </div>
        <el-form-item label="通常星期几" required>
          <el-checkbox-group v-model="form.weekdays" class="weekday-group">
            <el-checkbox v-for="day in weekdays" :key="day.value" :value="day.value">{{ day.label }}</el-checkbox>
          </el-checkbox-group>
          <div class="field-hint">请选择与每周次数相同的日期。</div>
        </el-form-item>
        <el-form-item label="通常几点开始" required>
          <el-time-picker v-model="form.start_time" value-format="HH:mm:ss" format="HH:mm" class="full-width" />
          <div v-if="selectedPlanCourse?.duration" class="field-hint">
            每节约 {{ selectedPlanCourse.duration }} 分钟，系统会自动计算结束时间。
          </div>
        </el-form-item>
      </el-form>
    </template>
    <template v-else>
      <div class="preview-summary">
        <strong>{{ selectedPlanCourse?.course_type_name || '课程' }}</strong>
        <span>共 {{ scheduledItems.length }} 节</span>
      </div>
      <el-alert
        v-if="conflicts.length"
        title="以下时间与已有课程冲突，请返回调整"
        type="warning"
        :closable="false"
        show-icon
        class="preview-alert"
      >
        <div v-for="(item, index) in conflicts" :key="index">{{ conflictText(item) }}</div>
      </el-alert>
      <el-empty v-if="scheduledItems.length === 0" description="暂时没有可安排的课程，请调整开始日期或时间" :image-size="70" />
      <div v-else class="preview-list">
        <div v-for="(item, index) in scheduledItems" :key="`${item.date}-${index}`" class="preview-item">
          <span>{{ formatPreviewDate(item.date) }}</span>
          <strong>{{ formatTime(item.start_time) }} - {{ formatTime(item.end_time) }}</strong>
          <em>{{ item.session_topic || selectedPlanCourse?.course_type_name }}</em>
        </div>
      </div>
      <p class="preview-note">确认后，这些课程会加入课表；之后仍可在课表中单独调整。</p>
    </template>
    <template #footer>
      <el-button @click="close">取消</el-button>
      <template v-if="step === 'form'">
        <el-button type="primary" :loading="previewing" @click="previewSchedule">查看安排预览</el-button>
      </template>
      <template v-else>
        <el-button @click="goBack">返回调整</el-button>
        <el-button type="primary" :loading="confirming" :disabled="!scheduledItems.length || conflicts.length > 0" @click="confirmSchedule">
          确认加入课表
        </el-button>
      </template>
    </template>
  </el-dialog>
</template>

<style scoped>
.wizard-intro,
.preview-note,
.field-hint {
  color: var(--retrue-text-secondary);
  font-size: 13px;
}

.wizard-intro {
  margin: 0 0 18px;
  line-height: 1.6;
}

.wizard-form :deep(.el-form-item) {
  margin-bottom: 16px;
}

.wizard-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  gap: 0 16px;
}

.full-width {
  width: 100%;
}

.weekday-group {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 12px;
}

.field-hint {
  margin-top: 4px;
  line-height: 1.5;
}

.warning-hint {
  color: var(--el-color-warning);
}

.preview-summary {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 14px;
  font-size: 15px;
}

.preview-summary span {
  color: var(--retrue-primary);
  font-size: 13px;
}

.preview-alert {
  margin-bottom: 14px;
}

.preview-alert div + div {
  margin-top: 4px;
}

.preview-list {
  display: flex;
  max-height: 330px;
  flex-direction: column;
  gap: 8px;
  overflow-y: auto;
}

.preview-item {
  display: grid;
  grid-template-columns: 76px 145px minmax(0, 1fr);
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  border: 1px solid var(--retrue-border);
  border-radius: var(--retrue-radius-sm);
  background: var(--retrue-bg);
}

.preview-item span {
  color: var(--retrue-text-secondary);
}

.preview-item strong {
  color: var(--retrue-primary-dark);
}

.preview-item em {
  overflow: hidden;
  color: var(--retrue-text-secondary);
  font-style: normal;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.preview-note {
  margin: 14px 0 0;
  line-height: 1.5;
}

@media (max-width: 600px) {
  .wizard-grid {
    grid-template-columns: 1fr;
    gap: 0;
  }

  .wizard-form :deep(.el-date-editor.full-width) {
    width: 100%;
  }

  .preview-item {
    grid-template-columns: 68px minmax(0, 1fr);
  }

  .preview-item em {
    grid-column: 2;
  }
}
</style>
