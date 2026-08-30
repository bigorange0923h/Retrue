<script setup lang="ts">
/** 客户康复周期与周期课程管理。 */

import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'

import { apiListCourseTypes } from '@/api/courses'
import {
  apiAdjustRehabPlanCourse,
  apiCreateRehabPlan,
  apiCreateRehabPlanCourse,
  apiListRehabPlanCourses,
  apiListRehabPlans,
  apiUpdateRehabPlan,
  apiUpdateRehabPlanCourse,
} from '@/api/rehab'
import type { Assessment, CoursePackage, CourseType, PlanCourseStatus, RehabPlan, RehabPlanCourse } from '@/types/api'

const props = defineProps<{
  customerId: number
  packages: CoursePackage[]
  assessments: Assessment[]
}>()

const loading = ref(false)
const plans = ref<RehabPlan[]>([])
const planCourses = ref<RehabPlanCourse[]>([])
const courseTypes = ref<CourseType[]>([])

const planVisible = ref(false)
const editingPlanId = ref<number | null>(null)
const planForm = reactive({
  name: '康复周期',
  start_date: '',
  end_date: '',
  status: 'active' as 'active' | 'closed',
  goals: '',
  note: '',
})

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

async function load(): Promise<void> {
  loading.value = true
  try {
    const [planResult, courseResult, typeResult] = await Promise.all([
      apiListRehabPlans(props.customerId),
      apiListRehabPlanCourses({ customer_id: props.customerId }),
      apiListCourseTypes(),
    ])
    plans.value = planResult
    planCourses.value = courseResult
    courseTypes.value = typeResult
  } finally {
    loading.value = false
  }
}

function coursesForPlan(planId: number): RehabPlanCourse[] {
  return planCourses.value.filter((item) => item.rehab_plan === planId)
}

function openCreatePlan(): void {
  editingPlanId.value = null
  Object.assign(planForm, {
    name: '康复周期',
    start_date: new Date().toISOString().slice(0, 10),
    end_date: '',
    status: 'active',
    goals: '',
    note: '',
  })
  planVisible.value = true
}

function openEditPlan(plan: RehabPlan): void {
  editingPlanId.value = plan.id
  Object.assign(planForm, {
    name: plan.name,
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
    ElMessage.warning('请填写周期名称和开始日期')
    return
  }
  const payload = {
    customer: props.customerId,
    name: planForm.name,
    start_date: planForm.start_date,
    end_date: planForm.end_date || null,
    status: planForm.status,
    goals: planForm.goals,
    note: planForm.note,
  }
  if (editingPlanId.value) {
    await apiUpdateRehabPlan(editingPlanId.value, payload)
    ElMessage.success('康复周期已更新')
  } else {
    await apiCreateRehabPlan(payload)
    ElMessage.success('康复周期已创建')
  }
  planVisible.value = false
  await load()
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
    ElMessage.success('周期课程已更新')
  } else {
    await apiCreateRehabPlanCourse(payload)
    ElMessage.success('周期课程已添加')
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
        <strong>康复周期计划</strong>
        <div class="section-hint">一个周期可安排多种课程，并根据恢复情况调整次数。</div>
      </div>
      <el-button type="primary" size="small" @click="openCreatePlan">新建周期</el-button>
    </div>

    <el-empty v-if="!loading && plans.length === 0" description="尚未建立康复周期" :image-size="60" />

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
          <div v-if="plan.goals" class="plan-goals">周期目标：{{ plan.goals }}</div>
        </div>
        <div class="plan-actions">
          <el-button link type="primary" @click="openEditPlan(plan)">编辑周期</el-button>
          <el-button v-if="plan.status === 'active'" type="primary" size="small" @click="openCreateCourse(plan)">
            添加课程
          </el-button>
        </div>
      </div>

      <el-table :data="coursesForPlan(plan.id)" size="small" empty-text="该周期尚未添加课程">
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
        <el-table-column prop="completed_count" label="已完成" width="80" />
        <el-table-column prop="remaining_count" label="剩余" width="70">
          <template #default="{ row }"><strong>{{ row.remaining_count }}</strong></template>
        </el-table-column>
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-tag :type="statusTag(row.status)" size="small">{{ row.status_display }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="150" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" :disabled="row.rehab_plan_status !== 'active' || row.status === 'cancelled'" @click="openAdjustment(row)">调整次数</el-button>
            <el-button link :disabled="row.rehab_plan_status !== 'active'" @click="openEditCourse(row)">编辑</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <el-dialog v-model="planVisible" :title="editingPlanId ? '编辑康复周期' : '新建康复周期'" width="520px">
      <el-form :model="planForm" label-width="90px">
        <el-form-item label="周期名称"><el-input v-model="planForm.name" /></el-form-item>
        <el-form-item label="起止日期">
          <div class="date-row">
            <el-date-picker v-model="planForm.start_date" type="date" value-format="YYYY-MM-DD" placeholder="开始日期" />
            <span>至</span>
            <el-date-picker v-model="planForm.end_date" type="date" value-format="YYYY-MM-DD" placeholder="结束日期（可空）" />
          </div>
        </el-form-item>
        <el-form-item label="周期目标"><el-input v-model="planForm.goals" type="textarea" :rows="3" /></el-form-item>
        <el-form-item label="备注"><el-input v-model="planForm.note" type="textarea" :rows="2" /></el-form-item>
        <el-form-item v-if="editingPlanId" label="状态">
          <el-radio-group v-model="planForm.status">
            <el-radio-button value="active">进行中</el-radio-button>
            <el-radio-button value="closed">已结束</el-radio-button>
          </el-radio-group>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="planVisible = false">取消</el-button>
        <el-button type="primary" @click="savePlan">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="courseVisible" :title="editingCourseId ? '编辑周期课程' : '添加周期课程'" width="520px">
      <el-form :model="courseForm" label-width="105px">
        <el-form-item label="课程模板">
          <el-select v-model="courseForm.course_type" :disabled="Boolean(editingCourseId)" @change="handleCourseTypeChange">
            <el-option v-for="item in courseTypes" :key="item.id" :label="item.name" :value="item.id" :disabled="!item.is_active" />
          </el-select>
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

    <el-dialog v-model="adjustmentVisible" title="调整计划次数" width="430px">
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
              v-for="item in props.assessments"
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
.field-hint,
.adjust-summary {
  color: var(--retrue-text-secondary);
  font-size: 13px;
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
.plan-goals {
  margin-top: 4px;
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

.history-title {
  margin-bottom: 8px;
  font-weight: 600;
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
