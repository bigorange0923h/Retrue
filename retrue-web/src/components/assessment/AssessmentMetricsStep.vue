<script setup lang="ts">
/** 第三步：选择评估类型并使用对应的临床录入控件。 */

import { ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { AssessmentMetricDefinition, AssessmentMetricInput, MetricType } from '@/types/api'
import MetricTypePicker from './MetricTypePicker.vue'
import PainMetricEditor from './metrics/PainMetricEditor.vue'
import StrengthMetricEditor from './metrics/StrengthMetricEditor.vue'
import RomMetricEditor from './metrics/RomMetricEditor.vue'
import SpecialTestMetricEditor from './metrics/SpecialTestMetricEditor.vue'
import FunctionalMetricEditor from './metrics/FunctionalMetricEditor.vue'

const props = defineProps<{
  definitions?: AssessmentMetricDefinition[]
  previousMetrics?: AssessmentMetricInput[]
  previousAssessmentDate?: string
}>()

const metrics = defineModel<AssessmentMetricInput[]>({ required: true })
const pickerVisible = ref(false)
const selectedType = ref<MetricType>('pain')

const typeLabels: Record<MetricType, string> = {
  pain: '疼痛',
  strength: '肌力',
  rom: '活动度',
  special_test: '特殊测试',
  functional: '功能动作',
}

const typeHints: Record<MetricType, string> = {
  pain: '使用 0～10 疼痛程度',
  strength: '使用 MRC 0～5 级',
  rom: '记录实际关节角度',
  special_test: '记录阳性、阴性或无法判断',
  functional: '观察正常、受限或无法完成',
}

function createMetric(type: MetricType): AssessmentMetricInput {
  return {
    metric_type: type,
    body_part: '',
    score: null,
    description: '',
    sort_order: metrics.value.length,
    side: '',
    scale_code: '',
    unit: '',
    context: '',
    movement: '',
    measurement_mode: '',
    result_code: '',
    details: {},
  }
}

function addMetric(): void {
  metrics.value.push(createMetric(selectedType.value))
  pickerVisible.value = false
}

function removeMetric(index: number): void {
  metrics.value.splice(index, 1)
  metrics.value.forEach((metric, metricIndex) => { metric.sort_order = metricIndex })
}

function metricTitle(type: MetricType): string {
  return typeLabels[type]
}

function editorComponent(type: MetricType) {
  switch (type) {
    case 'pain': return PainMetricEditor
    case 'strength': return StrengthMetricEditor
    case 'rom': return RomMetricEditor
    case 'special_test': return SpecialTestMetricEditor
    case 'functional': return FunctionalMetricEditor
  }
}

function definitionHint(type: MetricType): string {
  const definition = props.definitions?.find((item) => item.metric_type === type)
  return definition?.description || typeHints[type]
}

async function importPreviousMetrics(): Promise<void> {
  if (!props.previousMetrics?.length) return
  if (metrics.value.length > 0) {
    try {
      await ElMessageBox.confirm('导入会替换当前已经添加的评估项目，是否继续？', '导入上次评估项目', {
        confirmButtonText: '替换并导入',
        cancelButtonText: '取消',
        type: 'warning',
      })
    } catch {
      return
    }
  }
  metrics.value = props.previousMetrics.map((metric, index) => ({
    ...metric,
    details: { ...(metric.details || {}) },
    sort_order: index,
  }))
  ElMessage.success('已带入上次的评估项目，请填写本次测量结果')
}
</script>

<template>
  <section class="assessment-step">
    <div class="step-intro">
      <p class="eyebrow">第三步 / 客观评估</p>
      <h3>按实际观察添加评估项目</h3>
      <p>先选择项目类型，系统会自动提供对应的填写方式。无需填写满分、单位或量表规则。</p>
    </div>

    <el-alert title="可以只记录本次确实完成的项目，暂不清楚的项目可先不添加。" type="info" :closable="false" show-icon />

    <el-alert
      v-if="props.previousMetrics?.length"
      :title="`发现 ${props.previousAssessmentDate || '上一次'} 的已完成评估，可沿用项目结构后重新填写本次结果。`"
      type="success"
      :closable="false"
      show-icon
    >
      <template #default>
        <el-button type="success" plain class="import-previous-button" @click="importPreviousMetrics">导入上次评估项目</el-button>
      </template>
    </el-alert>

    <div class="metrics-list">
      <article v-for="(metric, index) in metrics" :key="`${metric.metric_type}-${index}`" class="metric-card">
        <div class="metric-card-header">
          <div>
            <div class="metric-card-title"><span class="metric-number">{{ index + 1 }}</span>{{ metricTitle(metric.metric_type) }}</div>
            <p>{{ definitionHint(metric.metric_type) }}</p>
          </div>
          <el-button link type="danger" @click="removeMetric(index)">删除此项目</el-button>
        </div>

        <el-form label-position="top" class="metric-form">
          <component :is="editorComponent(metric.metric_type)" v-model="metrics[index]" />
        </el-form>
      </article>
    </div>

    <el-empty v-if="metrics.length === 0" description="还没有添加客观评估项目" :image-size="76" />

    <el-button type="primary" plain class="add-metric-button" @click="pickerVisible = true">
      <el-icon><Plus /></el-icon>
      添加评估项目
    </el-button>

    <el-dialog v-model="pickerVisible" title="选择评估项目" width="min(640px, 92vw)" destroy-on-close>
      <p class="picker-description">选择后会打开对应的填写卡片。</p>
      <MetricTypePicker v-model="selectedType" />
      <template #footer>
        <el-button @click="pickerVisible = false">取消</el-button>
        <el-button type="primary" @click="addMetric">添加项目</el-button>
      </template>
    </el-dialog>
  </section>
</template>

<style scoped>
.assessment-step {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.step-intro h3 {
  margin: 4px 0 7px;
  font-size: 20px;
}

.step-intro p {
  margin: 0;
  color: var(--retrue-text-secondary);
  line-height: 1.7;
}

.step-intro .eyebrow {
  color: var(--retrue-primary);
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.08em;
}

.metrics-list {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.metric-card {
  border: 1px solid var(--retrue-border);
  border-radius: var(--retrue-radius-md);
  background: var(--retrue-surface-subtle);
  padding: 18px;
}

.metric-card-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
}

.metric-card-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 16px;
  font-weight: 700;
}

.metric-number {
  display: grid;
  width: 24px;
  height: 24px;
  place-items: center;
  border-radius: 50%;
  background: var(--retrue-primary-light);
  color: var(--retrue-primary-dark);
  font-size: 12px;
}

.metric-card-header p {
  margin: 5px 0 0 32px;
  color: var(--retrue-text-secondary);
  font-size: 12px;
}

.metric-form {
  width: 100%;
}

.add-metric-button {
  align-self: flex-start;
  min-height: 44px;
}

.import-previous-button {
  min-height: 44px;
  margin-top: 10px;
}

.picker-description {
  margin: 0 0 14px;
  color: var(--retrue-text-secondary);
  font-size: 13px;
}

@media (max-width: 768px) {
  .metric-card {
    padding: 14px;
  }

  .metric-card-header {
    flex-direction: column;
  }

  .metric-card-header :deep(.el-button) {
    width: 100%;
    justify-content: flex-start;
    min-height: 44px;
  }

  .add-metric-button {
    width: 100%;
  }

  .import-previous-button {
    width: 100%;
    margin-left: 0;
  }
}
</style>
