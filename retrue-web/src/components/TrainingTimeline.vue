<script setup lang="ts">
/** 客户训练时间线组件：展示该客户的训练记录并按日期倒序。 */

import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import { apiGetCustomerTimeline } from '@/api/training'
import type { TrainingRecord } from '@/types/api'

const props = defineProps<{ customerId: number }>()

const router = useRouter()
const loading = ref(false)
const records = ref<TrainingRecord[]>([])

async function loadTimeline(): Promise<void> {
  loading.value = true
  try {
    records.value = await apiGetCustomerTimeline(props.customerId)
  } finally {
    loading.value = false
  }
}

function goNew(): void {
  router.push({ name: 'training-edit', query: { customerId: props.customerId } })
}

function goAi(): void {
  router.push({ name: 'ai-draft', query: { customerId: props.customerId } })
}

function goEdit(record: TrainingRecord): void {
  router.push({ name: 'training-edit', params: { id: record.id } })
}

function formatExercises(record: TrainingRecord): string {
  return record.exercises.map((e) => e.exercise_name).join('、') || '无动作记录'
}

onMounted(loadTimeline)

defineExpose({ reload: loadTimeline })
</script>

<template>
  <div class="timeline">
    <div class="timeline-header">
      <span>训练时间线</span>
      <div class="header-actions">
        <el-button type="primary" size="small" @click="goAi">AI 记录</el-button>
        <el-button size="small" @click="goNew">手动记录</el-button>
      </div>
    </div>

    <el-empty v-if="!loading && records.length === 0" description="暂无训练记录" />

    <div v-loading="loading" class="timeline-list">
      <div v-for="record in records" :key="record.id" class="timeline-item" @click="goEdit(record)">
        <div class="timeline-date">{{ record.training_date }}</div>
        <div class="timeline-content">
          <div class="record-exercises">{{ formatExercises(record) }}</div>
          <div v-if="record.customer_feedback" class="record-feedback">感受：{{ record.customer_feedback }}</div>
          <div v-if="record.next_plan" class="record-plan">计划：{{ record.next_plan }}</div>
        </div>
        <el-icon class="timeline-arrow"><ArrowRight /></el-icon>
      </div>
    </div>
  </div>
</template>

<style scoped>
.timeline-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-weight: 600;
  margin-bottom: 12px;
}

.header-actions {
  display: flex;
  gap: 8px;
}

.timeline-list {
  display: flex;
  flex-direction: column;
}

.timeline-item {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 14px 8px;
  border-bottom: 1px solid var(--retrue-border);
  cursor: pointer;
  border-radius: var(--retrue-radius-sm);
}

.timeline-item:hover {
  background: var(--retrue-primary-light);
}

.timeline-date {
  font-weight: 600;
  color: var(--retrue-primary);
  width: 110px;
  flex-shrink: 0;
}

.timeline-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.record-exercises {
  font-weight: 500;
}

.record-feedback,
.record-plan {
  color: var(--retrue-text-secondary);
  font-size: 13px;
}

.timeline-arrow {
  color: var(--retrue-text-muted);
}
</style>
