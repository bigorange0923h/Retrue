<script setup lang="ts">
/** 评估编辑页：支持新建与编辑评估，包含评估指标。 */

import { onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'

import { apiCreateAssessment, apiGetAssessment, apiUpdateAssessment, type AssessmentForm } from '@/api/assessments'
import type { MetricType } from '@/types/api'

const route = useRoute()
const router = useRouter()

const customerId = Number(route.query.customerId || route.params.customerId)
const assessmentId = route.params.id ? Number(route.params.id) : null

const loading = ref(false)
const saving = ref(false)

const metricTypeOptions: { label: string; value: MetricType }[] = [
  { label: '疼痛 NRS', value: 'pain' },
  { label: '肌力分级', value: 'strength' },
  { label: '活动度', value: 'rom' },
  { label: '特殊测试', value: 'special_test' },
  { label: '功能动作', value: 'functional' },
]

const form = reactive<AssessmentForm>({
  customer: customerId,
  assessment_type: 'initial',
  assessment_date: '',
  chief_complaint: '',
  medical_history: '',
  rehab_goal: '',
  current_status: '',
  note: '',
  metrics: [],
})

function addMetric(): void {
  form.metrics.push({
    metric_type: 'pain',
    metric_type_display: '',
    body_part: '',
    score: null,
    score_max: null,
    description: '',
    sort_order: form.metrics.length,
  })
}

function removeMetric(index: number): void {
  form.metrics.splice(index, 1)
}

async function loadForEdit(): Promise<void> {
  if (!assessmentId) return
  loading.value = true
  try {
    const assessment = await apiGetAssessment(assessmentId)
    form.customer = assessment.customer
    form.assessment_type = assessment.assessment_type
    form.assessment_date = assessment.assessment_date
    form.chief_complaint = assessment.chief_complaint
    form.medical_history = assessment.medical_history
    form.rehab_goal = assessment.rehab_goal
    form.current_status = assessment.current_status
    form.note = assessment.note
    form.metrics = assessment.metrics.map((m, i) => ({ ...m, sort_order: i }))
  } finally {
    loading.value = false
  }
}

async function handleSave(): Promise<void> {
  if (!form.assessment_date) {
    ElMessage.warning('请选择评估日期')
    return
  }
  const metrics = form.metrics.filter((m) => m.metric_type)
  const payload = { ...form, metrics }

  saving.value = true
  try {
    if (assessmentId) {
      await apiUpdateAssessment(assessmentId, payload)
      ElMessage.success('评估已更新')
    } else {
      await apiCreateAssessment(payload)
      ElMessage.success('评估已创建')
    }
    router.push({ name: 'customer-detail', params: { id: customerId } })
  } finally {
    saving.value = false
  }
}

onMounted(() => {
  loadForEdit()
  if (!form.assessment_date) {
    form.assessment_date = new Date().toISOString().slice(0, 10)
  }
  if (form.metrics.length === 0) {
    addMetric()
  }
})
</script>

<template>
  <div v-loading="loading" class="assessment-edit-page">
    <div class="page-header">
      <h2>{{ assessmentId ? '编辑评估' : '新建评估' }}</h2>
      <el-button @click="router.back()">返回</el-button>
    </div>

    <el-card class="form-card">
      <el-form label-width="90px">
        <el-form-item label="评估日期">
          <el-date-picker v-model="form.assessment_date" type="date" value-format="YYYY-MM-DD" />
        </el-form-item>
        <el-form-item label="评估类型">
          <el-select v-model="form.assessment_type">
            <el-option label="首次评估" value="initial" />
            <el-option label="阶段复评" value="reassessment" />
          </el-select>
        </el-form-item>

        <el-divider content-position="left">评估指标</el-divider>
        <div v-for="(metric, index) in form.metrics" :key="index" class="metric-row">
          <el-select v-model="metric.metric_type" class="metric-type">
            <el-option v-for="opt in metricTypeOptions" :key="opt.value" :label="opt.label" :value="opt.value" />
          </el-select>
          <el-input v-model="metric.body_part" placeholder="部位" class="metric-part" />
          <el-input-number v-model="metric.score" :min="0" :max="metric.score_max ?? 10" placeholder="评分" class="metric-num" />
          <el-input-number v-model="metric.score_max" :min="0" placeholder="满分" class="metric-num" />
          <el-input v-model="metric.description" placeholder="描述（诱发动作等）" class="metric-desc" />
          <el-button link type="danger" @click="removeMetric(index)">删除</el-button>
        </div>
        <el-button link type="primary" @click="addMetric">+ 添加指标</el-button>

        <el-divider content-position="left">评估内容</el-divider>
        <el-form-item label="主诉">
          <el-input v-model="form.chief_complaint" type="textarea" :rows="2" placeholder="哪里不舒服、何时开始等" />
        </el-form-item>
        <el-form-item label="病史">
          <el-input v-model="form.medical_history" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item label="康复目标">
          <el-input v-model="form.rehab_goal" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item v-if="form.assessment_type === 'reassessment'" label="当前状态">
          <el-input v-model="form.current_status" type="textarea" :rows="2" />
        </el-form-item>

        <div class="form-actions">
          <el-button @click="router.back()">取消</el-button>
          <el-button type="primary" :loading="saving" @click="handleSave">保存</el-button>
        </div>
      </el-form>
    </el-card>
  </div>
</template>

<style scoped>
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.page-header h2 {
  margin: 0;
}

.form-card {
  border-radius: 12px;
  max-width: 780px;
}

.metric-row {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-bottom: 8px;
}

.metric-type {
  width: 130px;
}

.metric-part {
  width: 100px;
}

.metric-num {
  width: 100px;
}

.metric-desc {
  flex: 1;
}

.form-actions {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
}
</style>
