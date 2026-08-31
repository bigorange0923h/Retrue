<script setup lang="ts">
/** 客户课程计划及计划内课程管理。 */

import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'

import { apiCreateCourseType, apiListCourseTypes } from '@/api/courses'
import { useViewport } from '@/composables/useViewport'
import {
  apiAdjustRehabPlanCourse,
  apiCreateRehabPlan,
  apiCreateRehabPlanCourse,
  apiListRehabPlanCourses,
  apiListRehabPlans,
  apiListRehabPlanTemplates,
  apiUpdateRehabPlan,
  apiUpdateRehabPlanCourse,
} from '@/api/rehab'
import type {
  Assessment,
  CoursePackage,
  CourseType,
  PlanCourseStatus,
  RehabPlan,
  RehabPlanCourse,
  RehabPlanCourseDraft,
  RehabPlanTemplate,
} from '@/types/api'

const props = defineProps<{
  customerId: number
  packages: CoursePackage[]
  assessments: Assessment[]
}>()

const router = useRouter()

/** 课程计划调整只能引用已经确认完成的评估。 */
const completedAssessments = computed(() => props.assessments.filter((item) => item.status !== 'draft'))
const { isMobile } = useViewport()

const loading = ref(false)
const plans = ref<RehabPlan[]>([])
const planCourses = ref<RehabPlanCourse[]>([])
const courseTypes = ref<CourseType[]>([])
const planTemplates = ref<RehabPlanTemplate[]>([])

const planVisible = ref(false)
const editingPlanId = ref<number | null>(null)
const planForm = reactive({
  source_template: null as number | null,
  name: '课程计划',
  start_date: '',
  end_date: '',
  status: 'active' as 'active' | 'closed',
  goals: '',
  note: '',
})
const planSource = ref<'template' | 'blank'>('template')
const planCourseDrafts = ref<RehabPlanCourseDraft[]>([])

const courseVisible = ref(false)
const editingCourseId = ref<number | null>(null)
const courseForm = reactive({
  rehab_plan: null as number | null,
  course_type: null as number | null,
  package: null as number | null,
  planned_count: 1,
  session_cost: 1,
  duration: null as number | null,
  status: 'active' as PlanCourseStatus,
  goals: '',
})

const adjustmentVisible = ref(false)
const adjustingCourse = ref<RehabPlanCourse | null>(null)
const adjustmentForm = reactive({ delta_count: 1, reason: '', assessment: null as number | null })

/** 新建课程类型（供在计划内即时新建课程）。 */
const courseTypeVisible = ref(false)
const courseTypeSaving = ref(false)
const courseTypeForm = reactive({
  name: '',
  description: '',
  default_duration: null as number | null,
  default_session_cost: 1.0,
  default_goals: '',
})
/** 新建课程的目标：'draft' 回填到计划预览草稿，'course' 回填到计划内课程表单。 */
const courseTypeTarget = ref<{ kind: 'draft' | 'course'; index?: number } | null>(null)

function openCreateCourseType(kind: 'draft' | 'course', index?: number): void {
  courseTypeTarget.value = { kind, index }
  courseTypeForm.name = ''
  courseTypeForm.description = ''
  courseTypeForm.default_duration = null
  courseTypeForm.default_session_cost = 1.0
  courseTypeForm.default_goals = ''
  courseTypeVisible.value = true
}

async function saveCourseType(): Promise<void> {
  if (!courseTypeForm.name.trim()) {
    ElMessage.warning('请输入课程名称')
    return
  }
  courseTypeSaving.value = true
  try {
    const created = await apiCreateCourseType({ ...courseTypeForm })
    ElMessage.success('课程已创建')
    courseTypeVisible.value = false
    // 刷新课程类型列表并自动选中新建课程
    courseTypes.value = await apiListCourseTypes()
    const target = courseTypeTarget.value
    if (target?.kind === 'draft' && target.index !== undefined) {
      const draft = planCourseDrafts.value[target.index]
      if (draft) {
        draft.course_type = created.id
        handlePlanDraftCourseTypeChange(draft)
      }
    } else if (target?.kind === 'course') {
      courseForm.course_type = created.id
      handleCourseTypeChange(created.id)
    }
    courseTypeTarget.value = null
  } finally {
    courseTypeSaving.value = false
  }
}

async function load(): Promise<void> {
  loading.value = true
  try {
    const [planResult, courseResult, typeResult, templateResult] = await Promise.all([
      apiListRehabPlans(props.customerId),
      apiListRehabPlanCourses({ customer_id: props.customerId }),
      apiListCourseTypes(),
      apiListRehabPlanTemplates({ active_only: 1 }),
    ])
    plans.value = planResult
    planCourses.value = courseResult
    courseTypes.value = typeResult
    planTemplates.value = templateResult
  } finally {
    loading.value = false
  }
}

function coursesForPlan(planId: number): RehabPlanCourse[] {
  return planCourses.value.filter((item) => item.rehab_plan === planId)
}

function openCreatePlan(): void {
  editingPlanId.value = null
  planSource.value = planTemplates.value.length > 0 ? 'template' : 'blank'
  planCourseDrafts.value = []
  Object.assign(planForm, {
    source_template: null,
    name: '课程计划',
    start_date: new Date().toISOString().slice(0, 10),
    end_date: '',
    status: 'active',
    goals: '',
    note: '',
  })
  planVisible.value = true
}

/** 按开始日期和模板建议周数计算可编辑的默认结束日期。 */
function calculateSuggestedEndDate(startDate: string, weeks: number | null): string {
  if (!startDate || !weeks) return ''
  const date = new Date(`${startDate}T00:00:00`)
  date.setDate(date.getDate() + weeks * 7 - 1)
  return date.toISOString().slice(0, 10)
}

/** 切换计划创建来源时清空模板和课程预览。 */
function handlePlanSourceChange(): void {
  planForm.source_template = null
  planCourseDrafts.value = []
  planForm.name = '课程计划'
  planForm.goals = ''
  planForm.end_date = ''
}

/** 选择课程计划模板后复制模板内容到客户计划预览。 */
function handlePlanTemplateChange(templateId: number): void {
  const template = planTemplates.value.find((item) => item.id === templateId)
  if (!template) return
  planForm.name = template.name
  planForm.goals = template.goals
  planForm.end_date = calculateSuggestedEndDate(
    planForm.start_date,
    template.suggested_duration_weeks,
  )
  planCourseDrafts.value = template.courses.map((item) => ({
    course_type: item.course_type,
    package: props.packages.length === 1 ? props.packages[0]?.id ?? null : null,
    planned_count: item.planned_count,
    session_cost: item.session_cost,
    duration: item.duration,
    goals: item.goals,
  }))
}

/** 开始日期变化后按当前模板建议周数刷新默认结束日期。 */
function handlePlanStartDateChange(): void {
  if (planSource.value !== 'template' || !planForm.source_template) return
  const template = planTemplates.value.find((item) => item.id === planForm.source_template)
  if (!template) return
  planForm.end_date = calculateSuggestedEndDate(
    planForm.start_date,
    template.suggested_duration_weeks,
  )
}

/** 在创建客户计划的预览中增加一门课程。 */
function addPlanDraftCourse(): void {
  planCourseDrafts.value.push({
    course_type: 0,
    package: props.packages.length === 1 ? props.packages[0]?.id ?? null : null,
    planned_count: 1,
    session_cost: 1,
    duration: null,
    goals: '',
  })
}

/** 选择单课程模板后复制其默认字段到客户计划预览。 */
function handlePlanDraftCourseTypeChange(draft: RehabPlanCourseDraft): void {
  const courseType = courseTypes.value.find((item) => item.id === draft.course_type)
  if (!courseType) return
  draft.session_cost = courseType.default_session_cost
  draft.duration = courseType.default_duration
  draft.goals = courseType.default_goals
}

/** 同一个客户计划不重复添加相同课程类型。 */
function planDraftCourseDisabled(courseTypeId: number, currentIndex: number): boolean {
  return planCourseDrafts.value.some(
    (item, index) => index !== currentIndex && item.course_type === courseTypeId,
  )
}

function openEditPlan(plan: RehabPlan): void {
  editingPlanId.value = plan.id
  Object.assign(planForm, {
    name: plan.name,
    source_template: plan.source_template,
    start_date: plan.start_date,
    end_date: plan.end_date ?? '',
    status: plan.status,
    goals: plan.goals,
    note: plan.note,
  })
  planVisible.value = true
}

async function savePlan(): Promise<void> {
  if (!planForm.name.trim() || !planForm.start_date) {
    ElMessage.warning('请填写计划名称和开始日期')
    return
  }
  const payload = {
    customer: props.customerId,
    source_template: planForm.source_template,
    name: planForm.name,
    start_date: planForm.start_date,
    end_date: planForm.end_date || null,
    status: planForm.status,
    goals: planForm.goals,
    note: planForm.note,
  }
  let createdPlan: RehabPlan | null = null
  if (editingPlanId.value) {
    await apiUpdateRehabPlan(editingPlanId.value, payload)
    ElMessage.success('课程计划已更新')
  } else {
    if (planSource.value === 'template' && !planForm.source_template) {
      ElMessage.warning('请选择课程计划模板')
      return
    }
    if (planSource.value === 'template' && planCourseDrafts.value.length === 0) {
      ElMessage.warning('从课程计划模板创建时至少保留一门课程')
      return
    }
    if (planCourseDrafts.value.some((item) => !item.course_type || item.planned_count <= 0)) {
      ElMessage.warning('请完整选择课程并填写计划次数')
      return
    }
    createdPlan = await apiCreateRehabPlan({
      ...payload,
      source_template: planSource.value === 'template' ? planForm.source_template : null,
      courses: planCourseDrafts.value,
    })
    ElMessage.success('课程计划已创建')
  }
  planVisible.value = false
  await load()
  if (createdPlan) {
    try {
      await ElMessageBox.confirm(
        '课程计划已保存，是否现在安排上课时间？',
        '安排课程',
        {
          confirmButtonText: '现在安排',
          cancelButtonText: '稍后再说',
          closeOnClickModal: false,
          type: 'success',
        },
      )
      router.push({
        name: 'schedule',
        query: {
          customerId: String(props.customerId),
          planId: String(createdPlan.id),
        },
      })
    } catch {
      // 康复师选择稍后安排时留在客户详情页。
    }
  }
}

/** 从某门课程直接进入课表，并自动带入客户和课程。 */
function openSchedule(course: RehabPlanCourse): void {
  const remaining = course.unscheduled_count ?? Math.max(
    course.planned_count - course.completed_count - (course.scheduled_count ?? 0),
    0,
  )
  if (remaining <= 0) {
    ElMessage.info('该课程已全部安排')
    return
  }
  router.push({
    name: 'schedule',
    query: {
      customerId: String(props.customerId),
      planCourseId: String(course.id),
      planId: String(course.rehab_plan),
    },
  })
}

function scheduledCount(course: RehabPlanCourse): number {
  return course.scheduled_count ?? 0
}

function unscheduledCount(course: RehabPlanCourse): number {
  return course.unscheduled_count ?? Math.max(
    course.planned_count - course.completed_count - scheduledCount(course),
    0,
  )
}

function nextSessionLabel(course: RehabPlanCourse): string {
  const session = course.next_session
  if (!session?.date) return '尚未安排'
  const time = session.start_time ? session.start_time.slice(0, 5) : '时间待定'
  return `${session.date} ${time}`
}

function canSchedule(course: RehabPlanCourse): boolean {
  return course.rehab_plan_status === 'active' && course.status === 'active' && unscheduledCount(course) > 0
}

function openCreateCourse(plan: RehabPlan): void {
  editingCourseId.value = null
  Object.assign(courseForm, {
    rehab_plan: plan.id,
    course_type: null,
    package: props.packages.length === 1 ? props.packages[0]?.id ?? null : null,
    planned_count: 1,
    session_cost: 1,
    duration: null,
    status: 'active',
    goals: '',
  })
  courseVisible.value = true
}

function openEditCourse(course: RehabPlanCourse): void {
  editingCourseId.value = course.id
  Object.assign(courseForm, {
    rehab_plan: course.rehab_plan,
    course_type: course.course_type,
    package: course.package,
    planned_count: course.planned_count,
    session_cost: course.session_cost,
    duration: course.duration,
    status: course.status,
    goals: course.goals,
  })
  courseVisible.value = true
}

function handleCourseTypeChange(typeId: number): void {
  if (editingCourseId.value) return
  const template = courseTypes.value.find((item) => item.id === typeId)
  if (!template) return
  courseForm.session_cost = template.default_session_cost
  courseForm.duration = template.default_duration
  courseForm.goals = template.default_goals
}

async function saveCourse(): Promise<void> {
  if (!courseForm.rehab_plan || !courseForm.course_type) {
    ElMessage.warning('请选择课程模板')
    return
  }
  const payload: Partial<RehabPlanCourse> = {
    ...courseForm,
    rehab_plan: courseForm.rehab_plan as number,
    course_type: courseForm.course_type as number,
  }
  if (editingCourseId.value) {
    await apiUpdateRehabPlanCourse(editingCourseId.value, payload)
    ElMessage.success('计划内课程已更新')
  } else {
    await apiCreateRehabPlanCourse(payload)
    ElMessage.success('计划内课程已添加')
  }
  courseVisible.value = false
  await load()
}

function openAdjustment(course: RehabPlanCourse): void {
  adjustingCourse.value = course
  adjustmentForm.delta_count = 1
  adjustmentForm.reason = ''
  adjustmentForm.assessment = null
  adjustmentVisible.value = true
}

async function saveAdjustment(): Promise<void> {
  if (!adjustingCourse.value) return
  if (!adjustmentForm.delta_count || !adjustmentForm.reason.trim()) {
    ElMessage.warning('请填写增减次数和调整原因')
    return
  }
  await apiAdjustRehabPlanCourse(
    adjustingCourse.value.id,
    adjustmentForm.delta_count,
    adjustmentForm.reason,
    adjustmentForm.assessment,
  )
  ElMessage.success('计划次数已调整')
  adjustmentVisible.value = false
  await load()
}

function assessmentLabel(assessmentId: number | null): string {
  if (!assessmentId) return ''
  const assessment = props.assessments.find((item) => item.id === assessmentId)
  return assessment
    ? `${assessment.assessment_date} ${assessment.assessment_type_display}`
    : `评估 #${assessmentId}`
}

function statusTag(status: string): 'success' | 'warning' | 'info' | 'danger' {
  if (status === 'active') return 'success'
  if (status === 'paused') return 'warning'
  if (status === 'cancelled') return 'danger'
  return 'info'
}

onMounted(load)
</script>

<template>
  <div v-loading="loading" class="plan-manager">
    <div class="section-header">
      <div>
        <strong>客户课程计划</strong>
        <div class="section-hint">一个计划可安排多种课程，并根据客户情况调整课程和次数。</div>
      </div>
      <el-button type="primary" size="small" @click="openCreatePlan">新建计划</el-button>
    </div>

    <el-empty v-if="!loading && plans.length === 0" description="尚未建立课程计划" :image-size="60" />

    <div v-for="plan in plans" :key="plan.id" class="plan-card">
      <div class="plan-header">
        <div>
          <div class="plan-title">
            {{ plan.name }}
            <el-tag :type="plan.status === 'active' ? 'success' : 'info'" size="small">
              {{ plan.status_display }}
            </el-tag>
          </div>
          <div class="plan-meta">
            {{ plan.start_date }} ～ {{ plan.end_date || '未设结束日期' }}
          </div>
          <div v-if="plan.source_template_name" class="plan-template-source">
            来源模板：{{ plan.source_template_name }}（已复制为客户独立计划）
          </div>
          <div v-if="plan.goals" class="plan-goals">计划目标：{{ plan.goals }}</div>
        </div>
        <div class="plan-actions">
          <el-button link type="primary" @click="openEditPlan(plan)">编辑计划</el-button>
          <el-button v-if="plan.status === 'active'" type="primary" size="small" @click="openCreateCourse(plan)">
            添加课程
          </el-button>
        </div>
      </div>

      <el-table :data="coursesForPlan(plan.id)" size="small" empty-text="该计划尚未添加课程">
        <el-table-column type="expand" width="44">
          <template #default="{ row }">
            <div class="adjustment-history">
              <div class="history-title">次数调整记录</div>
              <el-empty v-if="row.adjustments.length === 0" description="暂无调整" :image-size="42" />
              <div v-for="item in row.adjustments" :key="item.id" class="history-item">
                <span>{{ item.before_count }} → {{ item.after_count }} 次</span>
                <span>{{ item.reason }}</span>
                <span v-if="item.assessment">依据：{{ assessmentLabel(item.assessment) }}</span>
                <span>{{ item.therapist_name }} · {{ item.created_at.slice(0, 16).replace('T', ' ') }}</span>
              </div>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="course_type_name" label="课程" min-width="140" />
        <el-table-column prop="duration" label="单次时长" width="95">
          <template #default="{ row }">{{ row.duration ? `${row.duration} 分钟` : '—' }}</template>
        </el-table-column>
        <el-table-column prop="session_cost" label="单次课时" width="90" />
        <el-table-column prop="planned_count" label="计划" width="70" />
        <el-table-column prop="completed_count" label="已上" width="70" />
        <el-table-column label="已安排" width="80">
          <template #default="{ row }">{{ scheduledCount(row) }}</template>
        </el-table-column>
        <el-table-column label="待安排" width="80">
          <template #default="{ row }">
            <strong :class="{ 'remaining-warning': unscheduledCount(row) > 0 }">{{ unscheduledCount(row) }}</strong>
          </template>
        </el-table-column>
        <el-table-column label="下次上课" min-width="145">
          <template #default="{ row }">
            <span>{{ nextSessionLabel(row) }}</span>
            <el-tag v-if="row.overdue_count" type="warning" size="small" class="overdue-tag">待处理 {{ row.overdue_count }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-tag :type="statusTag(row.status)" size="small">{{ row.status_display }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="220" fixed="right">
          <template #default="{ row }">
            <el-button
              type="primary"
              link
              :disabled="!canSchedule(row)"
              :title="canSchedule(row) ? '安排后续上课时间' : unscheduledCount(row) === 0 ? '该课程已全部安排' : '当前课程暂不能安排'"
              @click="openSchedule(row)"
            >
              安排课程
            </el-button>
            <el-button link type="primary" :disabled="row.rehab_plan_status !== 'active' || row.status === 'cancelled'" @click="openAdjustment(row)">调整次数</el-button>
            <el-button link :disabled="row.rehab_plan_status !== 'active'" @click="openEditCourse(row)">编辑</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <el-dialog
      v-model="planVisible"
      :title="editingPlanId ? '编辑课程计划' : '新建课程计划'"
      :width="isMobile ? 'calc(100vw - 24px)' : '880px'"
    >
      <el-form :model="planForm" label-width="90px">
        <template v-if="!editingPlanId">
          <el-alert
            title="课程计划模板只用于生成初始方案，创建后可按客户实际情况独立调整，不会随模板变化。"
            type="info"
            :closable="false"
            class="template-copy-alert"
          />
          <el-form-item label="创建方式">
            <el-radio-group v-model="planSource" @change="handlePlanSourceChange">
              <el-radio-button value="template" :disabled="planTemplates.length === 0">从课程计划模板创建</el-radio-button>
              <el-radio-button value="blank">创建空白计划</el-radio-button>
            </el-radio-group>
          </el-form-item>
          <el-form-item v-if="planSource === 'template'" label="计划模板" required>
            <el-select
              v-model="planForm.source_template"
              placeholder="选择已维护的课程计划模板"
              @change="handlePlanTemplateChange"
            >
              <el-option
                v-for="item in planTemplates"
                :key="item.id"
                :label="`${item.name}（${item.total_planned_count} 次）`"
                :value="item.id"
              />
            </el-select>
          </el-form-item>
          <el-alert
            v-if="planTemplates.length === 0"
            title="尚未维护课程计划模板，本次可创建空白计划，之后可在“课程模板与计划模板”中维护。"
            type="warning"
            :closable="false"
            class="template-copy-alert"
          />
        </template>
        <el-form-item label="计划名称"><el-input v-model="planForm.name" /></el-form-item>
        <el-form-item label="起止日期">
          <div class="date-row">
            <el-date-picker v-model="planForm.start_date" type="date" value-format="YYYY-MM-DD" placeholder="开始日期" @change="handlePlanStartDateChange" />
            <span>至</span>
            <el-date-picker v-model="planForm.end_date" type="date" value-format="YYYY-MM-DD" placeholder="结束日期（可空）" />
          </div>
        </el-form-item>
        <el-form-item label="计划目标"><el-input v-model="planForm.goals" type="textarea" :rows="3" /></el-form-item>
        <el-form-item label="备注"><el-input v-model="planForm.note" type="textarea" :rows="2" /></el-form-item>
        <el-form-item v-if="editingPlanId" label="状态">
          <el-radio-group v-model="planForm.status">
            <el-radio-button value="active">进行中</el-radio-button>
            <el-radio-button value="closed">已结束</el-radio-button>
          </el-radio-group>
        </el-form-item>

        <template v-if="!editingPlanId">
          <el-divider content-position="left">计划内课程预览</el-divider>
          <div v-if="planCourseDrafts.length === 0" class="draft-empty">
            当前尚未添加课程，可先创建空白计划，也可以在下方添加课程。
          </div>
          <div v-for="(draft, index) in planCourseDrafts" :key="index" class="plan-draft-course">
            <div class="draft-course-heading">
              <strong>课程 {{ index + 1 }}</strong>
              <el-button link type="danger" @click="planCourseDrafts.splice(index, 1)">移除</el-button>
            </div>
            <div class="draft-course-grid">
              <el-form-item label="课程类型" required>
                <div class="course-type-picker">
                  <el-select
                    v-model="draft.course_type"
                    placeholder="选择课程"
                    @change="handlePlanDraftCourseTypeChange(draft)"
                  >
                    <el-option
                      v-for="item in courseTypes"
                      :key="item.id"
                      :label="item.name"
                      :value="item.id"
                      :disabled="!item.is_active || planDraftCourseDisabled(item.id, index)"
                    />
                  </el-select>
                  <el-button link type="primary" @click="openCreateCourseType('draft', index)">
                    新建课程
                  </el-button>
                </div>
              </el-form-item>
              <el-form-item label="计划次数" required>
                <el-input-number v-model="draft.planned_count" :min="1" :step="1" />
              </el-form-item>
              <el-form-item label="单次时长">
                <el-input-number v-model="draft.duration" :min="15" :step="15" />
                <span class="field-hint">分钟</span>
              </el-form-item>
              <el-form-item label="单次扣减">
                <el-input-number v-model="draft.session_cost" :min="0.5" :step="0.5" :precision="1" />
                <span class="field-hint">课时</span>
              </el-form-item>
              <el-form-item label="扣减课时包">
                <el-select v-model="draft.package" clearable placeholder="可选">
                  <el-option
                    v-for="item in props.packages"
                    :key="item.id"
                    :label="`${item.name}（余 ${item.remaining_sessions}）`"
                    :value="item.id"
                  />
                </el-select>
              </el-form-item>
              <el-form-item label="课程目标" class="draft-goals">
                <el-input v-model="draft.goals" placeholder="针对该客户调整课程目标" />
              </el-form-item>
            </div>
          </div>
          <el-button class="add-draft-course-button" @click="addPlanDraftCourse">
            <el-icon><Plus /></el-icon>
            添加课程
          </el-button>
        </template>
      </el-form>
      <template #footer>
        <el-button @click="planVisible = false">取消</el-button>
        <el-button type="primary" @click="savePlan">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="courseVisible" :title="editingCourseId ? '编辑计划内课程' : '添加计划内课程'" width="520px">
      <el-form :model="courseForm" label-width="105px">
        <el-form-item label="课程模板">
          <div class="course-type-picker">
            <el-select v-model="courseForm.course_type" :disabled="Boolean(editingCourseId)" @change="handleCourseTypeChange">
              <el-option v-for="item in courseTypes" :key="item.id" :label="item.name" :value="item.id" :disabled="!item.is_active" />
            </el-select>
            <el-button v-if="!editingCourseId" link type="primary" @click="openCreateCourseType('course')">
              新建课程
            </el-button>
          </div>
        </el-form-item>
        <el-form-item label="计划次数">
          <el-input-number v-model="courseForm.planned_count" :min="0" :step="1" :disabled="Boolean(editingCourseId)" />
          <span v-if="editingCourseId" class="field-hint">请使用列表中的“调整次数”并填写原因</span>
        </el-form-item>
        <el-form-item label="单次时长"><el-input-number v-model="courseForm.duration" :min="15" :step="15" /> <span class="field-hint">分钟</span></el-form-item>
        <el-form-item label="单次课时"><el-input-number v-model="courseForm.session_cost" :min="0.5" :step="0.5" :precision="1" /></el-form-item>
        <el-form-item label="扣减课时包">
          <el-select v-model="courseForm.package" clearable placeholder="不关联则不扣课时">
            <el-option v-for="item in props.packages" :key="item.id" :label="`${item.name}（余 ${item.remaining_sessions}）`" :value="item.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="课程目标"><el-input v-model="courseForm.goals" type="textarea" :rows="2" /></el-form-item>
        <el-form-item v-if="editingCourseId" label="状态">
          <el-select v-model="courseForm.status">
            <el-option label="进行中" value="active" />
            <el-option label="暂停" value="paused" />
            <el-option label="已完成（系统自动）" value="completed" disabled />
            <el-option label="已取消" value="cancelled" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="courseVisible = false">取消</el-button>
        <el-button type="primary" @click="saveCourse">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="adjustmentVisible" title="调整计划次数" width="min(430px, 92vw)">
      <p v-if="adjustingCourse" class="adjust-summary">
        {{ adjustingCourse.course_type_name }}：当前计划 {{ adjustingCourse.planned_count }} 次，已完成 {{ adjustingCourse.completed_count }} 次
      </p>
      <el-form :model="adjustmentForm" label-width="80px">
        <el-form-item label="增减次数">
          <el-input-number v-model="adjustmentForm.delta_count" :step="1" />
          <span class="field-hint">正数增加，负数减少</span>
        </el-form-item>
        <el-form-item label="调整原因">
          <el-input v-model="adjustmentForm.reason" type="textarea" :rows="3" placeholder="例如：复评后恢复良好，减少 2 次疼痛控制课程" />
        </el-form-item>
        <el-form-item label="关联复评">
          <el-select v-model="adjustmentForm.assessment" clearable placeholder="可选：选择本次调整依据">
            <el-option
              v-for="item in completedAssessments"
              :key="item.id"
              :label="`${item.assessment_date} · ${item.assessment_type_display}`"
              :value="item.id"
            />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="adjustmentVisible = false">取消</el-button>
        <el-button type="primary" @click="saveAdjustment">确认调整</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="courseTypeVisible" title="新建课程" width="520px">
      <el-form :model="courseTypeForm" label-width="105px">
        <el-form-item label="课程名称" required>
          <el-input v-model="courseTypeForm.name" placeholder="如：膝关节术后力量重建" />
        </el-form-item>
        <el-form-item label="简介">
          <el-input v-model="courseTypeForm.description" placeholder="简要说明该课程（可选）" />
        </el-form-item>
        <el-form-item label="默认课时">
          <el-input-number v-model="courseTypeForm.default_session_cost" :min="0.5" :step="0.5" :precision="1" />
          <span class="field-hint">半课 0.5 / 全课 1.0</span>
        </el-form-item>
        <el-form-item label="默认时长">
          <el-input-number v-model="courseTypeForm.default_duration" :min="15" :step="15" />
          <span class="field-hint">分钟（可空）</span>
        </el-form-item>
        <el-form-item label="课程目标">
          <el-input v-model="courseTypeForm.default_goals" type="textarea" :rows="2" placeholder="默认课程目标（可选）" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="courseTypeVisible = false">取消</el-button>
        <el-button type="primary" :loading="courseTypeSaving" @click="saveCourseType">创建并选用</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.section-header,
.plan-header,
.plan-actions,
.date-row {
  display: flex;
  align-items: center;
}

.section-header,
.plan-header {
  justify-content: space-between;
  gap: 16px;
}

.section-hint,
.plan-meta,
.plan-goals,
.plan-template-source,
.field-hint,
.adjust-summary {
  color: var(--retrue-text-secondary);
  font-size: 13px;
}

.remaining-warning {
  color: var(--retrue-primary);
}

.overdue-tag {
  margin-left: 6px;
}

.section-hint {
  margin-top: 4px;
}

.plan-card {
  margin-top: 14px;
  padding: 14px;
  border: 1px solid var(--retrue-border);
  border-radius: var(--retrue-radius-md);
}

.plan-header {
  margin-bottom: 12px;
}

.plan-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 600;
}

.plan-meta,
.plan-goals,
.plan-template-source {
  margin-top: 4px;
}

.plan-template-source {
  color: var(--retrue-primary);
}

.plan-actions,
.date-row {
  gap: 8px;
}

.adjust-summary {
  margin-top: 0;
}

.adjustment-history {
  padding: 2px 18px 10px 44px;
}

.template-copy-alert {
  margin-bottom: 16px;
}

.draft-empty {
  margin-bottom: 12px;
  padding: 14px;
  border: 1px dashed var(--retrue-border);
  border-radius: var(--retrue-radius-md);
  color: var(--retrue-text-secondary);
  font-size: 13px;
  text-align: center;
}

.plan-draft-course {
  margin-bottom: 12px;
  padding: 12px;
  border: 1px solid var(--retrue-border);
  border-radius: var(--retrue-radius-md);
  background: var(--retrue-bg);
}

.draft-course-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
}

.draft-course-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0 14px;
}

.draft-course-grid :deep(.el-select),
.draft-course-grid :deep(.el-input-number) {
  width: 100%;
}

.draft-goals {
  grid-column: 1 / -1;
}

.course-type-picker {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
}

.course-type-picker .el-select {
  flex: 1;
}

.add-draft-course-button {
  width: 100%;
  margin: 0;
  border-style: dashed;
}

.history-title {
  margin-bottom: 8px;
  font-weight: 600;
}

@media (max-width: 767px) {
  .section-header,
  .plan-header {
    align-items: flex-start;
  }

  .plan-header {
    flex-direction: column;
  }

  .draft-course-grid {
    grid-template-columns: 1fr;
  }

  .draft-goals {
    grid-column: auto;
  }
}

.history-item {
  display: grid;
  grid-template-columns: 105px minmax(160px, 1fr) minmax(150px, auto) 180px;
  gap: 12px;
  padding: 7px 0;
  color: var(--retrue-text-secondary);
  font-size: 13px;
  border-top: 1px solid var(--retrue-border);
}

@media (max-width: 768px) {
  .section-header,
  .plan-header {
    align-items: flex-start;
    flex-direction: column;
  }

  .date-row {
    align-items: stretch;
    flex-direction: column;
  }
}
</style>
