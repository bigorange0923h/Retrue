<script setup lang="ts">
/** 课程管理页：月历展示课程，支持新增、修改与状态管理。 */
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, type FormInstance } from 'element-plus'
import { apiCreateCourse, apiGetCalendarCourses, apiUpdateCourse } from '@/api/courses'
import { apiListCustomers } from '@/api/customers'
import type { CourseSessionItem, CustomerListItem } from '@/types/api'

type CourseForm = { customer: number | undefined; courseName: string; date: string; timeRange: string[]; status: string; note: string }
const loading = ref(false)
const selectedDate = ref(new Date())
const courses = ref<CourseSessionItem[]>([])
const customers = ref<CustomerListItem[]>([])
const dialogVisible = ref(false)
const dayDialogVisible = ref(false)
const selectedDay = ref('')
const saving = ref(false)
const editingCourse = ref<CourseSessionItem | null>(null)
const formRef = ref<FormInstance>()
const form = reactive<CourseForm>({ customer: undefined, courseName: '康复训练', date: '', timeRange: [], status: 'scheduled', note: '' })
const dialogTitle = computed(() => editingCourse.value ? '管理课程' : '新增课程')
const submitText = computed(() => editingCourse.value ? '保存修改' : '添加课程')
const coursesByDate = computed(() => {
  const result = new Map<string, CourseSessionItem[]>()
  for (const course of courses.value) result.set(course.date, [...(result.get(course.date) ?? []), course])
  return result
})
const selectedDayCourses = computed(() => coursesByDate.value.get(selectedDay.value) ?? [])
function formatDate(value: Date): string { return `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, '0')}-${String(value.getDate()).padStart(2, '0')}` }
function formatTime(value: string | null): string { return value ? value.slice(0, 5) : '待定' }
async function loadCalendar(): Promise<void> {
  const year = selectedDate.value.getFullYear(); const month = selectedDate.value.getMonth()
  loading.value = true
  try { courses.value = await apiGetCalendarCourses(formatDate(new Date(year, month, 1)), formatDate(new Date(year, month + 1, 0))) } finally { loading.value = false }
}
async function loadCustomers(): Promise<void> { customers.value = (await apiListCustomers({ status: 'active', page: 1, page_size: 100 })).items }
function openCreate(date = formatDate(selectedDate.value)): void {
  editingCourse.value = null
  Object.assign(form, { customer: undefined, courseName: '康复训练', date, timeRange: [], status: 'scheduled', note: '' })
  dialogVisible.value = true
}
function openEdit(course: CourseSessionItem): void {
  editingCourse.value = course
  Object.assign(form, { customer: course.customer, courseName: course.course_name, date: course.date, timeRange: course.start_time && course.end_time ? [course.start_time, course.end_time] : [], status: course.status, note: course.note })
  dialogVisible.value = true
}
async function handleSave(): Promise<void> {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return
  if (form.timeRange.length === 2 && form.timeRange[1] <= form.timeRange[0]) { ElMessage.warning('结束时间需要晚于开始时间'); return }
  const data = { customer: form.customer as number, course_name: form.courseName, date: form.date, start_time: form.timeRange[0] || null, end_time: form.timeRange[1] || null, status: form.status, note: form.note }
  saving.value = true
  try {
    if (editingCourse.value) { await apiUpdateCourse(editingCourse.value.id, data); ElMessage.success('课程已更新') }
    else { await apiCreateCourse(data); ElMessage.success('课程已添加到课表') }
    dialogVisible.value = false; await loadCalendar()
  } finally { saving.value = false }
}
function handlePanelChange(value: Date): void { selectedDate.value = value; loadCalendar() }
function openDay(date: string): void { selectedDay.value = date; dayDialogVisible.value = true }
function openCreateForDay(): void { dayDialogVisible.value = false; openCreate(selectedDay.value) }
onMounted(async () => { await Promise.all([loadCalendar(), loadCustomers()]) })
</script>

<template>
  <div class="schedule-page">
    <div class="page-toolbar"><div><h3>课程管理</h3><p>按月查看、添加和管理客户课程。</p></div><el-button type="primary" @click="openCreate()">新增课程</el-button></div>
    <el-card v-loading="loading" class="calendar-card">
      <el-calendar v-model="selectedDate" @panel-change="handlePanelChange">
        <template #date-cell="{ data }"><div class="calendar-cell" @click="openDay(data.day)"><span class="day-number">{{ data.day.slice(-2) }}</span><div class="course-events"><button v-for="course in coursesByDate.get(data.day)?.slice(0, 3)" :key="course.id" class="course-event" type="button" @click.stop="openEdit(course)"><span>{{ formatTime(course.start_time) }}</span><strong>{{ course.customer_name }}</strong><em>{{ course.course_name }}</em></button><span v-if="(coursesByDate.get(data.day)?.length ?? 0) > 3" class="more-events">查看全部 {{ coursesByDate.get(data.day)?.length }} 节</span></div></div></template>
      </el-calendar>
    </el-card>
    <el-dialog v-model="dialogVisible" :title="dialogTitle" width="500px" destroy-on-close>
      <el-form ref="formRef" :model="form" label-width="86px">
        <el-form-item label="客户" prop="customer" :rules="[{ required: true, message: '请选择客户' }]"><el-select v-model="form.customer" filterable placeholder="搜索并选择客户" class="full-width"><el-option v-for="customer in customers" :key="customer.id" :label="customer.name" :value="customer.id"><span>{{ customer.name }}</span><span class="customer-issue">{{ customer.main_issue }}</span></el-option></el-select></el-form-item>
        <el-form-item label="课程主题" prop="courseName" :rules="[{ required: true, message: '请选择或输入课程主题' }]"><el-select v-model="form.courseName" filterable allow-create default-first-option placeholder="选择或输入课程主题" class="full-width"><el-option label="初次评估" value="初次评估" /><el-option label="疼痛控制训练" value="疼痛控制训练" /><el-option label="活动度恢复" value="活动度恢复" /><el-option label="力量重建训练" value="力量重建训练" /><el-option label="功能回归训练" value="功能回归训练" /><el-option label="阶段复评" value="阶段复评" /></el-select></el-form-item>
        <el-form-item label="日期" prop="date" :rules="[{ required: true, message: '请选择日期' }]"><el-date-picker v-model="form.date" type="date" value-format="YYYY-MM-DD" class="full-width" /></el-form-item>
        <el-form-item label="时间段"><el-time-picker v-model="form.timeRange" is-range value-format="HH:mm:ss" range-separator="至" start-placeholder="开始时间" end-placeholder="结束时间" class="full-width" /></el-form-item>
        <el-form-item label="状态"><el-select v-model="form.status" class="full-width"><el-option label="待上课" value="scheduled" /><el-option label="已完成" value="completed" /><el-option label="已取消" value="cancelled" /><el-option label="请假" value="absent" /></el-select></el-form-item>
        <el-form-item label="备注"><el-input v-model="form.note" type="textarea" :rows="3" maxlength="255" show-word-limit placeholder="例如：首次训练、带评估报告" /></el-form-item>
      </el-form>
      <template #footer><el-button @click="dialogVisible = false">取消</el-button><el-button type="primary" :loading="saving" @click="handleSave">{{ submitText }}</el-button></template>
    </el-dialog>
    <el-dialog v-model="dayDialogVisible" :title="`${selectedDay} 的课程`" width="560px">
      <el-empty v-if="selectedDayCourses.length === 0" description="当天尚未安排课程" />
      <div v-else class="day-course-list"><button v-for="course in selectedDayCourses" :key="course.id" class="day-course-item" type="button" @click="dayDialogVisible = false; openEdit(course)"><span class="day-course-time">{{ formatTime(course.start_time) }} - {{ formatTime(course.end_time) }}</span><strong>{{ course.customer_name }}</strong><span>{{ course.course_name }}</span><el-tag size="small">{{ course.status_display }}</el-tag></button></div>
      <template #footer><el-button @click="dayDialogVisible = false">关闭</el-button><el-button type="primary" @click="openCreateForDay">新增课程</el-button></template>
    </el-dialog>
  </div>
</template>

<style scoped>
.page-toolbar { display: flex; align-items: center; justify-content: space-between; margin-bottom: 16px; }.page-toolbar h3 { margin: 0 0 4px; font-size: 20px; }.page-toolbar p { margin: 0; color: var(--retrue-text-secondary); font-size: 14px; }.calendar-card { border: 1px solid var(--retrue-border); border-radius: var(--retrue-radius-lg); box-shadow: var(--retrue-shadow); }.calendar-card :deep(.el-calendar-day) { height: 100px; padding: 0; overflow: hidden; }.calendar-cell { box-sizing: border-box; height: 100%; padding: 6px; overflow: hidden; cursor: pointer; }.calendar-cell:hover { background: var(--retrue-primary-light); }.day-number { color: var(--retrue-text-secondary); font-size: 13px; }.course-events { display: flex; flex-direction: column; gap: 3px; margin-top: 4px; }.course-event { max-width: 100%; overflow: hidden; padding: 2px 4px; border: 0; border-radius: 3px; background: var(--retrue-primary-light); color: var(--retrue-primary-dark); cursor: pointer; font: inherit; font-size: 11px; text-align: left; text-overflow: ellipsis; white-space: nowrap; }.course-event:hover { background: #c9f2dd; }.course-event span { margin-right: 4px; }.course-event em { margin-left: 4px; color: var(--retrue-text-muted); font-style: normal; }.more-events { color: var(--retrue-text-muted); font-size: 11px; }.full-width { width: 100%; }.customer-issue { float: right; margin-left: 16px; color: var(--retrue-text-muted); font-size: 12px; }.day-course-list { display: flex; flex-direction: column; gap: 8px; }.day-course-item { display: grid; grid-template-columns: 105px 1fr 1fr auto; gap: 10px; width: 100%; padding: 12px; border: 1px solid var(--retrue-border); border-radius: var(--retrue-radius-sm); background: var(--retrue-surface); cursor: pointer; text-align: left; }.day-course-item:hover { background: var(--retrue-primary-light); }.day-course-time { color: var(--retrue-primary); font-weight: 600; }
</style>
