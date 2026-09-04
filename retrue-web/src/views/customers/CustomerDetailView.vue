<script setup lang="ts">
/** 客户详情页：展示与编辑客户资料（编辑场景含完整手机号）。 */

import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'

import { apiGetCustomer, apiUpdateCustomer, type CustomerForm } from '@/api/customers'
import { apiListAssessments, apiGetInitialAssessment } from '@/api/assessments'
import { apiListCoursePackages } from '@/api/coursePackages'
import AuxiliaryServices from '@/components/AuxiliaryServices.vue'
import LessonPreparation from '@/components/LessonPreparation.vue'
import RehabOverview from '@/components/RehabOverview.vue'
import RehabPlanManager from '@/components/RehabPlanManager.vue'
import TrainingTimeline from '@/components/TrainingTimeline.vue'
import type { Assessment, CoursePackage, CustomerDetail } from '@/types/api'

const route = useRoute()
const router = useRouter()
const customerId = Number(route.params.id)

const loading = ref(false)
const editing = ref(false)
const saving = ref(false)
const customer = ref<CustomerDetail | null>(null)
const assessments = ref<Assessment[]>([])
const packages = ref<CoursePackage[]>([])
const form = ref<CustomerForm>({ name: '' })
const trainingCardRef = ref<HTMLElement | null>(null)
let initialAssessmentReminderShown = false

/** 从助理「查看近期训练」进入时，落地后滚动到训练记录时间线。 */
const shouldFocusTraining = route.query.focus === 'training'
function scrollToTraining(): void {
  if (!shouldFocusTraining) return
  const el = trainingCardRef.value
  if (!el) return
  // 等训练时间线渲染后再滚动，避免布局未定导致定位偏差。
  requestAnimationFrame(() => el.scrollIntoView({ behavior: 'smooth', block: 'start' }))
}

/** 未有首次评估时，给康复师一次明确的下一步入口。 */
async function promptInitialAssessment(): Promise<void> {
  if (initialAssessmentReminderShown) return
  initialAssessmentReminderShown = true

  let initialStatus: Awaited<ReturnType<typeof apiGetInitialAssessment>>
  try {
    initialStatus = await apiGetInitialAssessment(customerId)
  } catch {
    // 接口失败时保持安静，不打断客户档案查看。
    return
  }
  // 已有首评即视为“已引导过”（无论草稿或已完成），避免重复打扰。
  if (initialStatus.exists) return

  try {
    await ElMessageBox.confirm(
      '该客户尚未完成首次评估。完成评估后，可据此制定康复计划并为后续 AI 辅助提供基础信息。',
      '尚未完成首次评估',
      {
        confirmButtonText: '去评估',
        cancelButtonText: '以后再说',
        type: 'warning',
        closeOnClickModal: false,
      },
    )
    router.push({ name: 'assessment-edit', query: { customerId, mode: 'initial' } })
  } catch {
    // 选择“以后再说”或关闭弹窗时，继续留在客户档案。
  }
}

async function loadCustomer(): Promise<void> {
  loading.value = true
  try {
    const [customerResult, assessmentResult, packageResult] = await Promise.all([
      apiGetCustomer(customerId),
      apiListAssessments(customerId),
      apiListCoursePackages(customerId),
    ])
    customer.value = customerResult
    assessments.value = assessmentResult
    packages.value = packageResult
    const c = customer.value
    form.value = {
      name: c.name,
      phone: c.phone,
      gender: c.gender,
      birth_date: c.birth_date,
      occupation: c.occupation,
      sport: c.sport,
      main_issue: c.main_issue,
      injury_date: c.injury_date,
      surgery_date: c.surgery_date,
      status: c.status,
      first_visit_date: c.first_visit_date,
      note: c.note,
    }
    await promptInitialAssessment()
    scrollToTraining()
  } finally {
    loading.value = false
  }
}

async function loadPackages(): Promise<void> {
  packages.value = await apiListCoursePackages(customerId)
}

async function handleSave(): Promise<void> {
  if (!form.value.name) {
    ElMessage.warning('请输入客户姓名')
    return
  }
  saving.value = true
  try {
    customer.value = await apiUpdateCustomer(customerId, form.value)
    editing.value = false
    ElMessage.success('客户信息已更新')
  } finally {
    saving.value = false
  }
}

onMounted(loadCustomer)
</script>

<template>
  <div v-loading="loading" class="customer-detail-page">
    <template v-if="customer">
      <div class="detail-header">
        <h2>{{ customer.name }}</h2>
        <el-tag :type="customer.status === 'active' ? 'success' : 'warning'" size="large">
          {{ customer.status_display }}
        </el-tag>
        <div class="spacer" />
        <el-button v-if="!editing" type="primary" @click="editing = true">编辑资料</el-button>
      </div>

      <el-card class="info-card">
        <template v-if="!editing">
          <el-descriptions :column="2" border>
            <el-descriptions-item label="姓名">{{ customer.name }}</el-descriptions-item>
            <el-descriptions-item label="手机号">{{ customer.phone }}</el-descriptions-item>
            <el-descriptions-item label="性别">{{ customer.gender_display || '未填写' }}</el-descriptions-item>
            <el-descriptions-item label="状态">{{ customer.status_display }}</el-descriptions-item>
            <el-descriptions-item label="主要问题">{{ customer.main_issue || '未填写' }}</el-descriptions-item>
            <el-descriptions-item label="运动项目">{{ customer.sport || '未填写' }}</el-descriptions-item>
            <el-descriptions-item label="职业">{{ customer.occupation || '未填写' }}</el-descriptions-item>
            <el-descriptions-item label="首次到店">{{ customer.first_visit_date || '未填写' }}</el-descriptions-item>
            <el-descriptions-item label="备注" :span="2">{{ customer.note || '无' }}</el-descriptions-item>
          </el-descriptions>
        </template>

        <el-form v-else :model="form" label-width="90px">
          <el-form-item label="姓名">
            <el-input v-model="form.name" />
          </el-form-item>
          <el-form-item label="手机号">
            <el-input v-model="form.phone" />
          </el-form-item>
          <el-form-item label="性别">
            <el-select v-model="form.gender" class="full-width">
              <el-option label="男" value="male" />
              <el-option label="女" value="female" />
            </el-select>
          </el-form-item>
          <el-form-item label="状态">
            <el-select v-model="form.status" class="full-width">
              <el-option label="正常" value="active" />
              <el-option label="暂停" value="paused" />
              <el-option label="结案" value="closed" />
            </el-select>
          </el-form-item>
          <el-form-item label="主要问题">
            <el-input v-model="form.main_issue" />
          </el-form-item>
          <el-form-item label="运动项目">
            <el-input v-model="form.sport" />
          </el-form-item>
          <el-form-item label="职业">
            <el-input v-model="form.occupation" />
          </el-form-item>
          <el-form-item label="首次到店">
            <el-date-picker v-model="form.first_visit_date" type="date" value-format="YYYY-MM-DD" class="full-width" />
          </el-form-item>
          <el-form-item label="备注">
            <el-input v-model="form.note" type="textarea" :rows="2" />
          </el-form-item>
          <div class="form-actions">
            <el-button @click="editing = false">取消</el-button>
            <el-button type="primary" :loading="saving" @click="handleSave">保存</el-button>
          </div>
        </el-form>
      </el-card>

      <el-card class="timeline-card">
        <LessonPreparation :customer-id="customer.id" />
      </el-card>

      <el-card class="timeline-card">
        <RehabPlanManager :customer-id="customer.id" :packages="packages" :assessments="assessments" />
        <el-divider />
        <RehabOverview :customer-id="customer.id" :assessments="assessments" />
      </el-card>

      <el-card class="timeline-card">
        <AuxiliaryServices :customer-id="customer.id" :packages="packages" @packages-changed="loadPackages" />
      </el-card>

      <el-card ref="trainingCardRef" class="timeline-card">
        <TrainingTimeline :customer-id="customer.id" />
      </el-card>
    </template>
  </div>
</template>

<style scoped>
.detail-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 18px;
}

.detail-header h2 {
  margin: 0;
  font-size: 20px;
  font-weight: 700;
}

.spacer {
  flex: 1;
}

.info-card,
.timeline-card {
  border-radius: var(--retrue-radius-lg);
  border: 1px solid var(--retrue-border);
  box-shadow: var(--retrue-shadow);
}

.timeline-card {
  margin-top: 16px;
}

.full-width {
  width: 100%;
}

.form-actions {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
}
</style>
