<script setup lang="ts">
/** 康复概览组件：展示当前康复阶段与评估列表，提供评估/阶段管理入口。 */

import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'

import { apiGetCurrentStage, apiSetStage } from '@/api/rehab'
import type { Assessment, RehabStage, RehabStageType } from '@/types/api'

const props = defineProps<{ customerId: number; assessments: Assessment[] }>()

const router = useRouter()
const loading = ref(false)
const currentStage = ref<RehabStage | null>(null)

// 阶段设置弹窗
const stageVisible = ref(false)
const stageForm = ref({ stage_type: 'strength' as RehabStageType, start_date: '', note: '' })

const stageOptions: { label: string; value: RehabStageType }[] = [
  { label: '急性期/疼痛控制', value: 'acute' },
  { label: '恢复期/活动度恢复', value: 'recovery' },
  { label: '力量重建期', value: 'strength' },
  { label: '功能回归期', value: 'functional' },
]

async function load(): Promise<void> {
  loading.value = true
  try {
    currentStage.value = await apiGetCurrentStage(props.customerId)
  } finally {
    loading.value = false
  }
}

function goNewAssessment(): void {
  router.push({ name: 'assessment-edit', query: { customerId: props.customerId } })
}

function goEditAssessment(assessment: Assessment): void {
  router.push({ name: 'assessment-edit', params: { id: assessment.id } })
}

function openStageDialog(): void {
  stageForm.value = {
    stage_type: (currentStage.value?.stage_type as RehabStageType) || 'strength',
    start_date: new Date().toISOString().slice(0, 10),
    note: '',
  }
  stageVisible.value = true
}

async function saveStage(): Promise<void> {
  if (!stageForm.value.start_date) {
    ElMessage.warning('请选择进入日期')
    return
  }
  await apiSetStage({ customer: props.customerId, ...stageForm.value })
  ElMessage.success('康复阶段已更新')
  stageVisible.value = false
  await load()
}

function stageTagType(stageType: string): 'danger' | 'warning' | 'primary' | 'success' {
  const map: Record<string, 'danger' | 'warning' | 'primary' | 'success'> = {
    acute: 'danger',
    recovery: 'warning',
    strength: 'primary',
    functional: 'success',
  }
  return map[stageType] || 'info'
}

onMounted(load)
</script>

<template>
  <div v-loading="loading" class="rehab-overview">
    <!-- 当前阶段 -->
    <div class="stage-row">
      <span class="section-title">当前康复阶段：</span>
      <template v-if="currentStage">
        <el-tag :type="stageTagType(currentStage.stage_type)">
          {{ currentStage.stage_type_display }}
        </el-tag>
        <span class="stage-date">自 {{ currentStage.start_date }}</span>
      </template>
      <span v-else class="no-stage">未设置</span>
      <el-button link type="primary" size="small" @click="openStageDialog">调整阶段</el-button>
    </div>

    <!-- 评估列表 -->
    <div class="assess-header">
      <span class="section-title">评估记录</span>
      <el-button type="primary" size="small" @click="goNewAssessment">新增评估</el-button>
    </div>

    <el-empty v-if="!loading && props.assessments.length === 0" description="暂无评估记录" :image-size="60" />

    <div class="assess-list">
      <div v-for="assessment in props.assessments" :key="assessment.id" class="assess-item" @click="goEditAssessment(assessment)">
        <div class="assess-main">
          <el-tag size="small">{{ assessment.assessment_type_display }}</el-tag>
          <span class="assess-date">{{ assessment.assessment_date }}</span>
          <span v-if="assessment.chief_complaint" class="assess-complaint">{{ assessment.chief_complaint }}</span>
        </div>
        <div class="assess-metrics">
          <el-tag v-for="m in assessment.metrics.slice(0, 3)" :key="m.id" size="small" type="info" effect="plain">
            {{ m.metric_type_display }} {{ m.score }}{{ m.score_max ? '/' + m.score_max : '' }}
          </el-tag>
        </div>
      </div>
    </div>

    <!-- 阶段设置弹窗 -->
    <el-dialog v-model="stageVisible" title="调整康复阶段" width="420px">
      <el-form :model="stageForm" label-width="80px">
        <el-form-item label="阶段">
          <el-select v-model="stageForm.stage_type" class="full-width">
            <el-option v-for="opt in stageOptions" :key="opt.value" :label="opt.label" :value="opt.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="进入日期">
          <el-date-picker v-model="stageForm.start_date" type="date" value-format="YYYY-MM-DD" class="full-width" />
        </el-form-item>
        <el-form-item label="说明">
          <el-input v-model="stageForm.note" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="stageVisible = false">取消</el-button>
        <el-button type="primary" @click="saveStage">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.stage-row {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 16px;
}

.section-title {
  font-weight: 600;
}

.no-stage {
  color: var(--retrue-text-muted);
}

.stage-date {
  color: var(--retrue-text-secondary);
  font-size: 13px;
}

.assess-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
}

.assess-item {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 10px 6px;
  border-bottom: 1px solid var(--retrue-border);
  cursor: pointer;
  border-radius: var(--retrue-radius-sm);
}

.assess-item:hover {
  background: var(--retrue-primary-light);
}

.assess-main {
  display: flex;
  align-items: center;
  gap: 10px;
}

.assess-date {
  font-weight: 500;
}

.assess-complaint {
  color: var(--retrue-text-secondary);
  font-size: 13px;
}

.assess-metrics {
  display: flex;
  gap: 8px;
}

.full-width {
  width: 100%;
}
</style>
