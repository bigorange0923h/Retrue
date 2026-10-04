<script setup lang="ts">
/** 客户详情页：展示与编辑客户资料（编辑场景含完整手机号）。 */

import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { onBeforeRouteLeave, onBeforeRouteUpdate, useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'

import { apiGetCustomer, apiUpdateCustomer, type CustomerForm } from '@/api/customers'
import { apiListAssessments } from '@/api/assessments'
import { apiListCoursePackages } from '@/api/coursePackages'
import AuxiliaryServices from '@/components/AuxiliaryServices.vue'
import CustomerMemoryManager from '@/components/CustomerMemoryManager.vue'
import CustomerAliasManager from '@/components/CustomerAliasManager.vue'
import CustomerDataTools from '@/components/CustomerDataTools.vue'
import LessonPreparation from '@/components/LessonPreparation.vue'
import RehabOverview from '@/components/RehabOverview.vue'
import RehabPlanManager from '@/components/RehabPlanManager.vue'
import TrainingTimeline from '@/components/TrainingTimeline.vue'
import type { Assessment, CoursePackage, CustomerDetail } from '@/types/api'
import { createCustomerScope } from '@/utils/customerScope'

const route = useRoute()
const router = useRouter()
const customerId = computed(() => Number(route.params.id))
const scope = createCustomerScope()

const loading = ref(false)
const editing = ref(false)
const saving = ref(false)
const customer = ref<CustomerDetail | null>(null)
const assessments = ref<Assessment[]>([])
const packages = ref<CoursePackage[]>([])
const form = ref<CustomerForm>({ name: '' })
const trainingCardRef = ref<HTMLElement | null>(null)
const loadFailed = ref(false)
let savedForm = ''
let loadSequence = 0
const initialAssessment = computed(() => assessments.value.find((item) => item.assessment_type === 'initial'))

/** 从助理「查看近期训练」进入时，落地后滚动到训练记录时间线。 */
function scrollToTraining(): void {
  if (route.query.focus !== 'training') return
  const el = trainingCardRef.value
  if (!el) return
  // 等训练时间线渲染后再滚动，避免布局未定导致定位偏差。
  requestAnimationFrame(() => el.scrollIntoView({ behavior: 'smooth', block: 'start' }))
}

/** 首评草稿继续原记录，已完成首评不重复创建。 */
function goInitialAssessment(): void {
  const initial = initialAssessment.value
  router.push(initial
    ? { name: 'assessment-revise', params: { id: initial.id } }
    : { name: 'assessment-edit', query: { customerId: customerId.value, mode: 'initial' } })
}

async function loadCustomer(): Promise<void> {
  const snapshot = scope.capture()
  const sequence = ++loadSequence
  loading.value = true
  loadFailed.value = false
  try {
    const [customerResult, assessmentResult, packageResult] = await Promise.all([
      apiGetCustomer(snapshot.customerId),
      apiListAssessments(snapshot.customerId),
      apiListCoursePackages(snapshot.customerId),
    ])
    if (!scope.isCurrent(snapshot) || sequence !== loadSequence) return
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
    savedForm = JSON.stringify(form.value)
    await nextTick()
    scrollToTraining()
  } catch {
    if (scope.isCurrent(snapshot) && sequence === loadSequence) loadFailed.value = true
  } finally {
    if (scope.isCurrent(snapshot) && sequence === loadSequence) loading.value = false
  }
}

async function loadPackages(): Promise<void> {
  const snapshot = scope.capture()
  const result = await apiListCoursePackages(snapshot.customerId)
  if (scope.isCurrent(snapshot)) packages.value = result
}

async function handleSave(): Promise<void> {
  if (saving.value || !customer.value) return
  if (!form.value.name) {
    ElMessage.warning('请输入客户姓名')
    return
  }
  saving.value = true
  const snapshot = scope.capture()
  const payload = { ...form.value }
  try {
    const result = await apiUpdateCustomer(snapshot.customerId, payload)
    if (!scope.isCurrent(snapshot)) return
    customer.value = result
    savedForm = JSON.stringify(payload)
    editing.value = false
    ElMessage.success('客户信息已更新')
  } finally {
    if (scope.isCurrent(snapshot)) saving.value = false
  }
}

/** 未保存的资料不会因前进、后退或切换客户静默丢弃。 */
async function confirmNavigation(): Promise<boolean> {
  if (!editing.value || JSON.stringify(form.value) === savedForm) return true
  try {
    await ElMessageBox.confirm('客户资料尚未保存，离开将丢弃本页修改。', '离开客户资料', {
      confirmButtonText: '丢弃并离开', cancelButtonText: '继续编辑', type: 'warning',
    })
    return true
  } catch { return false }
}
onBeforeRouteLeave(confirmNavigation)
onBeforeRouteUpdate((to, from) => to.params.id === from.params.id ? true : confirmNavigation())
watch(customerId, (id) => {
  scope.reset(id)
  customer.value = null
  assessments.value = []
  packages.value = []
  form.value = { name: '' }
  editing.value = false
  saving.value = false
  if (Number.isInteger(id) && id > 0) void loadCustomer()
  else loadFailed.value = true
}, { immediate: true })
onBeforeUnmount(() => scope.reset(0))
</script>

<template>
  <div v-loading="loading" class="customer-detail-page">
    <el-alert v-if="loadFailed" title="客户资料加载失败，请重试。" type="error" :closable="false">
      <el-button link type="primary" @click="loadCustomer">重新加载</el-button>
    </el-alert>
    <template v-if="customer" :key="customer.id">
      <div class="detail-header">
        <h2>{{ customer.name }}</h2>
        <el-tag :type="customer.status === 'active' ? 'success' : 'warning'" size="large">
          {{ customer.status_display }}
        </el-tag>
        <div class="spacer" />
        <el-button v-if="!editing" type="primary" @click="editing = true">编辑资料</el-button>
      </div>

      <el-alert v-if="!initialAssessment || initialAssessment.status !== 'completed'" title="尚未完成首次评估" type="info" :closable="false">
        <el-button link type="primary" @click="goInitialAssessment">{{ initialAssessment ? '继续评估' : '去评估' }}</el-button>
      </el-alert>

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

        <el-form v-else :model="form" label-width="90px" :disabled="saving">
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

      <el-card class="timeline-card"><CustomerAliasManager :customer-id="customer.id" /></el-card>
      <el-card class="timeline-card"><CustomerDataTools :customer-id="customer.id" /></el-card>

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

      <el-card class="timeline-card">
        <CustomerMemoryManager :customer-id="customer.id" />
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
