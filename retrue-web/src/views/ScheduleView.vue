<script setup lang="ts">
/** 课程管理页：月历展示课程，排课可关联客户课程计划中的具体课程。 */
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, type FormInstance } from 'element-plus'
import { apiCreateCourse, apiGetCalendarCourses, apiUpdateCourse } from '@/api/courses'
import { apiListCustomers } from '@/api/customers'
import { apiListRehabPlanCourses } from '@/api/rehab'
import type { CourseSessionItem, CustomerListItem, RehabPlanCourse } from '@/types/api'

type CourseForm = {
  customer: number | undefined
  plan_course: number | null
  session_topic: string
  session_count: number
  date: string
  start_time: string
  end_time: string
  status: string
  note: string
}
const loading = ref(false)
const router = useRouter()
const selectedDate = ref(new Date())
const courses = ref<CourseSessionItem[]>([])
const customers = ref<CustomerListItem[]>([])
const planCourses = ref<RehabPlanCourse[]>([])
const dialogVisible = ref(false)
const dayDialogVisible = ref(false)
const selectedDay = ref('')
const saving = ref(false)
const editingCourse = ref<CourseSessionItem | null>(null)
const formRef = ref<FormInstance>()
const form = reactive<CourseForm>({
  customer: undefined,
  plan_course: null,
  session_topic: '康复训练',
  session_count: 1,
  date: '',
  start_time: '',
  end_time: '',
  status: 'scheduled',
  note: '',
})
const dialogTitle = computed(() => (editingCourse.value ? '管理课程' : '新增课程'))
const submitText = computed(() => (editingCourse.value ? '保存修改' : '添加课程'))
const coursesByDate = computed(() => {
  const result = new Map<string, CourseSessionItem[]>()
  for (const course of courses.value) result.set(course.date, [...(result.get(course.date) ?? []), course])
  return result
})
const selectedDayCourses = computed(() => coursesByDate.value.get(selectedDay.value) ?? [])
function formatDate(value: Date): string {
  return `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, '0')}-${String(value.getDate()).padStart(2, '0')}`
}
function formatTime(value: string | null): string { return value ? value.slice(0, 5) : '待定' }
function addMinutes(value: string, minutes: number): string {
  const [hour = 0, minute = 0] = value.split(':').map(Number)
  const total = Math.min(hour * 60 + minute + minutes, 23 * 60 + 59)
  return `${String(Math.floor(total / 60)).padStart(2, '0')}:${String(total % 60).padStart(2, '0')}:00`
}
function applyPlanCourseDuration(): void {
  if (!form.start_time || !form.plan_course) return
  const planCourse = planCourses.value.find((item) => item.id === form.plan_course)
  if (planCourse?.duration) form.end_time = addMinutes(form.start_time, planCourse.duration)
}
function handleStartTimeChange(): void { applyPlanCourseDuration() }
async function loadCalendar(): Promise<void> {
  const year = selectedDate.value.getFullYear()
  const month = selectedDate.value.getMonth()
  loading.value = true
  try {
    courses.value = await apiGetCalendarCourses(formatDate(new Date(year, month, 1)), formatDate(new Date(year, month + 1, 0)))
  } finally { loading.value = false }
}
async function loadCustomers(): Promise<void> {
  customers.value = (await apiListCustomers({ status: 'active', page: 1, page_size: 100 })).items
}
async function loadPlanCoursesForCustomer(customerId: number | undefined): Promise<void> {
  planCourses.value = customerId
    ? await apiListRehabPlanCourses({ customer_id: customerId })
    : []
}
function openCreate(date = formatDate(selectedDate.value)): void {
  editingCourse.value = null
  Object.assign(form, {
    customer: undefined,
    plan_course: null,
    session_topic: '康复训练',
    session_count: 1,
    date,
    start_time: '',
    end_time: '',
    status: 'scheduled',
    note: '',
  })
  planCourses.value = []
  dialogVisible.value = true
}
function openEdit(course: CourseSessionItem): void {
  editingCourse.value = course
  Object.assign(form, {
    customer: course.customer,
    plan_course: course.plan_course,
    session_topic: course.session_topic,
    session_count: course.session_count ?? 1,
    date: course.date,
    start_time: course.start_time || '',
    end_time: course.end_time || '',
    status: course.status,
    note: course.note,
  })
  loadPlanCoursesForCustomer(course.customer)
  dialogVisible.value = true
}
async function handleCustomerChange(): Promise<void> {
  form.plan_course = null
  await loadPlanCoursesForCustomer(form.customer)
}
function handlePlanCourseChange(planCourseId: number | null): void {
  if (!planCourseId) return
  const planCourse = planCourses.value.find((item) => item.id === planCourseId)
  if (!planCourse) return
  form.session_count = planCourse.session_cost
  form.session_topic = planCourse.course_type_name
  applyPlanCourseDuration()
}
async function handleSave(): Promise<void> {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return
  if (Boolean(form.start_time) !== Boolean(form.end_time)) {
    ElMessage.warning('请同时填写开始和结束时间')
    return
  }
  if (form.start_time && form.end_time <= form.start_time) {
    ElMessage.warning('结束时间需要晚于开始时间')
    return
  }
  const data = {
    customer: form.customer as number,
    plan_course: form.plan_course,
    session_topic: form.session_topic,
    session_count: form.session_count,
    date: form.date,
    start_time: form.start_time || null,
    end_time: form.end_time || null,
    status: form.status,
    note: form.note,
  }
  saving.value = true
  try {
    if (editingCourse.value) {
      await apiUpdateCourse(editingCourse.value.id, data)
      ElMessage.success('课程已更新')
    } else {
      await apiCreateCourse(data)
      ElMessage.success('课程已添加到课表')
    }
    dialogVisible.value = false
    await loadCalendar()
  } finally { saving.value = false }
}
function handlePanelChange(value: Date): void { selectedDate.value = value; loadCalendar() }
function openDay(date: string): void { selectedDay.value = date; dayDialogVisible.value = true }
function openCreateForDay(): void { dayDialogVisible.value = false; openCreate(selectedDay.value) }
function goTrainingRecord(useAi = false): void {
  const course = editingCourse.value
  if (!course) return
  dialogVisible.value = false
  if (course.training_record_id) {
    router.push({ name: 'training-revise', params: { id: course.training_record_id } })
    return
  }
  router.push({
    name: useAi ? 'ai-draft' : 'training-edit',
    query: { customerId: course.customer, courseSessionId: course.id },
  })
}
onMounted(async () => { await Promise.all([loadCalendar(), loadCustomers()]) })
</script>

<template>
  <div class="schedule-page">
    <div class="page-toolbar">
      <div><h3>课程管理</h3><p>按月查看、添加和管理客户课程。</p></div>
      <el-button type="primary" @click="openCreate()">新增课程</el-button>
    </div>
    <el-card v-loading="loading" class="calendar-card">
      <el-calendar v-model="selectedDate" @panel-change="handlePanelChange">
        <template #date-cell="{ data }">
          <div class="calendar-cell" @click="openDay(data.day)">
            <span class="day-number">{{ data.day.slice(-2) }}</span>
            <div class="course-events">
              <el-button
                v-for="course in coursesByDate.get(data.day)?.slice(0, 3)"
                :key="course.id"
                class="course-event"
                text
                @click.stop="openEdit(course)"
              >
                <span>{{ formatTime(course.start_time) }}</span>
                <strong>{{ course.customer_name }}</strong>
                <em>{{ course.session_topic }}</em>
              </el-button>
              <span v-if="(coursesByDate.get(data.day)?.length ?? 0) > 3" class="more-events">
                查看全部 {{ coursesByDate.get(data.day)?.length }} 节
              </span>
            </div>
          </div>
        </template>
      </el-calendar>
    </el-card>
    <el-dialog v-model="dialogVisible" :title="dialogTitle" width="520px" destroy-on-close>
      <el-form ref="formRef" :model="form" label-width="96px">
        <el-form-item label="客户" prop="customer" :rules="[{ required: true, message: '请选择客户' }]">
          <el-select v-model="form.customer" filterable placeholder="搜索并选择客户" class="full-width" @change="handleCustomerChange">
            <el-option v-for="customer in customers" :key="customer.id" :label="customer.name" :value="customer.id">
              <span>{{ customer.name }}</span>
              <span class="customer-issue">{{ customer.main_issue }}</span>
            </el-option>
          </el-select>
        </el-form-item>
        <el-form-item label="计划内课程">
          <el-select v-model="form.plan_course" placeholder="选择客户课程计划中的课程（可选）" clearable class="full-width" @change="handlePlanCourseChange">
            <el-option
              v-for="item in planCourses"
              :key="item.id"
              :label="`${item.rehab_plan_name} · ${item.course_type_name}（剩余 ${item.remaining_count} 次）`"
              :value="item.id"
              :disabled="(item.rehab_plan_status !== 'active' || item.status !== 'active') && item.id !== form.plan_course"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="课时" prop="session_count">
          <el-input-number v-model="form.session_count" :min="0.5" :step="0.5" :precision="1" />
          <span class="field-hint">按所选计划内课程自动带出，可调整</span>
        </el-form-item>
        <el-form-item label="本节主题" prop="session_topic" :rules="[{ required: true, message: '请输入本节训练主题' }]">
          <el-select v-model="form.session_topic" filterable allow-create default-first-option placeholder="选择或输入本节训练主题" class="full-width">
            <el-option label="初次评估" value="初次评估" />
            <el-option label="疼痛控制训练" value="疼痛控制训练" />
            <el-option label="活动度恢复" value="活动度恢复" />
            <el-option label="力量重建训练" value="力量重建训练" />
            <el-option label="功能回归训练" value="功能回归训练" />
            <el-option label="阶段复评" value="阶段复评" />
          </el-select>
        </el-form-item>
        <el-form-item label="日期" prop="date" :rules="[{ required: true, message: '请选择日期' }]">
          <el-date-picker v-model="form.date" type="date" value-format="YYYY-MM-DD" class="full-width" />
        </el-form-item>
        <el-form-item label="时间段">
          <div class="time-row">
            <el-time-picker v-model="form.start_time" value-format="HH:mm:ss" placeholder="开始时间" @change="handleStartTimeChange" />
            <span>至</span>
            <el-time-picker v-model="form.end_time" value-format="HH:mm:ss" placeholder="结束时间" />
          </div>
        </el-form-item>
        <el-alert
          v-if="editingCourse && ['cancelled', 'absent'].includes(editingCourse.status)"
          title="补课请直接修改本条课程的日期、时间并改回“待上课”，避免为同一次课程重复建单和重复扣课。"
          type="info"
          :closable="false"
          show-icon
        />
        <el-form-item label="状态">
          <el-select v-model="form.status" class="full-width">
            <el-option label="待上课" value="scheduled" />
            <el-option label="已完成（由正式训练记录触发）" value="completed" disabled />
            <el-option label="已取消" value="cancelled" />
            <el-option label="请假" value="absent" />
          </el-select>
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="form.note" type="textarea" :rows="3" maxlength="255" show-word-limit placeholder="例如：首次训练、带评估报告" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button v-if="editingCourse" @click="goTrainingRecord(false)">
          {{ editingCourse.training_record_id ? '查看训练记录' : '填写训练记录' }}
        </el-button>
        <el-button v-if="editingCourse && !editingCourse.training_record_id" @click="goTrainingRecord(true)">AI 记录</el-button>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="handleSave">{{ submitText }}</el-button>
      </template>
    </el-dialog>
    <el-dialog v-model="dayDialogVisible" :title="`${selectedDay} 的课程`" width="560px">
      <el-empty v-if="selectedDayCourses.length === 0" description="当天尚未安排课程" />
      <div v-else class="day-course-list">
        <el-button
          v-for="course in selectedDayCourses"
          :key="course.id"
          class="day-course-item"
          text
          @click="dayDialogVisible = false; openEdit(course)"
        >
          <span class="day-course-time">{{ formatTime(course.start_time) }} - {{ formatTime(course.end_time) }}</span>
          <strong>{{ course.customer_name }}</strong>
          <span>{{ course.session_topic }}</span>
          <el-tag size="small">{{ course.status_display }}</el-tag>
        </el-button>
      </div>
      <template #footer>
        <el-button @click="dayDialogVisible = false">关闭</el-button>
        <el-button type="primary" @click="openCreateForDay">新增课程</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.page-toolbar { display: flex; align-items: center; justify-content: space-between; margin-bottom: 16px; }
.page-toolbar h3 { margin: 0 0 4px; font-size: 20px; }
.page-toolbar p { margin: 0; color: var(--retrue-text-secondary); font-size: 14px; }
.calendar-card { border: 1px solid var(--retrue-border); border-radius: var(--retrue-radius-lg); box-shadow: var(--retrue-shadow); }
.calendar-card :deep(.el-calendar-day) { height: 100px; padding: 0; overflow: hidden; }
.calendar-cell { box-sizing: border-box; height: 100%; padding: 6px; overflow: hidden; cursor: pointer; }
.calendar-cell:hover { background: var(--retrue-primary-light); }
.day-number { color: var(--retrue-text-secondary); font-size: 13px; }
.course-events { display: flex; flex-direction: column; gap: 3px; margin-top: 4px; }
.course-event { max-width: 100%; overflow: hidden; padding: 2px 4px; border: 0; border-radius: 3px; background: var(--retrue-primary-light); color: var(--retrue-primary-dark); cursor: pointer; font: inherit; font-size: 11px; text-align: left; text-overflow: ellipsis; white-space: nowrap; }
.course-event:hover { background: #c9f2dd; }
.course-event span { margin-right: 4px; }
.course-event em { margin-left: 4px; color: var(--retrue-text-muted); font-style: normal; }
.more-events { color: var(--retrue-text-muted); font-size: 11px; }
.full-width { width: 100%; }
.customer-issue { float: right; margin-left: 16px; color: var(--retrue-text-muted); font-size: 12px; }
.field-hint { margin-left: 8px; color: var(--retrue-text-muted); font-size: 12px; }
.time-row { display: flex; align-items: center; gap: 8px; width: 100%; }
.day-course-list { display: flex; flex-direction: column; gap: 8px; }
.day-course-item { display: grid; grid-template-columns: 105px 1fr 1fr auto; gap: 10px; width: 100%; padding: 12px; border: 1px solid var(--retrue-border); border-radius: var(--retrue-radius-sm); background: var(--retrue-surface); cursor: pointer; text-align: left; }
.day-course-item:hover { background: var(--retrue-primary-light); }
.day-course-time { color: var(--retrue-primary); font-weight: 600; }

@media (max-width: 768px) {
  .page-toolbar {
    align-items: flex-start;
  }
}
</style>
