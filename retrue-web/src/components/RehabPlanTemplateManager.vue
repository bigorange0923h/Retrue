<script setup lang="ts">
/** 课程计划模板管理：维护模板基本信息和多课程默认组成。 */

import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'

import { apiListCourseTypes } from '@/api/courses'
import {
  apiCreateRehabPlanTemplate,
  apiListRehabPlanTemplates,
  apiUpdateRehabPlanTemplate,
} from '@/api/rehab'
import { useViewport } from '@/composables/useViewport'
import type { CourseType, RehabPlanTemplate, RehabPlanTemplateCourse } from '@/types/api'

interface TemplateCourseForm {
  course_type: number | null
  planned_count: number
  session_cost: number
  duration: number | null
  goals: string
  sort_order: number
}

const { isMobile } = useViewport()
const loading = ref(false)
const saving = ref(false)
const keyword = ref('')
const templates = ref<RehabPlanTemplate[]>([])
const courseTypes = ref<CourseType[]>([])
const dialogVisible = ref(false)
const editingId = ref<number | null>(null)

const form = reactive({
  name: '',
  description: '',
  suggested_duration_weeks: null as number | null,
  goals: '',
  is_active: true,
  courses: [] as TemplateCourseForm[],
})

/** 同时加载课程计划模板和可用单课程模板。 */
async function load(): Promise<void> {
  loading.value = true
  try {
    const [templateResult, courseTypeResult] = await Promise.all([
      apiListRehabPlanTemplates({ keyword: keyword.value }),
      apiListCourseTypes(),
    ])
    templates.value = templateResult
    courseTypes.value = courseTypeResult
  } finally {
    loading.value = false
  }
}

/** 新增一行计划模板课程。 */
function addCourse(): void {
  form.courses.push({
    course_type: null,
    planned_count: 1,
    session_cost: 1,
    duration: null,
    goals: '',
    sort_order: form.courses.length,
  })
}

/** 选择课程模板后复制其默认时长、课时和目标。 */
function handleCourseTypeChange(row: TemplateCourseForm): void {
  const courseType = courseTypes.value.find((item) => item.id === row.course_type)
  if (!courseType) return
  row.session_cost = courseType.default_session_cost
  row.duration = courseType.default_duration
  row.goals = courseType.default_goals
}

/** 判断某课程是否已被其他行选择。 */
function courseTypeDisabled(courseTypeId: number, currentIndex: number): boolean {
  return form.courses.some((item, index) => index !== currentIndex && item.course_type === courseTypeId)
}

/** 打开空白课程计划模板表单。 */
function openCreate(): void {
  editingId.value = null
  Object.assign(form, {
    name: '',
    description: '',
    suggested_duration_weeks: null,
    goals: '',
    is_active: true,
    courses: [],
  })
  addCourse()
  dialogVisible.value = true
}

/** 打开已有课程计划模板并复制课程组成到编辑表单。 */
function openEdit(template: RehabPlanTemplate): void {
  editingId.value = template.id
  Object.assign(form, {
    name: template.name,
    description: template.description,
    suggested_duration_weeks: template.suggested_duration_weeks,
    goals: template.goals,
    is_active: template.is_active,
    courses: template.courses.map((item, index) => ({
      course_type: item.course_type,
      planned_count: item.planned_count,
      session_cost: item.session_cost,
      duration: item.duration,
      goals: item.goals,
      sort_order: index,
    })),
  })
  dialogVisible.value = true
}

/** 校验并保存课程计划模板。 */
async function handleSave(): Promise<void> {
  if (!form.name.trim()) {
    ElMessage.warning('请输入课程计划模板名称')
    return
  }
  if (form.is_active && form.courses.length === 0) {
    ElMessage.warning('启用的课程计划模板至少需要一门课程')
    return
  }
  if (form.courses.some((item) => !item.course_type || item.planned_count <= 0)) {
    ElMessage.warning('请完整选择课程并填写计划次数')
    return
  }
  const courses = form.courses.map((item, index) => ({
    ...item,
    course_type: item.course_type as number,
    sort_order: index,
  }))
  const payload = { ...form, courses }
  saving.value = true
  try {
    if (editingId.value) {
      await apiUpdateRehabPlanTemplate(editingId.value, payload)
      ElMessage.success('课程计划模板已更新')
    } else {
      await apiCreateRehabPlanTemplate(payload)
      ElMessage.success('课程计划模板创建成功')
    }
    dialogVisible.value = false
    await load()
  } finally {
    saving.value = false
  }
}

/** 启用或停用课程计划模板。 */
async function toggleActive(template: RehabPlanTemplate): Promise<void> {
  await apiUpdateRehabPlanTemplate(template.id, { is_active: !template.is_active })
  ElMessage.success(template.is_active ? '课程计划模板已停用' : '课程计划模板已启用')
  await load()
}

/** 返回课程组成的紧凑摘要。 */
function courseSummary(courses: RehabPlanTemplateCourse[]): string {
  return courses.map((item) => `${item.course_type_name} ${item.planned_count} 次`).join('、')
}

onMounted(load)
</script>

<template>
  <div class="plan-template-manager">
    <div class="template-toolbar">
      <el-input v-model="keyword" clearable placeholder="搜索课程计划模板" @keyup.enter="load">
        <template #prefix><el-icon><Search /></el-icon></template>
      </el-input>
      <el-button type="primary" @click="load">搜索</el-button>
      <div class="toolbar-spacer" />
      <el-button type="primary" @click="openCreate">新建计划模板</el-button>
    </div>

    <el-skeleton v-if="loading" :rows="5" animated />
    <el-empty v-else-if="templates.length === 0" description="暂无课程计划模板" />

    <el-card v-else-if="!isMobile" shadow="never" class="template-table-card">
      <el-table :data="templates">
        <el-table-column type="expand" width="44">
          <template #default="{ row }">
            <div class="course-detail-list">
              <div v-for="course in row.courses" :key="course.id" class="course-detail-row">
                <strong>{{ course.course_type_name }}</strong>
                <span>{{ course.planned_count }} 次</span>
                <span>{{ course.duration ? `${course.duration} 分钟/次` : '时长未设' }}</span>
                <span>{{ course.session_cost }} 课时/次</span>
                <span>总计 {{ course.planned_count * course.session_cost }} 课时</span>
              </div>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="name" label="计划模板" min-width="170" />
        <el-table-column label="课程组成" min-width="260" show-overflow-tooltip>
          <template #default="{ row }">{{ courseSummary(row.courses) }}</template>
        </el-table-column>
        <el-table-column label="建议周期" width="100">
          <template #default="{ row }">{{ row.suggested_duration_weeks ? `${row.suggested_duration_weeks} 周` : '未设置' }}</template>
        </el-table-column>
        <el-table-column prop="total_planned_count" label="总次数" width="80" />
        <el-table-column label="计划课时" width="95">
          <template #default="{ row }">{{ row.total_session_units }} 课时</template>
        </el-table-column>
        <el-table-column prop="usage_count" label="已应用" width="80" />
        <el-table-column label="状态" width="80">
          <template #default="{ row }"><el-tag :type="row.is_active ? 'success' : 'info'">{{ row.status_display }}</el-tag></template>
        </el-table-column>
        <el-table-column label="操作" width="150" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
            <el-button v-if="row.is_active" link type="warning" @click="toggleActive(row)">停用</el-button>
            <el-button v-else link type="success" @click="toggleActive(row)">启用</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <div v-else class="template-card-list">
      <el-card v-for="template in templates" :key="template.id" shadow="never" class="template-card">
        <div class="template-card-header">
          <strong>{{ template.name }}</strong>
          <el-tag size="small" :type="template.is_active ? 'success' : 'info'">{{ template.status_display }}</el-tag>
        </div>
        <p>{{ template.description || '暂无适用说明' }}</p>
        <div class="template-course-summary">{{ courseSummary(template.courses) || '暂未添加课程' }}</div>
        <div class="template-meta">
          <span>{{ template.suggested_duration_weeks ? `${template.suggested_duration_weeks} 周` : '周期未设' }}</span>
          <span>{{ template.total_planned_count }} 次</span>
          <span>{{ template.total_session_units }} 课时</span>
        </div>
        <div class="template-card-actions">
          <el-button size="small" @click="openEdit(template)">编辑</el-button>
          <el-button v-if="template.is_active" size="small" type="warning" @click="toggleActive(template)">停用</el-button>
          <el-button v-else size="small" type="success" @click="toggleActive(template)">启用</el-button>
        </div>
      </el-card>
    </div>

    <el-button v-if="isMobile" type="primary" class="mobile-create-button" @click="openCreate">新建计划模板</el-button>

    <el-dialog
      v-model="dialogVisible"
      :title="editingId ? '编辑课程计划模板' : '新建课程计划模板'"
      :width="isMobile ? 'calc(100vw - 24px)' : '960px'"
      class="plan-template-dialog"
    >
      <el-form :model="form" label-position="top">
        <div class="base-form-grid">
          <el-form-item label="模板名称" required>
            <el-input v-model="form.name" placeholder="如：膝关节术后恢复、青少年体能提升" />
          </el-form-item>
          <el-form-item label="建议时长">
            <div class="number-field">
              <el-input-number v-model="form.suggested_duration_weeks" :min="1" :step="1" />
              <span class="field-hint">周</span>
            </div>
          </el-form-item>
        </div>
        <el-form-item label="适用说明">
          <el-input v-model="form.description" placeholder="说明适用人群或问题" />
        </el-form-item>
        <el-form-item label="计划目标">
          <el-input v-model="form.goals" type="textarea" :rows="2" placeholder="应用到客户课程计划时作为默认目标" />
        </el-form-item>
        <el-form-item label="启用状态">
          <el-switch v-model="form.is_active" active-text="启用" inactive-text="停用" />
        </el-form-item>

        <el-divider content-position="left">课程组成</el-divider>
        <el-alert
          v-if="courseTypes.every((item) => !item.is_active)"
          title="请先在“课程模板”标签创建并启用至少一门课程，再维护课程计划模板。"
          type="warning"
          :closable="false"
          class="course-type-alert"
        />
        <div v-for="(course, index) in form.courses" :key="index" class="template-course-editor">
          <div class="course-editor-heading">
            <strong>课程 {{ index + 1 }}</strong>
            <el-button link type="danger" @click="form.courses.splice(index, 1)">移除</el-button>
          </div>
          <div class="course-editor-grid">
            <el-form-item label="课程模板" required>
              <el-select
                v-model="course.course_type"
                class="course-template-select"
                filterable
                placeholder="选择课程模板"
                @change="handleCourseTypeChange(course)"
              >
                <el-option
                  v-for="item in courseTypes"
                  :key="item.id"
                  :label="item.name"
                  :value="item.id"
                  :disabled="!item.is_active || courseTypeDisabled(item.id, index)"
                />
              </el-select>
            </el-form-item>
            <el-form-item label="计划次数" required>
              <el-input-number v-model="course.planned_count" :min="1" :step="1" />
            </el-form-item>
            <el-form-item label="单次时长">
              <div class="number-field">
                <el-input-number v-model="course.duration" :min="15" :step="15" />
                <span class="field-hint">分钟</span>
              </div>
            </el-form-item>
            <el-form-item label="单次扣减">
              <div class="number-field">
                <el-input-number v-model="course.session_cost" :min="0.5" :step="0.5" :precision="1" />
                <span class="field-hint">课时</span>
              </div>
            </el-form-item>
          </div>
          <el-form-item label="课程目标">
            <el-input v-model="course.goals" placeholder="该课程在计划内的默认目标" />
          </el-form-item>
        </div>
        <el-button class="add-course-button" @click="addCourse">
          <el-icon><Plus /></el-icon>
          添加课程
        </el-button>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="handleSave">保存模板</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.plan-template-manager { display: flex; flex-direction: column; gap: 14px; }
.template-toolbar { display: flex; align-items: center; gap: 10px; }
.template-toolbar :deep(.el-input) { width: 280px; }
.toolbar-spacer { flex: 1; }
.template-table-card, .template-card { border-color: var(--retrue-border); border-radius: var(--retrue-radius-md); }
.course-detail-list { padding: 4px 28px 10px; }
.course-detail-row { display: grid; grid-template-columns: minmax(140px, 1fr) repeat(4, minmax(100px, auto)); gap: 18px; padding: 8px 0; color: var(--retrue-text-secondary); font-size: 13px; }
.course-detail-row + .course-detail-row { border-top: 1px solid var(--retrue-border); }
.course-detail-row strong { color: var(--retrue-text); }
.template-card-list { display: flex; flex-direction: column; gap: 10px; }
.template-card-header, .template-card-actions, .template-meta, .course-editor-heading { display: flex; align-items: center; }
.template-card-header, .course-editor-heading { justify-content: space-between; gap: 8px; }
.template-card p { margin: 8px 0; color: var(--retrue-text-secondary); font-size: 13px; }
.template-course-summary { color: var(--retrue-text); font-size: 13px; line-height: 1.6; }
.template-meta { flex-wrap: wrap; gap: 8px 14px; margin-top: 8px; color: var(--retrue-text-muted); font-size: 12px; }
.template-card-actions { gap: 8px; margin-top: 12px; }
.mobile-create-button { width: 100%; height: 44px; margin: 0; }
.base-form-grid { display: grid; grid-template-columns: minmax(0, 2fr) minmax(220px, 1fr); gap: 16px; }
.template-course-editor { margin-bottom: 12px; padding: 12px; border: 1px solid var(--retrue-border); border-radius: var(--retrue-radius-md); background: var(--retrue-bg); }
.course-type-alert { margin-bottom: 12px; }
.course-editor-heading { margin-bottom: 10px; }
.course-editor-grid { display: grid; grid-template-columns: minmax(250px, 1.8fr) repeat(3, minmax(125px, 1fr)); gap: 12px; }
.course-editor-grid :deep(.el-form-item), .base-form-grid :deep(.el-form-item) { margin-bottom: 12px; }
.course-editor-grid :deep(.el-form-item__content), .base-form-grid :deep(.el-form-item__content) { min-width: 0; }
.course-editor-grid :deep(.el-select), .course-editor-grid :deep(.el-input-number), .base-form-grid :deep(.el-input-number) { width: 100%; }
.course-template-select { min-width: 0; width: 100%; }
.number-field { display: grid; grid-template-columns: minmax(0, 1fr) auto; align-items: center; gap: 6px; width: 100%; }
.field-hint { white-space: nowrap; color: var(--retrue-text-muted); font-size: 12px; }
.add-course-button { width: 100%; margin: 0; border-style: dashed; }

@media (max-width: 767px) {
  .template-toolbar { flex-wrap: wrap; }
  .template-toolbar :deep(.el-input) { width: auto; flex: 1; }
  .template-toolbar > .el-button:last-child, .toolbar-spacer { display: none; }
  .base-form-grid, .course-editor-grid { grid-template-columns: 1fr; gap: 0; }
  .template-course-editor { padding: 10px; }
}
</style>
