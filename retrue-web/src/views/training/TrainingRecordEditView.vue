<script setup lang="ts">
/** 训练记录编辑页：支持新建与人工修订（修订需填原因）。 */

import { onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'

import {
  apiCreateTrainingRecord,
  apiGetTrainingRecord,
  apiReviseTrainingRecord,
} from '@/api/training'
import type { TrainingExercise } from '@/types/api'

const route = useRoute()
const router = useRouter()

const customerId = Number(route.query.customerId || route.params.customerId)
const recordId = route.params.id ? Number(route.params.id) : null

const loading = ref(false)
const saving = ref(false)
const reason = ref('')

const form = reactive({
  customer: customerId,
  training_date: '',
  customer_feedback: '',
  therapist_observation: '',
  next_plan: '',
  note: '',
  exercises: [] as TrainingExercise[],
})

function addExercise(): void {
  form.exercises.push({ exercise_name: '', sets: null, reps: null, weight: '', duration_seconds: null, note: '', sort_order: form.exercises.length })
}

function removeExercise(index: number): void {
  form.exercises.splice(index, 1)
}

async function loadForEdit(): Promise<void> {
  if (!recordId) return
  loading.value = true
  try {
    const record = await apiGetTrainingRecord(recordId)
    form.customer = record.customer
    form.training_date = record.training_date
    form.customer_feedback = record.customer_feedback
    form.therapist_observation = record.therapist_observation
    form.next_plan = record.next_plan
    form.note = record.note
    form.exercises = record.exercises.map((e, i) => ({ ...e, sort_order: i }))
  } finally {
    loading.value = false
  }
}

async function handleSave(): Promise<void> {
  if (!form.training_date) {
    ElMessage.warning('请选择训练日期')
    return
  }
  // 修订模式必须填写原因
  if (recordId && !reason.value) {
    ElMessage.warning('修订正式记录必须填写修改原因')
    return
  }
  // 过滤空动作
  const exercises = form.exercises.filter((e) => e.exercise_name.trim())
  const payload = { ...form, exercises }

  saving.value = true
  try {
    if (recordId) {
      await apiReviseTrainingRecord(recordId, { ...payload, reason: reason.value })
      ElMessage.success('训练记录已更新')
    } else {
      await apiCreateTrainingRecord(payload)
      ElMessage.success('训练记录已创建')
    }
    router.push({ name: 'customer-detail', params: { id: customerId } })
  } finally {
    saving.value = false
  }
}

onMounted(() => {
  loadForEdit()
  if (!form.training_date) {
    form.training_date = new Date().toISOString().slice(0, 10)
  }
  if (form.exercises.length === 0) {
    addExercise()
  }
})
</script>

<template>
  <div v-loading="loading" class="record-edit-page">
    <div class="page-header">
      <h2>{{ recordId ? '修订训练记录' : '新建训练记录' }}</h2>
      <el-button @click="router.back()">返回</el-button>
    </div>

    <el-card class="form-card">
      <el-form label-width="90px">
        <el-form-item label="训练日期">
          <el-date-picker v-model="form.training_date" type="date" value-format="YYYY-MM-DD" />
        </el-form-item>

        <el-divider content-position="left">训练动作</el-divider>
        <div v-for="(ex, index) in form.exercises" :key="index" class="exercise-row">
          <el-input v-model="ex.exercise_name" placeholder="动作名称" class="ex-name" />
          <el-input-number v-model="ex.sets" :min="0" placeholder="组" class="ex-num" />
          <el-input-number v-model="ex.reps" :min="0" placeholder="次" class="ex-num" />
          <el-input v-model="ex.weight" placeholder="重量" class="ex-weight" />
          <el-input-number v-model="ex.duration_seconds" :min="0" placeholder="秒" class="ex-num" />
          <el-button link type="danger" @click="removeExercise(index)">删除</el-button>
        </div>
        <el-button link type="primary" @click="addExercise">+ 添加动作</el-button>

        <el-divider content-position="left">记录内容</el-divider>
        <el-form-item label="客户感受">
          <el-input v-model="form.customer_feedback" type="textarea" :rows="2" placeholder="如：左膝下蹲疼痛 NRS 2，比上次稳定" />
        </el-form-item>
        <el-form-item label="康复师观察">
          <el-input v-model="form.therapist_observation" type="textarea" :rows="2" placeholder="观察到的改善或问题" />
        </el-form-item>
        <el-form-item label="下次计划">
          <el-input v-model="form.next_plan" type="textarea" :rows="2" placeholder="下次训练计划方向" />
        </el-form-item>

        <el-form-item v-if="recordId" label="修改原因">
          <el-input v-model="reason" type="textarea" :rows="2" placeholder="修订正式记录必须填写修改原因" />
        </el-form-item>

        <div class="form-actions">
          <el-button @click="router.back()">取消</el-button>
          <el-button type="primary" :loading="saving" @click="handleSave">
            {{ recordId ? '保存修订' : '创建记录' }}
          </el-button>
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
  max-width: 720px;
}

.exercise-row {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-bottom: 8px;
}

.ex-name {
  flex: 1;
}

.ex-num {
  width: 110px;
}

.ex-weight {
  width: 90px;
}

.form-actions {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
}
</style>
